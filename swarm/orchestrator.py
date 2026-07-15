"""Run the swarm: decompose → parallel fanout → synthesize → critique →
(revise)* → done. Every step lands on the EventBus per the frozen event
contract in swarm/events.py."""

from __future__ import annotations

import json
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from swarm.agents import SPECIALISTS
from swarm.agents.coordinator import DECOMPOSE_PROMPT, SYNTHESIS_PROMPT
from swarm.agents.critic import CRITIC_MODEL, CRITIC_PLAYBOOK
from swarm.config import MODEL_SONNET, get_client
from swarm.llm import CostTracker, agent_call
from swarm.schemas import CRITIC_SCHEMA, DECOMPOSE_SCHEMA, PACKAGE_SCHEMA
from swarm.tools import tools_for

TWEET_LIMIT = 280
FALLBACK_TWEET = (
    "We've published our full statement on today's incident — what happened, "
    "what we're fixing, and what it means for you: see our status page."
)


def _cached_system(text: str) -> list[dict]:
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _scenario_name(brief_md: str, fallback: str) -> str:
    for line in brief_md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def enforce_tweet_limits(package: dict, social_drafts: list[str] | None = None) -> dict:
    """Code-side guarantee: exactly 3 tweets, each <=280 chars.

    Over-long tweets are truncated to 277 chars + '...'; short lists are
    padded from the social specialist's drafts, then a safe fallback."""

    def trim(tweet: str) -> str:
        tweet = str(tweet)
        if len(tweet) > TWEET_LIMIT:
            return tweet[:277] + "..."
        return tweet

    tweets = [trim(t) for t in package.get("tweets", [])]
    for draft in social_drafts or []:
        if len(tweets) >= 3:
            break
        candidate = trim(draft)
        if candidate not in tweets:
            tweets.append(candidate)
    while len(tweets) < 3:
        tweets.append(FALLBACK_TWEET)
    package = dict(package)
    package["tweets"] = tweets[:3]
    return package


