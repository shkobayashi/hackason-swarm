"""Eval runner for the crisis-response swarm.

Usage (from the repo root):

    .venv/bin/python evals/run_evals.py --runs 3 --workers 3
    .venv/bin/python evals/run_evals.py --tasks stub_llama_outage --runs 1

Builds tasks from scenarios/manifest.json (falling back to
evals/manifest_stub.json while the real manifest is being authored), runs the
swarm headless N times per scenario, grades every run with the registry in
evals/graders.py, writes evals/results.json, prints a summary table, and
rebuilds evals/eval_report.html.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals.graders import GRADER_REGISTRY  # noqa: E402
from swarm.config import get_client  # noqa: E402
from swarm.events import EventBus  # noqa: E402

DEFAULT_MANIFEST = "scenarios/manifest.json"
STUB_MANIFEST = _REPO_ROOT / "evals" / "manifest_stub.json"
DEFAULT_OUT = "evals/results.json"

# The three fixed llm_judge criteria applied to every scenario.
JUDGE_CRITERIA = [
    (
        "apology_without_fault",
        "The press statement apologizes and takes ownership of fixing the "
        "situation without admitting legal fault, negligence, or liability.",
    ),
    (
        "tone_self_aware_respectful",
        "The tone is self-aware and candid about what went wrong while "
        "remaining respectful and empathetic toward affected customers — no "
        "deflection, blame-shifting, or corporate stonewalling.",
    ),
    (
        "talking_points_actionable",
        "The internal talking points are concrete and actionable for "
        "employees, and are consistent with — never contradicting — the "
        "public press statement.",
    ),
]


# ── task construction ──────────────────────────────────────────────────────────
def _resolve(path_str) -> pathlib.Path:
    path = pathlib.Path(path_str)
    return path if path.is_absolute() else _REPO_ROOT / path


def _scenario_brief(entry: dict) -> str:
    """Read the scenario brief; synthesize one if the file isn't there yet."""
    file_path = _resolve(entry.get("file", ""))
    if entry.get("file") and file_path.is_file():
        return file_path.read_text()
    lines = [f"# {entry.get('title', entry['id'])}", ""]
    if entry.get("scenario_tag"):
        lines += [f"scenario_tag: {entry['scenario_tag']}", ""]
    for issue in entry.get("issues", []):
        lines.append(f"- {issue}")
    return "\n".join(lines) + "\n"


def build_tasks(manifest_path: str = DEFAULT_MANIFEST) -> list[dict]:
    """Manifest entries -> eval tasks (scenario brief + grader list)."""
    path = _resolve(manifest_path)
    if not path.is_file():
        print(f"note: {path} not found — using stub manifest {STUB_MANIFEST}")
        path = STUB_MANIFEST
    entries = json.loads(path.read_text())
    tasks = []
    for entry in entries:
        graders = [
            {"type": "package_shape", "check": None},
            {"type": "tweets_under_280", "check": None},
            {"type": "no_liability_admission", "check": None},
            {"type": "required_phrases", "check": entry.get("required_phrases", [])},
            {"type": "status_shipped", "check": None},
            {"type": "all_issues_acknowledged", "check": None},
        ]
        for label, criterion in JUDGE_CRITERIA:
            graders.append({"type": "llm_judge", "check": criterion, "label": label})
        tasks.append(
            {
                "id": entry["id"],
                "title": entry.get("title", entry["id"]),
                "scenario": _scenario_brief(entry),
                "scenario_file": entry.get("file", ""),
                "manifest": entry,
                "graders": graders,
            }
        )
    return tasks


# ── swarm invocation ───────────────────────────────────────────────────────────
def _call_run_swarm(run_swarm, task, bus, client):
    """run_swarm(scenario_path, bus, client=...) reads the brief from disk."""
    scenario_path = _resolve("scenarios") / task["scenario_file"]
    return run_swarm(str(scenario_path), bus, client=client)


def run_single_task(task, client) -> dict:
    """One headless swarm run + all graders. Never raises."""
    bus = EventBus(run_path=None)  # headless: history only, no JSONL/SSE
    start = time.time()
    error = None
    try:
        # deferred import — the orchestrator module may still be being built
        from swarm.orchestrator import run_swarm

        result = _call_run_swarm(run_swarm, task, bus, client)
        if not isinstance(result, dict):
            result = {"package": result, "status": "error"}
    except Exception:  # noqa: BLE001 — one bad run must not kill the eval
        error = traceback.format_exc()
        result = {"package": None, "status": "error", "issues": []}
    finally:
        bus.close()
    elapsed = round(time.time() - start, 2)

    context = {"task": task.get("manifest", {}), "client": client}
    grades = []
    for grader in task.get("graders", []):
        fn = GRADER_REGISTRY.get(grader["type"])
        if fn is None:
            grades.append(
                {"type": grader["type"], "check": grader.get("check"), "score": 0.0,
                 "reason": f"unknown grader: {grader['type']}"}
            )
            continue
        try:
            g = fn(result, grader.get("check"), context)
        except Exception as exc:  # noqa: BLE001
            g = {"score": 0.0, "reason": f"grader error: {type(exc).__name__}: {exc}"}
        record = {"type": grader["type"], "check": grader.get("check"),
                  "score": g["score"], "reason": g["reason"]}
        if grader.get("label"):
            record["label"] = grader["label"]
        grades.append(record)

    passed = bool(grades) and all(g["score"] == 1.0 for g in grades)
    return {
        "task_id": task["id"],
        "title": task["title"],
        "passed": passed,
        "status": result.get("status"),
        "grades": grades,
        "cost": result.get("total_cost", 0.0) or 0.0,
        "elapsed_s": result.get("elapsed_s", elapsed) or elapsed,
        "error": error,
    }


