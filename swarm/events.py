"""The frozen event contract.

Every run — live or replay — is a stream of events shaped:

    {"seq": int, "ts": float, "t_rel": float, "type": str,
     "agent": str | None, "data": {...}}

Event types and payloads (agent is null unless noted):

    run_started        {run_id, scenario_name, brief_md, mode: "live"|"replay"}
    phase              {phase: decompose|fanout|synthesize|critique|revise|done}
    issues_identified  agent=coordinator {issues: [{id, title, severity}],
                        briefs: {fact_checker, legal, comms, social}}
    agent_started      agent=<specialist> {brief}
    agent_delta        agent=* {text}                (throttled upstream)
    agent_tool_use     agent=<specialist> {tool, input}
    agent_tool_result  agent=<specialist> {tool, summary}
    agent_done         agent=<specialist> {output}   (structured JSON)
    synthesis_delta    agent=coordinator {text}
    synthesis_done     agent=coordinator {package, revision}
    critic_verdict     agent=critic {verdict: SHIP_IT|REVISE, cycle, scores,
                        required_changes, one_liner}
    cost_update        agent=* {input_tokens, output_tokens, cache_read,
                        cache_write, call_cost, total_cost}
    run_done           {status: shipped|shipped_with_reservations|error,
                        total_cost, elapsed_s, final_package}
    error              agent=* {message, recoverable}

Live mode: orchestrator -> bus.emit -> {JSONL file, SSE subscriber queues}.
Replay mode: JSONL -> replay_run -> bus.emit_raw -> SSE subscriber queues.
The dashboard cannot tell the difference; that is the point.
"""

from __future__ import annotations

import json
import pathlib
import queue
import threading
import time

EVENT_TYPES = frozenset(
    {
        "run_started",
        "phase",
        "issues_identified",
        "agent_started",
        "agent_delta",
        "agent_tool_use",
        "agent_tool_result",
        "agent_done",
        "synthesis_delta",
        "synthesis_done",
        "critic_verdict",
        "cost_update",
        "run_done",
        "error",
    }
)


class EventBus:
    """Thread-safe fan-out of run events to a JSONL file and SSE subscribers.

    run_path=None gives a headless bus (evals) that still keeps history.
    """

    def __init__(self, run_path: pathlib.Path | str | None = None):
        self.run_path = pathlib.Path(run_path) if run_path else None
        self.history: list[dict] = []
        self.subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._t0 = time.time()
        self._file = None
        if self.run_path:
            self.run_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.run_path.open("w")

    def emit(self, type: str, agent: str | None = None, **data) -> dict:
        assert type in EVENT_TYPES, f"unknown event type: {type}"
        now = time.time()
        with self._lock:
            self._seq += 1
            event = {
                "seq": self._seq,
                "ts": round(now, 3),
                "t_rel": round(now - self._t0, 3),
                "type": type,
                "agent": agent,
                "data": data,
            }
            self._dispatch(event)
        return event

    def emit_raw(self, event: dict) -> None:
        """Re-emit a pre-built event (replay). Restamps seq to keep dedupe sane."""
        with self._lock:
            self._seq += 1
            event = {**event, "seq": self._seq}
            self._dispatch(event)

    def _dispatch(self, event: dict) -> None:
        self.history.append(event)
        if self._file:
            self._file.write(json.dumps(event) + "\n")
            self._file.flush()
        for q in list(self.subscribers):
            q.put(event)

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None


def load_run(jsonl_path: pathlib.Path | str) -> list[dict]:
    events = []
    for line in pathlib.Path(jsonl_path).read_text().splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def replay_run(
    jsonl_path: pathlib.Path | str,
    bus: EventBus,
    speed: float = 1.0,
    max_gap: float = 3.0,
) -> None:
    """Re-emit a recorded run through the bus with original pacing.

    Gaps are compressed to max_gap seconds so a slow live run replays snappily.
    """
    events = load_run(jsonl_path)
    prev_t = None
    for event in events:
        t = event.get("t_rel", 0.0)
        if prev_t is not None:
            time.sleep(min(max(t - prev_t, 0.0) / max(speed, 0.01), max_gap))
        prev_t = t
        if event.get("type") == "run_started":
            event = {**event, "data": {**event.get("data", {}), "mode": "replay"}}
        bus.emit_raw(event)


def validate_events(events: list[dict]) -> list[str]:
    """Return a list of problems (empty = valid). Used by tests and smoke checks."""
    problems = []
    last_seq = 0
    for i, ev in enumerate(events):
        for field in ("seq", "ts", "t_rel", "type", "data"):
            if field not in ev:
                problems.append(f"event {i}: missing field {field!r}")
        if ev.get("type") not in EVENT_TYPES:
            problems.append(f"event {i}: unknown type {ev.get('type')!r}")
        if not isinstance(ev.get("data"), dict):
            problems.append(f"event {i}: data is not an object")
        seq = ev.get("seq", 0)
        if seq <= last_seq:
            problems.append(f"event {i}: seq {seq} not increasing")
        last_seq = seq
    if events:
        if events[0].get("type") != "run_started":
            problems.append("first event is not run_started")
        if events[-1].get("type") not in ("run_done", "error"):
            problems.append("last event is not run_done/error")
    return problems
