"""Configuration: API key resolution, client factory, models, pricing.

The .env parser walks up from this file's directory so the key can live in
the repo root regardless of where a script is launched from. Shell env wins
over the file. No python-dotenv dependency.
"""

from __future__ import annotations

import os
import pathlib

import anthropic

MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU = "claude-haiku-4-5"

# $/MTok. Cache writes bill at 1.25x input, cache reads at 0.10x.
PRICING = {
    MODEL_SONNET: {"input": 3.00, "output": 15.00},
    MODEL_HAIKU: {"input": 1.00, "output": 5.00},
}
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10


def _resolve_env_file() -> pathlib.Path | None:
    here = pathlib.Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_api_key() -> str | None:
    """Return a plausible ANTHROPIC_API_KEY from the shell env or nearest .env."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key.startswith("sk-ant-"):
        return key
    env_file = _resolve_env_file()
    if env_file:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY"):
                _, _, value = line.partition("=")
                value = value.strip().strip("'\"")
                if value.startswith("sk-ant-"):
                    os.environ["ANTHROPIC_API_KEY"] = value
                    return value
    return None


def get_client(timeout: float = 300.0) -> anthropic.Anthropic:
    key = load_api_key()
    if not key:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY found. Copy .env.example to .env and add your key, "
            "or run with --replay for the canned demo."
        )
    return anthropic.Anthropic(api_key=key, timeout=timeout)


def calculate_cost(model: str, usage) -> float:
    """Cache-aware cost in dollars for one API response's usage object."""
    rates = PRICING[model]
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    return (
        input_tokens * rates["input"]
        + cache_write * rates["input"] * CACHE_WRITE_MULT
        + cache_read * rates["input"] * CACHE_READ_MULT
        + output_tokens * rates["output"]
    ) / 1e6