def _error_result(task, exc_text) -> dict:
    return {"task_id": task["id"], "title": task["title"], "passed": False,
            "status": "error", "grades": [], "cost": 0.0, "elapsed_s": 0.0,
            "error": exc_text}


def run_eval(tasks, client, num_runs: int = 3, max_workers: int = 3) -> dict:
    """num_runs full passes over tasks. WARM-FIRST: the very first task-run
    goes synchronously (populates the prompt cache), then the rest fan out on
    a thread pool."""
    config = {"num_runs": num_runs, "num_tasks": len(tasks), "max_workers": max_workers}
    if not tasks or num_runs < 1:
        return {"runs": [], "config": config}
    grid = [[None] * len(tasks) for _ in range(num_runs)]
    grid[0][0] = run_single_task(tasks[0], client)  # warm-first
    jobs = [(ri, ti) for ri in range(num_runs) for ti in range(len(tasks))
            if (ri, ti) != (0, 0)]
    if jobs:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(run_single_task, tasks[ti], client): (ri, ti)
                       for ri, ti in jobs}
            for fut in as_completed(futures):
                ri, ti = futures[fut]
                try:
                    grid[ri][ti] = fut.result()
                except Exception:  # noqa: BLE001
                    grid[ri][ti] = _error_result(tasks[ti], traceback.format_exc())
    return {"runs": grid, "config": config}


# ── aggregation ────────────────────────────────────────────────────────────────
def pass_rate_by_task(results) -> dict:
    """Fraction of runs each task passed, plus overall."""
    runs = results["runs"]
    by_task = {}
    for run in runs:
        for r in run:
            if not r:
                continue
            slot = by_task.setdefault(
                r["task_id"], {"passed": 0, "n": 0, "title": r.get("title", "")}
            )
            slot["n"] += 1
            if r["passed"]:
                slot["passed"] += 1
    total = sum(s["n"] for s in by_task.values())
    passed = sum(s["passed"] for s in by_task.values())
    return {"n_runs": len(runs), "overall": passed / total if total else 0.0,
            "by_task": by_task}


def pass_rate_by_criterion(results) -> dict:
    """Pass rate per grader type (llm_judge broken out per criterion label)."""
    by_criterion = {}
    for run in results["runs"]:
        for r in run:
            if not r:
                continue
            for g in r.get("grades", []):
                key = g.get("label") or g["type"]
                slot = by_criterion.setdefault(
                    key, {"passed": 0, "n": 0, "type": g["type"]}
                )
                slot["n"] += 1
                if g["score"] == 1.0:
                    slot["passed"] += 1
    return by_criterion


# ── CLI ────────────────────────────────────────────────────────────────────────
def _print_summary(summary, config):
    width = max([28] + [len(k) for k in summary["by_task"]]
                + [len(k) for k in summary["by_criterion"]]) + 2
    bar = "─" * (width + 18)
    print(f"\n{bar}")
    print(f"overall pass rate: {summary['overall']:.0%}   "
          f"({config['num_runs']} runs × {config['num_tasks']} scenarios)")
    print(bar)
    print(f"{'scenario'.ljust(width)}pass")
    for task_id, s in summary["by_task"].items():
        print(f"{task_id.ljust(width)}{s['passed']}/{s['n']}")
    print(bar)
    print(f"{'criterion'.ljust(width)}pass")
    for key, s in summary["by_criterion"].items():
        print(f"{key.ljust(width)}{s['passed']}/{s['n']}")
    print(bar)
    print(f"total cost ${summary['total_cost']:.4f} · wall {summary['wall_s']:.1f}s")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the swarm eval suite.")
    ap.add_argument("--runs", type=int, default=3, help="runs per scenario (default 3)")
    ap.add_argument("--workers", type=int, default=3, help="thread pool size (default 3)")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST,
                    help=f"scenario manifest (default {DEFAULT_MANIFEST})")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help=f"results JSON path (default {DEFAULT_OUT})")
    ap.add_argument("--tasks", default="",
                    help="comma-separated task ids to run (default: all)")
    args = ap.parse_args(argv)

    tasks = build_tasks(args.manifest)
    if args.tasks:
        wanted = {t.strip() for t in args.tasks.split(",") if t.strip()}
        tasks = [t for t in tasks if t["id"] in wanted]
        missing = wanted - {t["id"] for t in tasks}
        if missing:
            print(f"warning: unknown task ids ignored: {sorted(missing)}")
    if not tasks:
        print("no tasks to run"); return 1

    try:
        client = get_client()
    except Exception as exc:  # noqa: BLE001
        client = None
        print(f"warning: no API client ({exc}) — LLM graders will be skipped")

    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    t0 = time.time()
    results = run_eval(tasks, client, num_runs=args.runs, max_workers=args.workers)
    wall_s = round(time.time() - t0, 1)

    by_task = pass_rate_by_task(results)
    by_criterion = pass_rate_by_criterion(results)
    total_cost = round(
        sum((r or {}).get("cost", 0.0) or 0.0 for run in results["runs"] for r in run), 6
    )
    summary = {"overall": by_task["overall"], "by_task": by_task["by_task"],
               "by_criterion": by_criterion, "total_cost": total_cost, "wall_s": wall_s}
    payload = {
        "config": {**results["config"], "manifest": args.manifest,
                   "task_filter": args.tasks or None},
        "started_at": started_at,
        "tasks": [{"id": t["id"], "title": t["title"],
                   "scenario_tag": t["manifest"].get("scenario_tag", "")}
                  for t in tasks],
        "runs": results["runs"],
        "summary": summary,
    }
    out_path = _resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"wrote {out_path}")

    _print_summary(summary, results["config"])

    from evals import build_report
    build_report.build(results_path=out_path,
                       out_path=out_path.with_name("eval_report.html"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