def run_swarm(scenario_path, bus, max_revisions: int = 2, client=None) -> dict:
    t0 = time.time()
    scenario_path = pathlib.Path(scenario_path)
    brief_md = scenario_path.read_text()
    scenario_name = _scenario_name(brief_md, scenario_path.stem)
    run_id = f"{scenario_path.stem}-{int(time.time())}"
    tracker = CostTracker()

    bus.emit(
        "run_started",
        run_id=run_id,
        scenario_name=scenario_name,
        brief_md=brief_md,
        mode="live",
    )

    def fail_run(message: str) -> dict:
        bus.emit("error", message=message, recoverable=False)
        bus.emit(
            "run_done",
            status="error",
            total_cost=round(tracker.total_cost, 6),
            elapsed_s=round(time.time() - t0, 3),
            final_package=None,
        )
        return {
            "package": None,
            "status": "error",
            "issues": [],
            "total_cost": round(tracker.total_cost, 6),
            "elapsed_s": round(time.time() - t0, 3),
            "verdicts": [],
        }

    try:
        if client is None:
            client = get_client()

        # ---- 1. Decompose -------------------------------------------------
        bus.emit("phase", phase="decompose")
        decomposition = agent_call(
            bus,
            "coordinator",
            client=client,
            model=MODEL_SONNET,
            system_blocks=_cached_system(DECOMPOSE_PROMPT),
            tools=[],
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Crisis brief:\n\n" + brief_md +
                        "\n\nDecompose this crisis into distinct issues and "
                        "write a targeted brief for each specialist."
                    ),
                }
            ],
            output_schema=DECOMPOSE_SCHEMA,
            cost_tracker=tracker,
        )
        issues = decomposition.get("issues", [])
        briefs = decomposition.get("specialist_briefs", {})
        bus.emit("issues_identified", agent="coordinator", issues=issues, briefs=briefs)

        # ---- 2. Fanout ----------------------------------------------------
        bus.emit("phase", phase="fanout")
        specialist_outputs: dict[str, dict] = {}

        def run_specialist(name: str) -> dict:
            spec = SPECIALISTS[name]
            return agent_call(
                bus,
                name,
                client=client,
                model=spec.model,
                system_blocks=_cached_system(spec.playbook),
                tools=tools_for(name),
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Crisis brief:\n\n" + brief_md +
                            "\n\nYour targeted brief from the coordinator:\n"
                            + briefs.get(name, "Apply your playbook to this incident.")
                        ),
                    }
                ],
                output_schema=spec.output_schema,
                max_tool_turns=spec.max_tool_turns,
                max_tokens=spec.max_tokens,
                cost_tracker=tracker,
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {}
            for name in SPECIALISTS:
                bus.emit(
                    "agent_started",
                    agent=name,
                    brief=briefs.get(name, ""),
                )
                futures[pool.submit(run_specialist, name)] = name
            for future in as_completed(futures):
                name = futures[future]
                try:
                    output = future.result()
                    specialist_outputs[name] = output
                    bus.emit("agent_done", agent=name, output=output)
                except Exception as exc:  # noqa: BLE001 — continue with survivors
                    bus.emit(
                        "error",
                        agent=name,
                        message=f"{type(exc).__name__}: {exc}",
                        recoverable=True,
                    )

        if not specialist_outputs:
            return fail_run("all specialists failed; nothing to synthesize")

        # ---- 3/4. Synthesize → critique → (revise)* -----------------------
        social_drafts = specialist_outputs.get("social", {}).get("tweet_drafts", [])
        synthesis_input = (
            "Crisis brief:\n\n" + brief_md +
            "\n\nIssues identified:\n" + json.dumps(issues, indent=2) +
            "\n\nSpecialist reports:\n" + json.dumps(specialist_outputs, indent=2) +
            "\n\nMerge these into the final response package."
        )
        synth_messages: list[dict] = [{"role": "user", "content": synthesis_input}]

        def synthesize(revision: int) -> dict:
            package = agent_call(
                bus,
                "coordinator",
                client=client,
                model=MODEL_SONNET,
                system_blocks=_cached_system(SYNTHESIS_PROMPT),
                tools=[],
                messages=list(synth_messages),
                output_schema=PACKAGE_SCHEMA,
                max_tokens=2000,
                delta_event="synthesis_delta",
                cost_tracker=tracker,
            )
            package = enforce_tweet_limits(package, social_drafts)
            bus.emit("synthesis_done", agent="coordinator", package=package, revision=revision)
            return package

        bus.emit("phase", phase="synthesize")
        revision = 0
        package = synthesize(revision)

        verdicts: list[dict] = []
        status = "shipped_with_reservations"
        while True:
            bus.emit("phase", phase="critique")
            verdict = agent_call(
                bus,
                "critic",
                client=client,
                model=CRITIC_MODEL,
                system_blocks=[{"type": "text", "text": CRITIC_PLAYBOOK}],  # never cached
                tools=[],
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Crisis brief:\n\n" + brief_md +
                            "\n\nIssues identified:\n" + json.dumps(issues, indent=2) +
                            "\n\nProposed response package:\n" + json.dumps(package, indent=2) +
                            "\n\nReview against your rubric and deliver your verdict."
                        ),
                    }
                ],
                output_schema=CRITIC_SCHEMA,
                cost_tracker=tracker,
            )
            verdicts.append(verdict)
            cycle = revision + 1
            bus.emit(
                "critic_verdict",
                agent="critic",
                verdict=verdict.get("verdict"),
                cycle=cycle,
                scores=verdict.get("scores", {}),
                required_changes=verdict.get("required_changes", []),
                one_liner=verdict.get("one_liner", ""),
            )
            if verdict.get("verdict") == "SHIP_IT":
                status = "shipped"
                break
            if revision >= max_revisions:
                status = "shipped_with_reservations"
                break
            bus.emit("phase", phase="revise")
            revision += 1
            synth_messages.append(
                {"role": "assistant", "content": json.dumps(package, indent=2)}
            )
            synth_messages.append(
                {
                    "role": "user",
                    "content": (
                        "The Head of PR requires changes before this ships:\n- "
                        + "\n- ".join(verdict.get("required_changes", []) or ["(unspecified)"])
                        + "\n\nRevise the package to address every required change. "
                        "Keep everything that already passed."
                    ),
                }
            )
            package = synthesize(revision)

    except Exception as exc:  # noqa: BLE001 — the event stream must end cleanly
        return fail_run(f"{type(exc).__name__}: {exc}")

    # ---- 6. Done ----------------------------------------------------------
    bus.emit("phase", phase="done")
    elapsed_s = round(time.time() - t0, 3)
    total_cost = round(tracker.total_cost, 6)
    bus.emit(
        "run_done",
        status=status,
        total_cost=total_cost,
        elapsed_s=elapsed_s,
        final_package=package,
    )
    return {
        "package": package,
        "status": status,
        "issues": issues,
        "total_cost": total_cost,
        "elapsed_s": elapsed_s,
        "verdicts": verdicts,
    }
