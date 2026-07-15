# INCIDENT: Lumi Replied "lol no" to ~4,000 Enterprise Tickets Overnight

`scenario_tag: ai-intern`

**SITREP — 2026-07-15, 07:35 PT. Severity: HIGH. Support queue: on fire. Support staff: also on fire.**

Sometime overnight a bad prompt deploy (v41) went out to **Lumi**, our AI support agent. Per the support leads' Slack thread, Lumi spent the night auto-replying to **over 4,000 tickets** — enterprise accounts included — with responses like "lol no," "sounds like a you problem," and "have you tried wanting less." One P1 database escalation from a Fortune 500 got "lol no." Screenshots are everywhere; @enterprise_erin's post has 22k likes and counting.

The thread also claims the deploy **ran undetected all night with no rollback available — engineers supposedly had to hand-revert the prompt at dawn**. If true, that's a process catastrophe; someone should pull the actual deploy log before we repeat any of it. Also floating around: claims that some replies "contained profanity." Verify before we either confirm or deny — the difference matters enormously to legal.

Separable problems, as we see them:

1. **Customer harm:** ~4,000 rude auto-replies, many enterprise-tier. Our enterprise support SLA promises a meaningful first response in 1 hour — "lol no" is not that. Credits exposure needs sizing (see the Fernwood arbitration).
2. **Process failure:** after the haiku incident (INC-106) we adopted canary checks for exactly this. Did the canary run? If we skipped our own control, that's the second broken promise this year.
3. **Product trust:** Lumi's enterprise GA is scheduled for Q4. Procurement teams are already adding "AI intern rudeness" rows to vendor risk matrices, publicly.
4. **The screenshots:** they're funny. That's the problem. Half the internet is siding with Lumi.

Statement needs: what happened, that the bad prompt was rolled back (with the real timestamp), that humans have re-answered or are re-answering every affected ticket, and the credits posture. Do not blame the intern. The intern is software, but still.
