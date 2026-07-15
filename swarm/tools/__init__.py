"""Tool schemas + dispatch — the contract between agents and the datastore.

DATA FILE CONTRACT (what data/ must provide; datastore.py reads these):

    data/company_facts.json    {"company": {...}, "products": [...], "slas": [...],
                                "execs": [...], "facts": [{"topic": str, "fact": str}]}
    data/past_incidents.json   [{"id": str, "date": str, "title": str, "summary": str,
                                "what_we_said": str, "resolution": str,
                                "timeline": [{"t": str, "event": str}]}]
    data/legal_precedents.json {"precedents": [{"id": str, "title": str, "summary": str,
                                "outcome": str}],
                                "banned_phrases": [str],
                                "approved_apology_language": [str]}
    data/brand_voice.md        markdown: tone rules, vocabulary, never-say list
    data/comms_templates.json  {"press": str, "internal": str, "customer_email": str,
                                "stakeholder_priorities": [str]}
    data/social_feed.json      {"mentions": [{"scenario_tag": str, "handle": str,
                                "text": str, "likes": int}],
                                "past_viral_posts": [{"text": str, "likes": int,
                                "lesson": str}]}

Scenario briefs (scenarios/*.md) start with an H1 title and contain a
`scenario_tag: <tag>` line matching social_feed mentions.
"""

from __future__ import annotations

TOOL_SCHEMAS: dict[str, dict] = {
    "lookup_company_fact": {
        "name": "lookup_company_fact",
        "description": (
            "Look up verified company facts by topic (products, SLAs, executives, "
            "office policies, the llama). Returns matching fact entries, or the "
            "list of available topics if nothing matches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Keyword(s) to search facts for, e.g. 'uptime SLA'.",
                }
            },
            "required": ["topic"],
        },
    },
    "search_past_incidents": {
        "name": "search_past_incidents",
        "description": (
            "Search prior company incidents by keyword. Returns id, title, summary, "
            "what we said publicly then, and how it was resolved. Use this to keep "
            "today's statement consistent with history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword(s) to search for."}
            },
            "required": ["query"],
        },
    },
    "get_incident_timeline": {
        "name": "get_incident_timeline",
        "description": "Get the detailed timeline for one past incident by its id (e.g. 'INC-104').",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string", "description": "Incident id, e.g. 'INC-104'."}
            },
            "required": ["incident_id"],
        },
    },
    "search_precedents": {
        "name": "search_precedents",
        "description": (
            "Search legal precedents and past settlements by keyword. Returns "
            "matching precedents with outcomes; use to gauge liability exposure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword(s) to search for."}
            },
            "required": ["query"],
        },
    },
    "get_banned_phrases": {
        "name": "get_banned_phrases",
        "description": (
            "Return the legal team's banned-phrase list (phrases that admit "
            "liability) plus the approved apology language that is safe to use."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "check_liability_language": {
        "name": "check_liability_language",
        "description": (
            "Scan a draft text for banned liability-admitting phrases. Returns the "
            "flagged phrases found, or an all-clear."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Draft text to scan."}
            },
            "required": ["text"],
        },
    },
    "get_brand_voice": {
        "name": "get_brand_voice",
        "description": "Return the brand voice guide: tone rules, approved vocabulary, never-say list.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "get_statement_template": {
        "name": "get_statement_template",
        "description": "Return the company's skeleton template for a statement type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["press", "internal", "customer_email"],
                    "description": "Which template to fetch.",
                }
            },
            "required": ["type"],
        },
    },
    "get_stakeholder_priorities": {
        "name": "get_stakeholder_priorities",
        "description": "Return the ordered list of stakeholders to notify in a crisis.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "get_recent_mentions": {
        "name": "get_recent_mentions",
        "description": (
            "Get recent social media mentions about a topic/scenario. Returns "
            "handle, text, likes — the internet's current mood about us."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Scenario tag or keyword, e.g. 'llama' or 'outage'.",
                }
            },
            "required": ["topic"],
        },
    },
    "get_past_viral_posts": {
        "name": "get_past_viral_posts",
        "description": "Return the company's past viral posts with the lesson learned from each.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "count_characters": {
        "name": "count_characters",
        "description": "Count characters in a draft tweet. Tweets must be 280 characters or fewer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Draft tweet text."}
            },
            "required": ["text"],
        },
    },
}

# Which tools each specialist gets (3 each — small on purpose).
SPECIALIST_TOOLS: dict[str, list[str]] = {
    "fact_checker": ["lookup_company_fact", "search_past_incidents", "get_incident_timeline"],
    "legal": ["search_precedents", "get_banned_phrases", "check_liability_language"],
    "comms": ["get_brand_voice", "get_statement_template", "get_stakeholder_priorities"],
    "social": ["get_recent_mentions", "get_past_viral_posts", "count_characters"],
}


def tools_for(specialist: str) -> list[dict]:
    return [TOOL_SCHEMAS[name] for name in SPECIALIST_TOOLS[specialist]]


def execute_tool(name: str, input_data: dict) -> str:
    """Dispatch a tool call to the datastore. Errors return teaching strings,
    never raise — a raw exception is a dead-end turn for the agent."""
    from swarm.tools import datastore

    func = getattr(datastore, name, None)
    if func is None:
        return f"Error: unknown tool '{name}'. Available: {', '.join(TOOL_SCHEMAS)}"
    try:
        return str(func(**input_data))
    except TypeError as e:
        return f"Error: bad arguments for {name}: {e}"
    except Exception as e:  # noqa: BLE001 — teach, don't crash
        return f"Error: {type(e).__name__}: {e}"
