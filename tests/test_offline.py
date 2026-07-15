"""Offline tests for the core engine: llm.agent_call, datastore, orchestrator.

No network — the anthropic client is fully mocked with SimpleNamespace
objects shaped like real SDK responses.
Run: .venv/bin/python -m unittest tests.test_offline -v
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from swarm import orchestrator
from swarm.events import EventBus, validate_events
from swarm.llm import CostTracker, agent_call
from swarm.schemas import (
    CRITIC_SCHEMA,
    DECOMPOSE_SCHEMA,
    PACKAGE_SCHEMA,
    SPECIALIST_SCHEMAS,
)
from swarm.tools import TOOL_SCHEMAS

# ── canned SDK-shaped fixtures ────────────────────────────────────────────────


def _usage(inp=100, out=50, cr=0, cw=0):
    return SimpleNamespace(
        input_tokens=inp,
        output_tokens=out,
        cache_read_input_tokens=cr,
        cache_creation_input_tokens=cw,
    )


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_block(name, input_data, block_id="toolu_01"):
    return SimpleNamespace(type="tool_use", name=name, input=input_data, id=block_id)


def _message(content, stop_reason="end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=_usage())


class FakeStream:
    """Context manager shaped like anthropic's MessageStream; yields no events."""

    def __init__(self, final_message):
        self._final = final_message

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter([])

    def get_final_message(self):
        return self._final


def fake_client(stream_messages=(), create_responses=()):
    client = SimpleNamespace(messages=SimpleNamespace())
    client.messages.stream = mock.Mock(
        side_effect=[FakeStream(m) for m in stream_messages]
    )
    client.messages.create = mock.Mock(side_effect=list(create_responses))
    return client


SIMPLE_SCHEMA = {"type": "json_schema", "schema": {"type": "object"}}


# ── 1 + 2: agent_call ─────────────────────────────────────────────────────────


