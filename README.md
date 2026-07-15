# The Hardest Part is saying you're sorry

A crisis-response specialist swarm that writes the corporate apology so you don't have to.

Lumina Cloud has a problem. Specifically: Biscuit, the CEO's emotional-support llama, just breached the badge gate at the Ashburn datacenter, dislodged a cable tray, and took us-east-1 down for 43 minutes — and a staff engineer's livestream of the pursuit is at 2.1M views and climbing. This is absurd, and it is also exactly the shape of a real incident: multiple distinct problems (an SLA breach, a physical-security failure, a viral-optics fire) that need fact-checking, legal review, message strategy, and social response *simultaneously*, under time pressure, without anyone accidentally admitting negligence in a tweet. Drop the crisis brief in; a Coordinator decomposes it into issues, fans out four specialists in parallel — each with its own playbook and three tools over synthetic company data — synthesizes a full statement package, and a Critic agent playing Head of PR stamps it SHIP IT or sends it back. You watch the whole thing happen live on a dashboard with a running cost odometer. Built for Track 03 (Specialist Swarm) at the Anthropic Basecamp Agent Build Hackathon, on the plain Anthropic Messages API. No frameworks were harmed.

## Architecture

```
                    scenarios/*.md  (the crisis brief)
                              │
                              ▼
                     ┌─────────────────┐
                     │   COORDINATOR   │  claude-sonnet-4-6
                     │    decompose    │  → issues + 4 specialist briefs
                     └────────┬────────┘
            ┌──────────┬──────┴─────┬───────────┐
            ▼          ▼            ▼           ▼        all four in parallel
      ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐
      │ 🔍 Fact-  │ │ ⚖️ Legal │ │ 📣 Comms  │ │ 📱 Social │
      │  Checker │ │   Risk  │ │ Strategy │ │  Media   │
      └────┬─────┘ └────┬────┘ └────┬─────┘ └────┬─────┘
        3 tools      3 tools     3 tools      3 tools     ← synthetic data/
            └──────────┴──────┬─────┴───────────┘
                              ▼
                     ┌─────────────────┐
                     │   COORDINATOR   │  press statement + internal
                     │    synthesize   │  talking points + 3 tweets ≤280
                     └────────┬────────┘
                              ▼
                     ┌─────────────────┐    REVISE ✏️
                     │  CRITIC (Haiku) │ ───────────────┐
                     │  "Head of PR"   │ ◄──(≤2 cycles)─┘
                     └────────┬────────┘
                              ▼ SHIP IT ✅
                      statement package

  every step emits onto THE EVENT BUS ──┬──► SSE → live dashboard (stdlib, one HTML file)
                                        ├──► runs/*.jsonl → --replay (demo failsafe)
                                        └──► eval harness graders
```

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # then paste your ANTHROPIC_API_KEY (sk-ant-...)

# Live run — starts the dashboard, opens the SSE stream, runs the swarm
.venv/bin/python demo.py scenarios/llama.md

# Replay a recorded run through the identical pipeline (no API key needed)
.venv/bin/python demo.py --replay replay/llama_golden.jsonl

