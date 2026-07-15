"""Datastore backing every tool in TOOL_SCHEMAS.

Reads data/*.json + data/brand_voice.md per the DATA FILE CONTRACT in
swarm/tools/__init__.py. All functions return plain readable strings.
Empty search results return TEACHING strings (valid topics/ids), and
missing files return a helpful "not present" note — never a bare error.

Tests may override DATA_DIR (module-level) to point at a temp directory.
"""

from __future__ import annotations

import json
import pathlib

DATA_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"

_MEMO: dict[tuple[str, str], object] = {}


def _load(filename: str):
    """Lazy-load and memoize a data file. Returns parsed JSON (or raw text for
    .md), or None if the file does not exist yet (it may be authored later,
    so missing files are NOT memoized)."""
    key = (str(DATA_DIR), filename)
    if key in _MEMO:
        return _MEMO[key]
    path = pathlib.Path(DATA_DIR) / filename
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return None
    data = json.loads(raw) if filename.endswith(".json") else raw
    _MEMO[key] = data
    return data


def _missing(filename: str) -> str:
    return (
        f"datastore file data/{filename} not present yet — proceed using the "
        "scenario brief and note this gap in your report."
    )


def _matches(query: str, *fields) -> bool:
    q = query.lower()
    return any(q in str(f).lower() for f in fields if f is not None)


# ---------------------------------------------------------------- fact_checker

def lookup_company_fact(topic: str) -> str:
    data = _load("company_facts.json")
    if data is None:
        return _missing("company_facts.json")
    hits = []
    for entry in data.get("facts", []):
        if _matches(topic, entry.get("topic"), entry.get("fact")):
            hits.append(f"[{entry.get('topic')}] {entry.get('fact')}")
    for section in ("products", "slas", "execs"):
        for entry in data.get(section, []):
            blob = json.dumps(entry)
            if _matches(topic, blob):
                hits.append(f"[{section}] {blob}")
    company = data.get("company", {})
    if company and _matches(topic, json.dumps(company)):
        hits.append(f"[company] {json.dumps(company)}")
    if hits:
        return "\n".join(hits)
    topics = sorted({e.get("topic", "?") for e in data.get("facts", [])})
    return (
        f"No company fact matches {topic!r}. Valid fact topics: "
        f"{', '.join(topics) if topics else '(none on file)'}. "
        "Also searchable: products, slas, execs, company."
    )


def search_past_incidents(query: str) -> str:
    incidents = _load("past_incidents.json")
    if incidents is None:
        return _missing("past_incidents.json")
    hits = [
        inc
        for inc in incidents
        if _matches(
            query,
            inc.get("id"),
            inc.get("title"),
            inc.get("summary"),
            inc.get("what_we_said"),
            inc.get("resolution"),
        )
    ]
    if hits:
        return "\n\n".join(
            f"{inc.get('id')}: {inc.get('title')}\n"
            f"  summary: {inc.get('summary')}\n"
            f"  what we said then: {inc.get('what_we_said')}\n"
            f"  resolution: {inc.get('resolution')}"
            for inc in hits
        )
    catalog = ", ".join(f"{i.get('id')} ({i.get('title')})" for i in incidents)
    return (
        f"No past incident matches {query!r}. Incidents on file: "
        f"{catalog if catalog else '(none)'}."
    )


def get_incident_timeline(incident_id: str) -> str:
    incidents = _load("past_incidents.json")
    if incidents is None:
        return _missing("past_incidents.json")
    for inc in incidents:
        if str(inc.get("id", "")).lower() == incident_id.strip().lower():
            lines = [f"Timeline for {inc.get('id')}: {inc.get('title')}"]
            lines += [f"  {t.get('t')}: {t.get('event')}" for t in inc.get("timeline", [])]
            return "\n".join(lines)
    valid = ", ".join(str(i.get("id")) for i in incidents)
    return (
        f"No incident with id {incident_id!r}. Valid incident ids: "
        f"{valid if valid else '(none)'}."
    )


# ------------------------------------------------------------------------ legal

