#!/usr/bin/env python3
"""The Hardest Part — crisis-response swarm demo launcher.

    python demo.py scenarios/llama.md                     # live run
    python demo.py --replay replay/llama_golden.jsonl     # canned run
    python demo.py scenarios/llama.md --port 8787 --no-browser --speed 1.5

Live mode needs ANTHROPIC_API_KEY (shell env or .env); without one it falls
back to the recorded golden run so the demo never dies on stage.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dashboard.server import start_dashboard  # noqa: E402
from swarm.events import EventBus, replay_run  # noqa: E402

GOLDEN = ROOT / "replay" / "llama_golden.jsonl"
SAMPLE = ROOT / "replay" / "sample_dev.jsonl"

NO_KEY_NOTICE = """
============================================================
  🔑  No ANTHROPIC_API_KEY found (shell env or .env file).
      Live mode needs one — but the show must go on:
      switching to the recorded replay instead.

      To go live:  cp .env.example .env  and add your key.
============================================================
"""


def _fallback_replay_path() -> pathlib.Path:
    return GOLDEN if GOLDEN.is_file() else SAMPLE


def _print_summary(bus: EventBus) -> None:
    done = next((e for e in reversed(bus.history) if e["type"] == "run_done"), None)
    if done:
        d = done["data"]
        print(
            f"\n✅ Run finished — status: {d.get('status')} | "
            f"cost: ${d.get('total_cost', 0):.4f} | "
            f"elapsed: {d.get('elapsed_s', 0):.1f}s"
        )
    else:
        print("\n⚠️  Run ended without a run_done event.")


def _serve_until_interrupt(server, bus: EventBus) -> None:
    print("Press Ctrl+C to stop the server")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down. The hardest part is saying goodbye.")
    finally:
        bus.close()
        server.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the crisis-response swarm demo.")
    parser.add_argument("scenario", nargs="?", help="path to a scenario .md file (live mode)")
    parser.add_argument("--replay", metavar="JSONL", help="replay a recorded run instead of going live")
    parser.add_argument("--port", type=int, default=8787, help="dashboard port (default 8787)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the dashboard in a browser")
    parser.add_argument("--speed", type=float, default=1.0, help="replay speed multiplier (default 1.0)")
    args = parser.parse_args()

    replay_path: pathlib.Path | None = pathlib.Path(args.replay) if args.replay else None
    scenario: pathlib.Path | None = pathlib.Path(args.scenario) if args.scenario else None

    if replay_path is None and scenario is None:
        print("\nNo scenario given (e.g. scenarios/llama.md) — falling back to the recorded replay.\n")
        replay_path = _fallback_replay_path()

    if replay_path is None:
        # Live mode requested — but only if we actually have a key.
        # config imports the anthropic SDK, so keep this import lazy too.
        from swarm.config import load_api_key

        if not load_api_key():
            print(NO_KEY_NOTICE)
            replay_path = _fallback_replay_path()
            print(f"→ replaying {replay_path.relative_to(ROOT)}\n")

    url = f"http://localhost:{args.port}/"

    if replay_path is not None:
        # ---- replay mode (works even while the swarm itself is mid-build) ----
        if not replay_path.is_file():
            sys.exit(f"error: replay file not found: {replay_path}")
        bus = EventBus(run_path=None)
        server = start_dashboard(bus, port=args.port)
        print(f"🎬 Dashboard on {url} — replaying {replay_path} at {args.speed}x")
        if not args.no_browser:
            webbrowser.open(url)
        time.sleep(2)  # grace: let the browser connect before events fly
        replay_run(replay_path, bus, speed=args.speed)
        _print_summary(bus)
        _serve_until_interrupt(server, bus)
        return

    # ---- live mode ----
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_path = ROOT / "runs" / f"{scenario.stem}-{stamp}.jsonl"
    bus = EventBus(run_path=run_path)
    server = start_dashboard(bus, port=args.port)
    print(f"🚨 Dashboard on {url} — live run of {scenario} (recording to {run_path})")
    if not args.no_browser:
        webbrowser.open(url)
    time.sleep(2)  # grace: let the browser connect before events fly

    try:
        # Lazy import: replay mode must keep working even if swarm deps are mid-build.
        from swarm.orchestrator import run_swarm

        run_swarm(str(scenario), bus)
    except Exception as exc:  # noqa: BLE001 - demo must never die silently
        bus.emit("error", agent=None, message=f"{type(exc).__name__}: {exc}", recoverable=False)
        print(f"\n💥 Live run failed: {exc}")
        print(f"   Partial recording saved. Replay it with:\n"
              f"   python demo.py --replay {run_path}")

    _print_summary(bus)
    _serve_until_interrupt(server, bus)


if __name__ == "__main__":
    main()