# Evals: N runs × 8 scenarios × ~9 criteria → HTML report
.venv/bin/python evals/run_evals.py --runs 3
```

One dependency: `anthropic`. The dashboard server, SSE, event bus, and replay engine are all Python stdlib.

## The 8 scenarios

Every crisis is a markdown brief in `scenarios/` — an H1 title, a `scenario_tag:` line, and a paragraph of escalating corporate misfortune.

| Scenario | The situation |
|---|---|
| `llama` | Biscuit the emotional-support llama breaches the Ashburn badge gate; us-east-1 down 43 minutes; pursuit livestream at 2.1M views. |
| `ai_intern` | The AI support intern replied "lol no" to 4,000 enterprise tickets. |
| `kombucha` | An office kombucha situation escalates into a building evacuation. |
| `superbowl` | The Super Bowl ad ships with a typo that renders the rival's logo. |
| `mctestface` | Customer "Test McTestface" is migrated to production. With consequences. |
| `hotmic` | The CEO, on a hot mic, describes a customer-impacting failure as "a rounding error with a logo." |
| `luminacoin` | The 2021 LuminaCoin blog post resurfaces. Nobody remembers approving it. |
| `drone` | A delivery drone delivers 400 t-shirts to a courthouse. |

Same pipeline, same specialists, eight very different apologies.

## How it works

**One event contract, one code path.** Everything the swarm does is an event — `run_started`, `issues_identified`, `agent_tool_use`, `synthesis_delta`, `critic_verdict`, `run_done`, fourteen types total, frozen in `swarm/events.py`. Live mode: the orchestrator emits onto a thread-safe bus that fans out to a JSONL file and SSE subscriber queues. Replay mode: the JSONL is re-emitted through the same bus with original pacing (gaps compressed to 3s so a slow run replays snappily). The dashboard cannot tell the difference; that is the point.

**Decompose → delegate → synthesize.** The Coordinator (Sonnet) reads the brief and produces structured output: a list of issues with severities, plus a tailored one-line brief for each specialist. The four specialists run in parallel threads, each with a bounded tool loop (max 4 tool turns) over its own three tools — the Fact-Checker searches past incidents and pulls timelines, Legal scans drafts against the banned-phrase list, Comms fetches brand voice and statement templates, Social reads the mentions feed and counts tweet characters. The Coordinator then synthesizes their structured outputs into the package.

**Structured outputs everywhere.** Every agent's final answer is schema-constrained JSON (`swarm/schemas.py`) — issue lists, liability flags, tweet drafts, the final package, the critic's verdict. The one place JSON Schema can't help (it has no working `maxLength` in structured outputs) the 280-character tweet limit is enforced by prompt, code, and an eval grader instead. Belt, suspenders, grader.

**The critic loop is bounded.** The Critic (Haiku, in character as a Head of PR who has seen things) scores the package against a five-point rubric — issues addressed, no liability admission, on-brand tone, tweets fit, and the load-bearing `job_on_the_line` — then stamps `SHIP_IT` or `REVISE` with required changes and one snarky quip. Maximum two revision cycles; after that the run ships `shipped_with_reservations`, because in a real crisis the deadline also gets a vote.

**Prompt caching keeps it cheap.** Each agent's system prefix (playbook + company context, padded past the cache-minimum) is cached, so specialists' repeated tool-loop turns bill cache reads at 0.10x input rate instead of full freight. A cost odometer on the dashboard tracks it live per call; a full run lands around $0.15–0.40.

## Evals

We didn't just build it, we measured it. `evals/run_evals.py` runs the full pipeline N times across all 8 scenarios and grades each final package against ~9 criteria: rule-based graders where rules suffice (no banned liability phrases, every tweet ≤280 characters, all issues mentioned) and Haiku LLM-judges where judgment is required (tone, sincerity-without-admission, would-a-journalist-mock-this). Output is `evals/results.json` and a rendered `evals/eval_report.html`.

<!-- EVAL_RESULTS -->
*Results table lands here after the eval run; `results.json` and `eval_report.html` are committed alongside it.*

## Design decisions

**Why local, not managed agents.** The demo *is* the orchestration: we want the room to watch decomposition, parallel fan-out, tool calls, and the critic loop as they happen, over an event stream we fully control. Owning the loop with the plain Messages API means one frozen event contract, byte-for-byte replayability, an honest cost model, and zero framework between the judges and what we actually built. Managed agents optimize away exactly the parts we're showing off.

**Why the critic.** First drafts of apologies are reliably bad in ways an author can't see — ours apologized for the outage and ghosted the llama-shaped hole in our physical security. A separate cheap model with a hostile rubric catches that. And when it fires on stage, it's not a failure state, it's the product working: the swarm noticing its own apology isn't good enough and fixing it, for about a tenth of a cent of Haiku.

**Tool errors teach.** `execute_tool` never raises. Unknown tool? The error names the available tools. Bad arguments? The error says which. No matching fact? The datastore returns the list of topics that *do* exist. A raw exception is a dead-end turn for an agent; an instructive string is a course correction, and the next tool call is usually right.

---

**The Hardest Part** — Basecamp 2026. The hardest part is saying you're sorry.
