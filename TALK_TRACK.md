# TALK TRACK — 3-minute demo (DRAFT BEATS)

> Draft beats for whoever voices this. Spoken register, not read-aloud-a-README register.
> Stage directions in *[brackets]*. Timings assume the live run takes ~60–90s on stage;
> the sample run clocked ~43s, so there's slack built into beats 3–5.
>
> **Pre-flight:** dashboard already open in a browser tab, terminal ready with the command
> typed but not run, replay command in a second terminal tab (see Fallback below), evals
> report tab pre-loaded. `.env` key verified that morning.

---

## 0:00 — Cold open

*[Stand still. No slides. Just say it.]*

"Hi — we're **The Hardest Part**, and we built the hardest part of every company: apologizing.

Every real corporate crisis is the same nightmare: something absurd happens, it's public, it's getting worse by the minute, and four different departments need to work the problem at once without contradicting each other. So we automated the departments."

## 0:20 — The setup (one breath)

"This is Track 03, a specialist swarm: one coordinator that reads a crisis brief and decomposes it, four specialist agents — fact-checking, legal, comms, social — that run **in parallel**, each with its own playbook and its own tools over company data, and a critic with veto power. Plain Anthropic API, no frameworks. Let me show you."

## 0:35 — START THE LIVE RUN

*[Hit enter on `demo.py scenarios/llama.md`. Switch to the dashboard tab. Narrate what's actually on screen — don't get ahead of it.]*

"Our fictional company is Lumina Cloud, and today's crisis: the CEO's emotional-support llama, Biscuit, got through the badge gate at our Ashburn datacenter and took down us-east-1 for 43 minutes. An engineer livestreamed the pursuit. 2.1 million views.

*[Decomposition chips appear]* — First, the coordinator is decomposing this. Watch: it's not one problem, it's three. An SLA breach — that's critical. A physical security failure — a llama defeated our badge gate. And a viral video. Three issues, four tailored briefs.

*[Four cards light up]* — And now all four specialists spin up **at the same time**. These are genuinely parallel API calls — watch all four cards streaming at once.

*[Point at tool pills as they appear]* — Those pills are tool calls. The fact-checker is searching our past incidents — and it just found something embarrassing: we had a smaller us-east-1 blip in March and promised 'multiple redundant safeguards.' Legal is pulling the banned-phrases list — the things you must never say in an apology. Social is reading the mentions... the top tweet right now is 'a LLAMA took down us-east-1 and honestly? valid.' Forty-eight thousand likes.

*[First card completes]* — First specialist done — structured JSON, not prose. Every agent hands back a schema-validated object, so synthesis never has to parse vibes.

*[Glance at the cost odometer]* — And that counter in the corner is real spend, live, cache-aware. We're at a few cents."

## 1:40 — Synthesis streams

*[Synthesis panel starts streaming the press statement]*

"Now the coordinator takes all four reports and writes the actual package: a press statement, internal talking points, and three tweets under 280 characters. Watch the statement — apology first, then facts, then the fix. It owns the 43 minutes plainly, and — this is the legal agent's fingerprints — it says 'we're sorry for the disruption,' which is approved language, and never 'we were negligent,' which is a lawsuit."

## 2:00 — The critic stamps

*[Critic verdict appears. Two branches — know both cold.]*

**If REVISE** *(lean in — this is the best possible outcome)*:
"And — look at that. **REVISE.** Even our own AI thinks our first apology wasn't good enough — watch it fix itself. The critic is a separate model playing Head of PR, and it caught that we apologized for the outage but never addressed the security failure — two million people watched a llama walk through our badge gate, and silence reads as cover-up. *[revision streams]* There's the fix: an independent security audit, named explicitly. *[SHIP IT appears]* And now it ships. Its sign-off, verbatim: 'Ship it before the llama gets a book deal.'"

**If SHIP IT first try**:
"**SHIP IT**, first pass. The critic is a separate Haiku model playing a Head of PR with a five-point rubric — including one literally called `job_on_the_line`. It has veto power and a two-revision budget, and in our test runs it uses it: our first drafts kept apologizing for the outage while ghosting the security failure. Today the swarm got it right in one."

## 2:30 — The receipts

*[Click 📊 evals — the report tab.]*

"We didn't just build it, we measured it. This is our eval harness: N runs times 8 crisis scenarios times 9 criteria — rule-based graders for the hard rules, like 'no liability admission' and 'every tweet under 280,' and Haiku LLM-judges for the soft ones, like tone. Every scenario, from the AI intern who replied 'lol no' to 4,000 enterprise tickets, to the drone that delivered 400 t-shirts to a courthouse."

## 2:50 — Close

*[Back to the dashboard, final package on screen.]*

"Saying sorry is hard. We automated everything but the sincerity. We're The Hardest Part — thank you."

---

## Timing table

