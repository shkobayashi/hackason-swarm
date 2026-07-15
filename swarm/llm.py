"""The one LLM engine every agent routes through.

Phase A (optional): a bounded streaming tool loop — text deltas are throttled
onto the bus, tool_use blocks are dispatched through swarm.tools.execute_tool,
and the full assistant content is appended AS-IS between turns.

Phase B: a non-streaming structured-output call (`output_config={"format": ...}`
+ `tool_choice={"type": "none"}`) whose last text block is parsed as JSON,
with exactly one corrective retry on malformed JSON.

Costs are accumulated in a thread-safe CostTracker and every API response
emits a `cost_update` event.
"""

from __future__ import annotations

import json
import threading
import time

from swarm.config import calculate_cost
from swarm.tools import execute_tool

FINAL_REPORT_PROMPT = "Provide your final structured report as JSON."
RETRY_PROMPT = (
    "That was not valid JSON. Respond again with ONLY the structured report "
    "as a single valid JSON object matching the required schema."
)

# Delta throttling: flush at >=120ms since last flush or >=80 buffered chars.
FLUSH_INTERVAL_S = 0.12
FLUSH_MIN_CHARS = 80


class CostTracker:
    """Thread-safe accumulator of cache-aware API costs across a run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0.0

    def add(self, model: str, usage) -> tuple[float, float]:
        """Record one response's usage; return (call_cost, running_total)."""
        call_cost = calculate_cost(model, usage)
        with self._lock:
            self._total += call_cost
            return call_cost, self._total

    @property
    def total_cost(self) -> float:
        with self._lock:
            return self._total


class _DeltaThrottle:
    """Buffer streamed text and emit it in human-paced chunks."""

    def __init__(self, bus, agent_name: str, event_type: str):
        self.bus = bus
        self.agent_name = agent_name
        self.event_type = event_type
        self._buffer = ""
        self._last_flush = time.monotonic()

    def feed(self, text: str) -> None:
        self._buffer += text
        now = time.monotonic()
        if (
            len(self._buffer) >= FLUSH_MIN_CHARS
            or now - self._last_flush >= FLUSH_INTERVAL_S
        ):
            self.flush()

    def flush(self) -> None:
        if self._buffer:
            self.bus.emit(self.event_type, agent=self.agent_name, text=self._buffer)
            self._buffer = ""
        self._last_flush = time.monotonic()


def _usage_int(usage, field: str) -> int:
    return getattr(usage, field, 0) or 0


def _emit_cost(bus, agent_name: str, model: str, response, cost_tracker: CostTracker) -> None:
    usage = getattr(response, "usage", None)
    call_cost, total_cost = cost_tracker.add(model, usage)
    bus.emit(
        "cost_update",
        agent=agent_name,
        input_tokens=_usage_int(usage, "input_tokens"),
        output_tokens=_usage_int(usage, "output_tokens"),
        cache_read=_usage_int(usage, "cache_read_input_tokens"),
        cache_write=_usage_int(usage, "cache_creation_input_tokens"),
        call_cost=round(call_cost, 6),
        total_cost=round(total_cost, 6),
    )


def _append_user_text(messages: list[dict], text: str) -> None:
    """Append user text, merging into a trailing user message to keep roles alternating."""
    if messages and messages[-1].get("role") == "user":
        content = messages[-1]["content"]
        if isinstance(content, str):
            messages[-1]["content"] = content + "\n\n" + text
        else:
            content.append({"type": "text", "text": text})
    else:
        messages.append({"role": "user", "content": text})


def _last_text_block(response) -> str | None:
    texts = [
        b.text
        for b in getattr(response, "content", [])
        if getattr(b, "type", "") == "text" and getattr(b, "text", "").strip()
    ]
    return texts[-1] if texts else None


def agent_call(
    bus,
    agent_name: str,
    *,
    client,
    model: str,
    system_blocks,
    tools,
    messages,
    output_schema: dict,
    max_tool_turns: int = 4,
    max_tokens: int = 1500,
    delta_event: str = "agent_delta",
    cost_tracker: CostTracker | None = None,
) -> dict:
    """Run an agent: (optional) bounded streaming tool loop, then a structured
    final call. Returns the parsed structured-output dict."""
    if cost_tracker is None:
        cost_tracker = CostTracker()
    messages = list(messages)

    # ---- Phase A: bounded streaming tool loop (no output_config here) ----
    if tools:
        for _turn in range(max_tool_turns):
            throttle = _DeltaThrottle(bus, agent_name, delta_event)
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system_blocks,
                tools=tools,
                messages=messages,
            ) as stream:
                for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if getattr(delta, "type", "") == "text_delta":
                            throttle.feed(delta.text)
                    elif etype == "content_block_stop":
                        throttle.flush()
                response = stream.get_final_message()
            throttle.flush()
            _emit_cost(bus, agent_name, model, response, cost_tracker)

            # Append the assistant content AS-IS (all blocks).
            messages.append({"role": "assistant", "content": response.content})

            if getattr(response, "stop_reason", None) != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if getattr(block, "type", "") != "tool_use":
                    continue
                tool_input = block.input or {}
                bus.emit("agent_tool_use", agent=agent_name, tool=block.name, input=tool_input)
                result = execute_tool(block.name, tool_input)
                bus.emit(
                    "agent_tool_result",
                    agent=agent_name,
                    tool=block.name,
                    summary=result[:200],
                )
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
            messages.append({"role": "user", "content": tool_results})

    # ---- Phase B: structured final call (non-streaming) ----
    _append_user_text(messages, FINAL_REPORT_PROMPT)

    final_kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=messages,
        output_config={"format": output_schema},
    )
    if tools:
        final_kwargs["tools"] = tools
        final_kwargs["tool_choice"] = {"type": "none"}

    for attempt in range(2):
        response = client.messages.create(**final_kwargs)
        _emit_cost(bus, agent_name, model, response, cost_tracker)
        text = _last_text_block(response)
        try:
            if text is None:
                raise json.JSONDecodeError("no text block in response", "", 0)
            return json.loads(text)
        except json.JSONDecodeError:
            if attempt == 1:
                raise
            messages.append({"role": "assistant", "content": text or "(empty)"})
            _append_user_text(messages, RETRY_PROMPT)
            final_kwargs["messages"] = messages
