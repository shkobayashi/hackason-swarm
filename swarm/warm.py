"""Pre-demo warmer: compile every structured-output grammar and write every
prompt cache so the first live run on stage is fast.

Structured outputs compile each novel JSON schema into a grammar server-side;
the first call with a new schema can take minutes, then it's cached. Prompt
caches (5-min TTL) also benefit from a warm pass right before the demo.

Usage:  .venv/bin/python -m swarm.warm
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from swarm.config import MODEL_HAIKU, MODEL_SONNET, get_client
from swarm.schemas import (
    CRITIC_SCHEMA,
    DECOMPOSE_SCHEMA,
    JUDGE_SCHEMA,
    PACKAGE_SCHEMA,
    SPECIALIST_SCHEMAS,
)


def _warm_targets():
    from swarm.agents import SPECIALISTS
    from swarm.agents.coordinator import DECOMPOSE_PROMPT, SYNTHESIS_PROMPT
    from swarm.agents.critic import CRITIC_PLAYBOOK

    targets = [
        ("decompose", MODEL_SONNET, DECOMPOSE_PROMPT, DECOMPOSE_SCHEMA, True),
        ("synthesis", MODEL_SONNET, SYNTHESIS_PROMPT, PACKAGE_SCHEMA, True),
        ("critic", MODEL_HAIKU, CRITIC_PLAYBOOK, CRITIC_SCHEMA, False),
        ("judge", MODEL_HAIKU, "You are an eval judge.", JUDGE_SCHEMA, False),
    ]
    for name, spec in SPECIALISTS.items():
        targets.append((name, spec.model, spec.playbook, SPECIALIST_SCHEMAS[name], True))
    return targets


def warm_one(client, name, model, system_text, schema, cache):
    t0 = time.time()
    system_block = {"type": "text", "text": system_text}
    if cache:
        system_block["cache_control"] = {"type": "ephemeral"}
    try:
        response = client.messages.create(
            model=model,
            max_tokens=64,
            system=[system_block],
            output_config={"format": schema},
            messages=[{"role": "user", "content": "Warm-up ping. Emit any minimal valid object."}],
        )
        wrote = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        return f"  {name:<14} ok {time.time() - t0:6.1f}s  cache: +{wrote} written, {read} read"
    except Exception as e:  # noqa: BLE001
        return f"  {name:<14} FAILED after {time.time() - t0:6.1f}s: {type(e).__name__}: {e}"


def main() -> None:
    client = get_client(timeout=600.0)
    targets = _warm_targets()
    print(f"Warming {len(targets)} schema grammars + prompt caches "
          "(first-ever compile can take minutes; reruns are seconds)…")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for line in pool.map(lambda t: warm_one(client, *t), targets):
            print(line)
    print(f"Done in {time.time() - t0:.1f}s. Run the demo within ~5 minutes for hot prompt caches.")


if __name__ == "__main__":
    main()
