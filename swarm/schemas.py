"""All structured-output schemas — the data contract between agents.

Usage: pass `output_config={"format": SCHEMA}` on the FINAL call only
(never during a tool loop — format constrains all output and silences
tool_use), together with `tool_choice={"type": "none"}`.

Note: json-schema maxLength is not supported by structured outputs, so the
280-char tweet limit is enforced in prompt + code + eval grader, not here.
"""

from __future__ import annotations


def _fmt(schema: dict) -> dict:
    return {"type": "json_schema", "schema": schema}


_STR_ARRAY = {"type": "array", "items": {"type": "string"}}

DECOMPOSE_SCHEMA = _fmt(
    {
        "type": "object",
        "properties": {
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "critical"],
                        },
                    },
                    "required": ["id", "title", "severity"],
                    "additionalProperties": False,
                },
            },
            "specialist_briefs": {
                "type": "object",
                "properties": {
                    "fact_checker": {"type": "string"},
                    "legal": {"type": "string"},
                    "comms": {"type": "string"},
                    "social": {"type": "string"},
                },
                "required": ["fact_checker", "legal", "comms", "social"],
                "additionalProperties": False,
            },
        },
        "required": ["issues", "specialist_briefs"],
        "additionalProperties": False,
    }
)

FACT_CHECKER_SCHEMA = _fmt(
    {
        "type": "object",
        "properties": {
            "verified_facts": _STR_ARRAY,
            "corrections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "reality": {"type": "string"},
                    },
                    "required": ["claim", "reality"],
                    "additionalProperties": False,
                },
            },
            "unknowns": _STR_ARRAY,
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["verified_facts", "corrections", "unknowns", "confidence"],
        "additionalProperties": False,
    }
)

LEGAL_SCHEMA = _fmt(
    {
        "type": "object",
        "properties": {
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high", "call-the-lawyers"],
            },
            "liability_flags": _STR_ARRAY,
            "banned_phrases_found": _STR_ARRAY,
            "approved_apology_language": _STR_ARRAY,
        },
        "required": [
            "risk_level",
            "liability_flags",
            "banned_phrases_found",
            "approved_apology_language",
        ],
        "additionalProperties": False,
    }
)

COMMS_SCHEMA = _fmt(
    {
        "type": "object",
        "properties": {
            "key_messages": _STR_ARRAY,
            "tone_guidance": {"type": "string"},
            "statement_skeleton": {"type": "string"},
            "stakeholders_to_notify": _STR_ARRAY,
        },
        "required": [
            "key_messages",
            "tone_guidance",
            "statement_skeleton",
            "stakeholders_to_notify",
        ],
        "additionalProperties": False,
    }
)

SOCIAL_SCHEMA = _fmt(
    {
        "type": "object",
        "properties": {
            "sentiment_summary": {"type": "string"},
            "meme_risk": {
                "type": "string",
                "enum": ["low", "medium", "already-a-meme"],
            },
            "tweet_drafts": _STR_ARRAY,
            "hashtags": _STR_ARRAY,
            "do_not_engage": _STR_ARRAY,
        },
        "required": [
            "sentiment_summary",
            "meme_risk",
            "tweet_drafts",
            "hashtags",
            "do_not_engage",
        ],
        "additionalProperties": False,
    }
)

PACKAGE_SCHEMA = _fmt(
    {
        "type": "object",
        "properties": {
            "press_statement": {"type": "string"},
            "internal_talking_points": _STR_ARRAY,
            "tweets": {
                "type": "array",
                "items": {
                    "type": "string",
                    "description": "A single tweet, MUST be 280 characters or fewer.",
                },
            },
        },
        "required": ["press_statement", "internal_talking_points", "tweets"],
        "additionalProperties": False,
    }
)

CRITIC_RUBRIC_POINTS = [
    "issues_addressed",
    "no_liability_admission",
    "on_brand_tone",
    "tweets_fit",
    "job_on_the_line",
]

CRITIC_SCHEMA = _fmt(
    {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["SHIP_IT", "REVISE"]},
            "scores": {
                "type": "object",
                "properties": {
                    point: {"type": "string", "enum": ["pass", "fail"]}
                    for point in CRITIC_RUBRIC_POINTS
                },
                "required": CRITIC_RUBRIC_POINTS,
                "additionalProperties": False,
            },
            "required_changes": _STR_ARRAY,
            "one_liner": {
                "type": "string",
                "description": "One snarky-but-professional PR-exec quip about this package.",
            },
        },
        "required": ["verdict", "scores", "required_changes", "one_liner"],
        "additionalProperties": False,
    }
)

JUDGE_SCHEMA = _fmt(
    {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "reason": {"type": "string"},
        },
        "required": ["verdict", "reason"],
        "additionalProperties": False,
    }
)

SPECIALIST_SCHEMAS = {
    "fact_checker": FACT_CHECKER_SCHEMA,
    "legal": LEGAL_SCHEMA,
    "comms": COMMS_SCHEMA,
    "social": SOCIAL_SCHEMA,
}
