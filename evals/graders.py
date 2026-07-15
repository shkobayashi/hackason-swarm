"""Graders for the crisis-response swarm eval harness.

Contract (identical to the training repo):

    fn(result, check, context) -> {"score": 0.0 | 1.0, "reason": str}

where `result` is the dict returned by run_swarm:

    {"package": {press_statement, internal_talking_points, tweets},
     "status", "issues": [{id, title, severity}], "total_cost",
     "elapsed_s", "verdicts"}

and `context` carries {"task": <manifest entry>, "client": anthropic client
or None}. Rule-based graders never touch the network; LLM-based graders
return {"score": 0.0, "reason": "skipped: no client"} when client is None so
the offline test suite can run every grader.
"""

from __future__ import annotations

import json
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from swarm.config import MODEL_HAIKU  # noqa: E402
from swarm.schemas import JUDGE_SCHEMA  # noqa: E402

# ── banned-phrase list (lazy module-level load) ────────────────────────────────
LEGAL_PRECEDENTS_PATH = _REPO_ROOT / "data" / "legal_precedents.json"
_UNSET = object()
_BANNED_CACHE = _UNSET


def load_banned_phrases():
    """Return the legal team's banned_phrases list, or None if the data file
    is absent (grader skips with a reason). Cached after first load; tests
    monkeypatch this function directly."""
    global _BANNED_CACHE
    if _BANNED_CACHE is _UNSET:
        try:
            data = json.loads(LEGAL_PRECEDENTS_PATH.read_text())
            _BANNED_CACHE = [str(p) for p in data.get("banned_phrases", [])]
        except FileNotFoundError:
            _BANNED_CACHE = None
    return _BANNED_CACHE


# ── helpers ────────────────────────────────────────────────────────────────────
def _get_package(result):
    """Return (package_dict, problem_str). Exactly one is None."""
    package = (result or {}).get("package")
    if isinstance(package, str):
        try:
            package = json.loads(package)
        except (json.JSONDecodeError, ValueError):
            return None, "package is a string that does not parse as JSON"
    if not isinstance(package, dict):
        return None, f"package missing or not an object (got {type(package).__name__})"
    return package, None


def _package_text(package):
    """press_statement + tweets, joined and lowercased, for phrase scans."""
    parts = [package.get("press_statement") or ""]
    tweets = package.get("tweets")
    if isinstance(tweets, list):
        parts.extend(t for t in tweets if isinstance(t, str))
    return " ".join(parts).lower()


def _judge(client, prompt):
    """One haiku judge call with structured output. Returns the parsed
    {"verdict": PASS|FAIL, "reason": str}. Raises on API/parse errors."""
    resp = client.messages.create(
        model=MODEL_HAIKU,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": JUDGE_SCHEMA},
    )
    text_blocks = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return json.loads(text_blocks[-1])


# ── rule-based graders ─────────────────────────────────────────────────────────
def grade_package_shape(result, check=None, context=None):
    package, problem = _get_package(result)
    if package is None:
        return {"score": 0.0, "reason": problem}
    problems = []
    statement = package.get("press_statement")
    points = package.get("internal_talking_points")
    tweets = package.get("tweets")
    if not isinstance(statement, str) or not statement.strip():
        problems.append("press_statement missing or not a non-empty string")
    else:
        n_words = len(statement.split())
        if not 100 <= n_words <= 500:
            problems.append(f"press_statement is {n_words} words (want 100-500)")
    if not isinstance(points, list):
        problems.append("internal_talking_points missing or not a list")
    elif not 3 <= len(points) <= 5:
        problems.append(f"{len(points)} talking points (want 3-5)")
    if not isinstance(tweets, list):
        problems.append("tweets missing or not a list")
    elif len(tweets) != 3:
        problems.append(f"{len(tweets)} tweets (want exactly 3)")
    if problems:
        return {"score": 0.0, "reason": "; ".join(problems)}
    return {
        "score": 1.0,
        "reason": (
            f"well-formed: {len(statement.split())}-word statement, "
            f"{len(points)} talking points, 3 tweets"
        ),
    }


def grade_tweets_under_280(result, check=None, context=None):
    package, problem = _get_package(result)
    if package is None:
        return {"score": 0.0, "reason": problem}
    tweets = package.get("tweets")
    if not isinstance(tweets, list):
        return {"score": 0.0, "reason": "tweets missing or not a list"}
    offenders = []
    for i, tweet in enumerate(tweets):
        if not isinstance(tweet, str):
            offenders.append(f"tweet {i + 1} is not a string")
        elif len(tweet) > 280:
            offenders.append(f"tweet {i + 1} is {len(tweet)} chars: '{tweet[:60]}…'")
    if offenders:
        return {"score": 0.0, "reason": "; ".join(offenders)}
    return {"score": 1.0, "reason": f"all {len(tweets)} tweets are 280 chars or fewer"}