class TestAgentCall(unittest.TestCase):
    def test_tool_loop_then_structured_call(self):
        bus = EventBus(None)
        client = fake_client(
            stream_messages=[
                _message(
                    [
                        _text_block("Let me check the length."),
                        _tool_block("count_characters", {"text": "hi"}),
                    ],
                    stop_reason="tool_use",
                ),
                _message([_text_block("Done checking.")], stop_reason="end_turn"),
            ],
            create_responses=[_message([_text_block('{"ok": true}')])],
        )
        result = agent_call(
            bus,
            "social",
            client=client,
            model="claude-sonnet-4-6",
            system_blocks=[{"type": "text", "text": "sys"}],
            tools=[TOOL_SCHEMAS["count_characters"]],
            messages=[{"role": "user", "content": "check 'hi'"}],
            output_schema=SIMPLE_SCHEMA,
            cost_tracker=CostTracker(),
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(client.messages.stream.call_count, 2)
        self.assertEqual(client.messages.create.call_count, 1)

        types = [e["type"] for e in bus.history]
        self.assertIn("agent_tool_use", types)
        self.assertIn("agent_tool_result", types)
        self.assertEqual(types.count("cost_update"), 3)  # 2 streams + 1 create

        tool_result = next(e for e in bus.history if e["type"] == "agent_tool_result")
        self.assertEqual(tool_result["data"]["tool"], "count_characters")
        self.assertIn("characters", tool_result["data"]["summary"])

        # Final structured call must carry output_config + tool_choice none.
        final_kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(final_kwargs["output_config"], {"format": SIMPLE_SCHEMA})
        self.assertEqual(final_kwargs["tool_choice"], {"type": "none"})

    def test_retries_once_on_malformed_json(self):
        bus = EventBus(None)
        client = fake_client(
            create_responses=[
                _message([_text_block("sorry, here is prose not JSON {")]),
                _message([_text_block('{"fixed": 1}')]),
            ]
        )
        result = agent_call(
            bus,
            "coordinator",
            client=client,
            model="claude-sonnet-4-6",
            system_blocks=[{"type": "text", "text": "sys"}],
            tools=[],
            messages=[{"role": "user", "content": "go"}],
            output_schema=SIMPLE_SCHEMA,
            cost_tracker=CostTracker(),
        )
        self.assertEqual(result, {"fixed": 1})
        self.assertEqual(client.messages.create.call_count, 2)
        # The retry call must include a corrective user message.
        retry_messages = client.messages.create.call_args.kwargs["messages"]
        self.assertIn("valid JSON", str(retry_messages[-1]["content"]))


# ── 3: tweet enforcement ──────────────────────────────────────────────────────


class TestTweetEnforcement(unittest.TestCase):
    def test_truncates_and_pads_to_exactly_three(self):
        long_tweet = "x" * 300
        package = {
            "press_statement": "s",
            "internal_talking_points": ["a"],
            "tweets": [long_tweet],
        }
        fixed = orchestrator.enforce_tweet_limits(
            package, social_drafts=["a fine draft", "y" * 400]
        )
        self.assertEqual(len(fixed["tweets"]), 3)
        self.assertTrue(all(len(t) <= 280 for t in fixed["tweets"]))
        self.assertEqual(fixed["tweets"][0], "x" * 277 + "...")
        self.assertEqual(fixed["tweets"][1], "a fine draft")

    def test_trims_extras_and_pads_with_fallback(self):
        package = {"tweets": ["a", "b", "c", "d"]}
        self.assertEqual(orchestrator.enforce_tweet_limits(package)["tweets"], ["a", "b", "c"])
        padded = orchestrator.enforce_tweet_limits({"tweets": []})
        self.assertEqual(len(padded["tweets"]), 3)
        self.assertTrue(all(len(t) <= 280 for t in padded["tweets"]))


# ── 4: datastore teaching strings ─────────────────────────────────────────────


class TestDatastore(unittest.TestCase):
    def setUp(self):
        from swarm.tools import datastore

        self.datastore = datastore
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        (pathlib.Path(self.tmp.name) / "company_facts.json").write_text(
            json.dumps(
                {
                    "company": {"name": "Lumina Cloud"},
                    "products": [],
                    "slas": [],
                    "execs": [],
                    "facts": [
                        {"topic": "uptime SLA", "fact": "Compute SLA is 99.95% monthly."},
                        {"topic": "the llama", "fact": "Biscuit has an office-only badge."},
                    ],
                }
            )
        )
        patcher = mock.patch.object(self.datastore, "DATA_DIR", pathlib.Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unknown_lookup_returns_teaching_string(self):
        result = self.datastore.lookup_company_fact("zzz-nonexistent-topic")
        self.assertIn("uptime SLA", result)  # lists valid topics
        self.assertIn("the llama", result)
        self.assertNotIn("Traceback", result)

    def test_hit_returns_the_fact(self):
        self.assertIn("99.95%", self.datastore.lookup_company_fact("uptime"))

    def test_missing_file_returns_helpful_string(self):
        result = self.datastore.search_past_incidents("outage")
        self.assertIn("data/past_incidents.json not present", result)

    def test_count_characters_needs_no_files(self):
        self.assertIn("fits", self.datastore.count_characters("short tweet"))
        self.assertIn("OVER", self.datastore.count_characters("x" * 281))


# ── cached-prompt size guardrails ─────────────────────────────────────────────


class TestPromptSizes(unittest.TestCase):
    MIN_CACHED_CHARS = 9000  # ~2,250 tokens at 4 chars/token > Sonnet's 2,048 floor

    def test_specialist_playbooks_clear_cache_floor(self):
        from swarm.agents import SPECIALISTS

        self.assertEqual(
            set(SPECIALISTS), {"fact_checker", "legal", "comms", "social"}
        )
        for name, spec in SPECIALISTS.items():
            self.assertGreater(len(spec.playbook), self.MIN_CACHED_CHARS, name)
            self.assertNotIn("time.time", spec.playbook)

    def test_coordinator_prompts_clear_cache_floor(self):
        from swarm.agents.coordinator import DECOMPOSE_PROMPT, SYNTHESIS_PROMPT

        self.assertGreater(len(DECOMPOSE_PROMPT), self.MIN_CACHED_CHARS)
        self.assertGreater(len(SYNTHESIS_PROMPT), self.MIN_CACHED_CHARS)


# ── 5: orchestrator end-to-end with mocked agent_call ─────────────────────────

SPECIALIST_CANNED = {
    "fact_checker": {
        "verified_facts": ["Outage lasted 43 minutes."],
        "corrections": [{"claim": "an hour", "reality": "43 minutes"}],
        "unknowns": ["final customer count"],
        "confidence": "high",
    },
    "legal": {
        "risk_level": "medium",
        "liability_flags": ["SLA credits owed"],
        "banned_phrases_found": [],
        "approved_apology_language": ["we're sorry for the disruption"],
    },
    "comms": {
        "key_messages": ["Service restored"],
        "tone_guidance": "warm, direct",
        "statement_skeleton": "apology -> facts -> fix",
        "stakeholders_to_notify": ["Tier-1 customers"],
    },
    "social": {
        "sentiment_summary": "mostly amused",
        "meme_risk": "already-a-meme",
        "tweet_drafts": ["draft tweet one", "draft tweet two", "draft tweet three"],
        "hashtags": [],
        "do_not_engage": ["competitor comparisons"],
    },
}


def fake_agent_call(bus, agent_name, *, output_schema, **kwargs):
    if output_schema is DECOMPOSE_SCHEMA:
        return {
            "issues": [{"id": "outage", "title": "Outage", "severity": "critical"}],
            "specialist_briefs": {
                "fact_checker": "verify",
                "legal": "assess",
                "comms": "draft",
                "social": "read the room",
            },
        }
    if output_schema is PACKAGE_SCHEMA:
        return {
            "press_statement": "We're sorry — we let you down today. " + "detail " * 40,
            "internal_talking_points": ["customers first", "route press to comms@"],
            "tweets": ["tweet one " + "x" * 300, "tweet two"],
        }
    if output_schema is CRITIC_SCHEMA:
        return {
            "verdict": "SHIP_IT",
            "scores": {
                "issues_addressed": "pass",
                "no_liability_admission": "pass",
                "on_brand_tone": "pass",
                "tweets_fit": "pass",
                "job_on_the_line": "pass",
            },
            "required_changes": [],
            "one_liner": "Ship it before the llama gets a book deal.",
        }
    return SPECIALIST_CANNED[agent_name]


class TestRunSwarm(unittest.TestCase):
    def _write_scenario(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = pathlib.Path(tmp.name) / "llama.md"
        path.write_text(
            "# INCIDENT: Llama in us-east-1\n\n`scenario_tag: llama`\n\n"
            "Biscuit took the region down for 43 minutes.\n"
        )
        return path

    def test_end_to_end_event_stream_is_valid(self):
        bus = EventBus(None)
        with mock.patch.object(orchestrator, "agent_call", side_effect=fake_agent_call):
            result = orchestrator.run_swarm(self._write_scenario(), bus, client=object())

        self.assertEqual(validate_events(bus.history), [])
        self.assertEqual(result["status"], "shipped")
        self.assertEqual(len(result["package"]["tweets"]), 3)
        self.assertTrue(all(len(t) <= 280 for t in result["package"]["tweets"]))
        self.assertEqual(result["issues"][0]["id"], "outage")
        self.assertEqual(len(result["verdicts"]), 1)

        types = [e["type"] for e in bus.history]
        self.assertEqual(types[0], "run_started")
        self.assertEqual(types[-1], "run_done")
        self.assertEqual(types.count("agent_started"), 4)
        self.assertEqual(types.count("agent_done"), 4)
        phases = [e["data"]["phase"] for e in bus.history if e["type"] == "phase"]
        self.assertEqual(
            phases, ["decompose", "fanout", "synthesize", "critique", "done"]
        )
        run_started = bus.history[0]
        self.assertEqual(run_started["data"]["mode"], "live")
        self.assertEqual(
            run_started["data"]["scenario_name"], "INCIDENT: Llama in us-east-1"
        )
        run_done = bus.history[-1]
        self.assertEqual(run_done["data"]["status"], "shipped")
        self.assertIn("final_package", run_done["data"])

    def test_revise_cycle_and_specialist_failure_are_recoverable(self):
        bus = EventBus(None)
        critic_calls = {"n": 0}

        def flaky_agent_call(bus_, agent_name, *, output_schema, **kwargs):
            if agent_name == "legal":
                raise RuntimeError("simulated specialist failure")
            if output_schema is CRITIC_SCHEMA:
                critic_calls["n"] += 1
                verdict = "REVISE" if critic_calls["n"] == 1 else "SHIP_IT"
                return {
                    "verdict": verdict,
                    "scores": {
                        "issues_addressed": "fail" if verdict == "REVISE" else "pass",
                        "no_liability_admission": "pass",
                        "on_brand_tone": "pass",
                        "tweets_fit": "pass",
                        "job_on_the_line": "pass",
                    },
                    "required_changes": ["address the badge gate"] if verdict == "REVISE" else [],
                    "one_liner": "quip",
                }
            return fake_agent_call(bus_, agent_name, output_schema=output_schema, **kwargs)

        with mock.patch.object(orchestrator, "agent_call", side_effect=flaky_agent_call):
            result = orchestrator.run_swarm(self._write_scenario(), bus, client=object())

        self.assertEqual(validate_events(bus.history), [])
        self.assertEqual(result["status"], "shipped")
        types = [e["type"] for e in bus.history]
        self.assertEqual(types.count("error"), 1)  # legal failed, run survived
        self.assertEqual(types.count("agent_done"), 3)
        self.assertEqual(types.count("critic_verdict"), 2)
        phases = [e["data"]["phase"] for e in bus.history if e["type"] == "phase"]
        self.assertIn("revise", phases)
        cycles = [e["data"]["cycle"] for e in bus.history if e["type"] == "critic_verdict"]
        self.assertEqual(cycles, [1, 2])


if __name__ == "__main__":
    unittest.main()
