"""Specialist definition. Concrete specialists live in sibling modules and
register themselves in swarm/agents/__init__.py's SPECIALISTS dict."""

from __future__ import annotations

from dataclasses import dataclass, field

from swarm.config import MODEL_SONNET


@dataclass(frozen=True)
class Specialist:
    name: str  # registry key: fact_checker | legal | comms | social
    display_name: str  # e.g. "Fact-Checker"
    emoji: str  # dashboard card icon
    playbook: str  # system-prompt playbook text (cached; pad ≥2,300 tokens combined with company context)
    tool_names: list[str] = field(default_factory=list)
    output_schema: dict = field(default_factory=dict)  # structured-output format dict
    model: str = MODEL_SONNET
    max_tool_turns: int = 4
    max_tokens: int = 1500