def search_precedents(query: str) -> str:
    data = _load("legal_precedents.json")
    if data is None:
        return _missing("legal_precedents.json")
    precedents = data.get("precedents", [])
    hits = [
        p
        for p in precedents
        if _matches(query, p.get("id"), p.get("title"), p.get("summary"), p.get("outcome"))
    ]
    if hits:
        return "\n\n".join(
            f"{p.get('id')}: {p.get('title')}\n"
            f"  summary: {p.get('summary')}\n"
            f"  outcome: {p.get('outcome')}"
            for p in hits
        )
    catalog = ", ".join(f"{p.get('id')} ({p.get('title')})" for p in precedents)
    return (
        f"No precedent matches {query!r}. Precedents on file: "
        f"{catalog if catalog else '(none)'}."
    )


def get_banned_phrases() -> str:
    data = _load("legal_precedents.json")
    if data is None:
        return _missing("legal_precedents.json")
    banned = data.get("banned_phrases", [])
    approved = data.get("approved_apology_language", [])
    return json.dumps(
        {"banned_phrases": banned, "approved_apology_language": approved}, indent=2
    )


def check_liability_language(text: str) -> str:
    data = _load("legal_precedents.json")
    if data is None:
        return _missing("legal_precedents.json")
    lowered = text.lower()
    flagged = [p for p in data.get("banned_phrases", []) if p.lower() in lowered]
    if flagged:
        return (
            "LIABILITY RISK — banned phrases found in draft: "
            + "; ".join(f"{p!r}" for p in flagged)
            + ". Rewrite using the approved apology language."
        )
    return "All clear: no banned liability-admitting phrases found in the draft."


# ------------------------------------------------------------------------ comms

def get_brand_voice() -> str:
    data = _load("brand_voice.md")
    if data is None:
        return _missing("brand_voice.md")
    return data


def get_statement_template(type: str) -> str:  # noqa: A002 — name fixed by tool schema
    data = _load("comms_templates.json")
    if data is None:
        return _missing("comms_templates.json")
    valid = ("press", "internal", "customer_email")
    template = data.get(type)
    if template:
        return str(template)
    return (
        f"No template of type {type!r}. Valid template types: {', '.join(valid)}."
    )


def get_stakeholder_priorities() -> str:
    data = _load("comms_templates.json")
    if data is None:
        return _missing("comms_templates.json")
    priorities = data.get("stakeholder_priorities", [])
    if not priorities:
        return "No stakeholder priorities on file in data/comms_templates.json."
    return "Stakeholders to notify, in order:\n" + "\n".join(
        f"  {i + 1}. {s}" for i, s in enumerate(priorities)
    )


# ----------------------------------------------------------------------- social

def get_recent_mentions(topic: str) -> str:
    data = _load("social_feed.json")
    if data is None:
        return _missing("social_feed.json")
    mentions = data.get("mentions", [])
    hits = [
        m
        for m in mentions
        if _matches(topic, m.get("scenario_tag"), m.get("handle"), m.get("text"))
    ]
    if hits:
        return "\n".join(
            f"{m.get('handle')}: \"{m.get('text')}\" ({m.get('likes', 0)} likes)"
            for m in hits
        )
    tags = sorted({m.get("scenario_tag", "?") for m in mentions})
    return (
        f"No mentions match {topic!r}. Valid scenario tags: "
        f"{', '.join(tags) if tags else '(none)'}."
    )


def get_past_viral_posts() -> str:
    data = _load("social_feed.json")
    if data is None:
        return _missing("social_feed.json")
    posts = data.get("past_viral_posts", [])
    if not posts:
        return "No past viral posts on file in data/social_feed.json."
    return "\n\n".join(
        f"\"{p.get('text')}\" ({p.get('likes', 0)} likes)\n  lesson: {p.get('lesson')}"
        for p in posts
    )


def count_characters(text: str) -> str:
    n = len(text)
    if n <= 280:
        return f"{n} characters — fits the 280-character tweet limit ({280 - n} to spare)."
    return f"{n} characters — OVER the 280-character tweet limit by {n - 280}. Trim it."