| Clock | On screen | You are saying |
|---|---|---|
| 0:00 | Presenter, no slides (or title card) | Team name joke, the premise |
| 0:20 | Title card / dashboard idle | Track 03, swarm anatomy in one breath |
| 0:35 | Terminal → dashboard; run starts | Introduce Lumina Cloud + the llama |
| 0:45 | Decomposition chips | "Not one problem — three" |
| 0:55 | 4 specialist cards streaming in parallel | Parallel fan-out; point at simultaneity |
| 1:05 | Tool pills firing | Narrate 2–3 juicy tool results (March incident, banned phrases, 48k-likes tweet) |
| 1:25 | First `agent_done` | Structured JSON, cost odometer |
| 1:40 | Synthesis panel streaming | Press statement anatomy; approved-language detail |
| 2:00 | Critic verdict (either branch) | REVISE → "watch it fix itself"; SHIP IT → rubric + veto story |
| 2:20 | SHIP IT ✅ + final package | Read the critic's one-liner verbatim |
| 2:30 | 📊 eval report | "N runs × 8 crises × 9 criteria" |
| 2:50 | Final package | The close |

**Slack management:** if the live run outpaces you, narrate deeper (read a tweet draft aloud — they're funny). If it lags, pull the eval beat earlier and return for the verdict.

---

## Fallback path (wifi dies / API stalls)

**Trigger:** no decomposition chips within ~15 seconds, or any error toast.

**Do:** switch to the second terminal tab and run:

```bash
.venv/bin/python demo.py --replay replay/llama_golden.jsonl
```

**Say, without breaking stride:**

"This is a recording of the run from this morning — same pipeline, same events."

**Why it holds up (say only if useful):** replay pushes the recorded JSONL through the identical event bus into the identical dashboard — the dashboard literally cannot tell the difference, which was a design goal, not a demo hack. Then continue the script from wherever the replay is; every beat from 0:45 onward works unchanged. Do not apologize for the wifi. We are the apology people; we don't do them for free.

---

## Judge Q&A crib sheet

**Q: Why didn't you use managed agents / an agent framework?**
A: The orchestration *is* the demo. Owning the loop on the plain Messages API gave us a frozen 14-event contract, byte-identical replay, parallel fan-out we control, and an honest per-token cost model. A framework would abstract away exactly what we're showing you.

**Q: How does prompt caching help here?**
A: Every agent has a stable system prefix — playbook plus company context, padded past the cache minimum. Specialists make several calls in their tool loops, so from the second call on, that prefix bills at 0.10x the input rate (writes cost 1.25x once). It's most of why a full multi-agent run with revisions lands around $0.15–0.40.

**Q: What does this cost per run?**
A: About $0.15–0.40 depending on tool-call count and revision cycles. Sonnet 4.6 for coordinator and specialists at $3/$15 per MTok, Haiku 4.5 for critic and judges at $1/$5. The dashboard odometer is computed cache-aware from real usage numbers, not estimated.

**Q: Why Haiku for the critic?**
A: Verdict-with-rubric is a classification job, not a generation job — Haiku does it well, fast, and for about a tenth of a cent, which matters because the critic also runs as ~9 judges × 8 scenarios × N runs in evals. And there's a nice adversarial asymmetry: a cheap skeptical model reliably catches omissions an expensive confident model makes.

**Q: What stops prompt injection through the scenario file?**
A: Blast radius first: specialists have read-only tools over local synthetic JSON — no network, no writes, no shell — so the worst injection outcome is a bad draft. Then layers: the brief is user content, not system prompt; every final output is schema-constrained JSON so an agent can't be talked into emitting arbitrary text; the legal tool scans drafts against the banned-phrase list in code; and the critic re-judges the package against the original issues. It's mitigation, not immunity — we'd say that honestly.

**Q: What breaks at scale?**
A: Three things, in order: the in-process event bus (single machine, threads — you'd swap in Redis or NATS for horizontal scale), the coordinator as synthesis bottleneck (fan-out parallelizes but synthesis is serial), and the fixed four-specialist roster — a real system would let the coordinator choose specialists per crisis. The event contract is the part that survives a rewrite; that's why we froze it.

**Q: What happens if the critic never says SHIP IT?**
A: The loop is bounded at two revisions, then the run completes as `shipped_with_reservations` with the critic's outstanding objections attached. Deadlines are real in a crisis; an infinite perfectionism loop is its own incident.

**Q: How do you know it works — beyond one cute demo?**
A: The eval harness: N runs × 8 scenarios × ~9 criteria, mixing deterministic graders (tweet length, banned phrases — no LLM opinions where a regex will do) with Haiku judges for tone and coverage. Committed report in the repo. We also validate every recorded run against the event contract.

**Q: Is the data real?**
A: All synthetic — a fictional company, fabricated incidents, a fake social feed keyed by scenario tag. That's deliberate: it makes runs reproducible, evals fair across scenarios, and the demo safe to project on a wall.

**Q: What was actually hard?**
A: Two things. Making live and replay indistinguishable — one event contract, one dispatch path, no `if replay` in the dashboard — took real design discipline. And the critic: too lenient and it's decorative, too harsh and it loops forever. The `job_on_the_line` rubric point plus a hard two-cycle budget is where we landed. Also, tweets: getting a model to respect 280 characters required prompt, a counting tool, *and* an eval grader. Schema alone can't do it.