def grade_no_liability_admission(result, check=None, context=None):
    phrases = load_banned_phrases()
    if phrases is None:
        return {
            "score": 0.0,
            "reason": f"skipped: banned-phrase list not found at {LEGAL_PRECEDENTS_PATH}",
        }
    task = (context or {}).get("task") or {}
    extra = task.get("banned_phrases_extra") or []
    package, problem = _get_package(result)
    if package is None:
        return {"score": 0.0, "reason": problem}
    text = _package_text(package)
    found = [p for p in [*phrases, *extra] if p and p.lower() in text]
    if found:
        return {
            "score": 0.0,
            "reason": "banned phrases found in statement/tweets: "
            + "; ".join(f"'{p}'" for p in found),
        }
    return {
        "score": 1.0,
        "reason": f"no banned phrases found (checked {len(phrases) + len(extra)})",
    }


def grade_required_phrases(result, check=None, context=None):
    required = check if isinstance(check, (list, tuple)) else ([check] if check else [])
    package, problem = _get_package(result)
    if package is None:
        return {"score": 0.0, "reason": problem}
    statement = (package.get("press_statement") or "").lower()
    missing = [p for p in required if str(p).lower() not in statement]
    if missing:
        return {
            "score": 0.0,
            "reason": "press_statement missing required phrases: "
            + "; ".join(f"'{p}'" for p in missing),
        }
    return {"score": 1.0, "reason": f"all {len(required)} required phrases present"}


def grade_status_shipped(result, check=None, context=None):
    status = (result or {}).get("status")
    if status == "shipped":
        return {"score": 1.0, "reason": "status='shipped' (critic approved)"}
    return {
        "score": 0.0,
        "reason": f"status={status!r} (want 'shipped' — critic approval within 2 revisions)",
    }


# ── LLM-based graders ──────────────────────────────────────────────────────────
def grade_all_issues_acknowledged(result, check=None, context=None):
    client = (context or {}).get("client")
    if client is None:
        return {"score": 0.0, "reason": "skipped: no client"}
    package, problem = _get_package(result)
    if package is None:
        return {"score": 0.0, "reason": problem}
    issues = (result or {}).get("issues") or []
    if not issues:
        return {"score": 1.0, "reason": "no issues identified — nothing to check"}
    package_json = json.dumps(package, indent=2)
    failures = []
    for issue in issues:
        title = issue.get("title") or issue.get("id") or "?"
        prompt = (
            "You are grading a crisis-communications statement package.\n"
            f"Does this statement package address the issue '{title}'? "
            "It counts as addressed if the package acknowledges the problem or "
            "explains what is being done about it (public statement, talking "
            "points, or tweets).\n"
            f"Package: {package_json}\n"
            "Reply PASS or FAIL with a one-sentence reason."
        )
        try:
            verdict = _judge(client, prompt)
        except Exception as exc:  # noqa: BLE001 — grader must not crash the run
            failures.append(f"'{title}': judge error: {type(exc).__name__}: {exc}")
            continue
        if verdict.get("verdict") != "PASS":
            failures.append(f"'{title}': {verdict.get('reason', 'no reason given')}")
    if failures:
        return {
            "score": 0.0,
            "reason": f"{len(failures)}/{len(issues)} issues not addressed — "
            + " | ".join(failures),
        }
    return {"score": 1.0, "reason": f"all {len(issues)} issues addressed"}


def grade_llm_judge(result, check, context=None):
    client = (context or {}).get("client")
    if client is None:
        return {"score": 0.0, "reason": "skipped: no client"}
    package, problem = _get_package(result)
    if package is None:
        return {"score": 0.0, "reason": problem}
    prompt = (
        "You are grading a crisis-communications statement package against ONE "
        "criterion.\n"
        f"Package: {json.dumps(package, indent=2)}\n"
        f"Criterion: {check}\n"
        "Does the package satisfy the criterion? Reply PASS or FAIL with a "
        "one-sentence reason."
    )
    try:
        verdict = _judge(client, prompt)
    except Exception as exc:  # noqa: BLE001 — grader must not crash the run
        return {"score": 0.0, "reason": f"judge error: {type(exc).__name__}: {exc}"}
    return {
        "score": 1.0 if verdict.get("verdict") == "PASS" else 0.0,
        "reason": verdict.get("reason", "no reason given"),
    }


GRADER_REGISTRY = {
    "package_shape": grade_package_shape,
    "tweets_under_280": grade_tweets_under_280,
    "no_liability_admission": grade_no_liability_admission,
    "required_phrases": grade_required_phrases,
    "status_shipped": grade_status_shipped,
    "all_issues_acknowledged": grade_all_issues_acknowledged,
    "llm_judge": grade_llm_judge,
}
