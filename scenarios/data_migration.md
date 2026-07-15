# INCIDENT: Migration Script Renamed Every Customer "Test McTestface"

`scenario_tag: migration`

**SITREP — 2026-07-15, 07:58 PT. Severity: HIGH. Billing: halted. A parody account already exists and it's funnier than us.**

Overnight, a **Glowworm** migration job (#88-1407) intended for a staging environment ran against production and renamed customer account display names to **"Test McTestface."** The early Slack numbers say **all 60,000 of our customers** were hit — that figure is already in an exec email, so someone needs to check it against the actual job log and our real customer count before it escapes into a statement.

It gets worse: before anyone noticed, the morning billing run went out. Thousands of **invoices were dispatched addressed to "Test McTestface"** — and enterprise AP departments are publicly refusing to pay invoices addressed to a nonexistent entity (@invoice_irene, 26k likes, and she has a point). Month-end is in two weeks.

There is also a claim circulating internally that **the original account names may be unrecoverable** — "the script may have overwritten source data." If Glowworm's rollback snapshots exist as designed, that claim is wrong and dangerous; if we repeat it publicly and then recover everything, we look incompetent twice. Verify against how Glowworm actually works before anyone says "data loss." And absolutely nobody says "data breach" — no data left the building.

The separable problems:

1. **The restore.** Confirm snapshot integrity, restore real names, publish the completion time.
2. **The invoices.** Corrected invoices to every affected account, fast — we built an invoice review gate after the 2025 decimal incident (INC-105), and customers will ask why it didn't catch this.
3. **Rumor control.** Kill "data loss" and "breach" language with verified facts about what Glowworm rename jobs can and cannot touch.
4. **Glowworm's reputation.** The product's whole pitch is "zero-data-loss migrations." The statement must name Glowworm and defend the guarantee with specifics, not adjectives.

Statement, customer email, and one tweet that acknowledges the parody account without feeding it. Corrected invoices are the headline; the joke name is the hook.
