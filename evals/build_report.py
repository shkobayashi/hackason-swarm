"""Build evals/eval_report.html from evals/results.json.
The JSON is injected verbatim so every number in the report is the measured one."""

from __future__ import annotations

import argparse
import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = _REPO_ROOT / "evals" / "results.json"
DEFAULT_OUT = _REPO_ROOT / "evals" / "eval_report.html"

HTML = r"""<title>sorry, inc. · swarm eval report</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{
  --bg:#f4f3f6; --surface:#ffffff; --surface-2:#faf9fb; --ink:#211d29; --muted:#6d6676;
  --hair:#e5e2ea; --hair-2:#efedf3; --accent:#0c7b84; --accent-soft:#e2f2f2;
  --plum:#7c4a78; --pass:#1f9d57; --fail:#cf4a5e; --warn:#c07a1e;
  --pass-bg:#e7f6ee; --fail-bg:#fbe9ec; --warn-bg:#fbf1e2;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --serif:Georgia,"Times New Roman",serif;
  --shadow:0 1px 2px rgba(30,20,40,.04),0 4px 16px rgba(30,20,40,.05);
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#141118; --surface:#1d1922; --surface-2:#221d2b; --ink:#ece8f1; --muted:#a49bad;
    --hair:#2f2838; --hair-2:#272130; --accent:#3ec7cf; --accent-soft:#123033;
    --plum:#c79ac2; --pass:#4cd28c; --fail:#f2788a; --warn:#e0a94a;
    --pass-bg:#12291e; --fail-bg:#2c1620; --warn-bg:#2a2012;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.35);
  }
}
:root[data-theme="light"]{
  --bg:#f4f3f6;--surface:#ffffff;--surface-2:#faf9fb;--ink:#211d29;--muted:#6d6676;--hair:#e5e2ea;--hair-2:#efedf3;
  --accent:#0c7b84;--accent-soft:#e2f2f2;--plum:#7c4a78;--pass:#1f9d57;--fail:#cf4a5e;--warn:#c07a1e;
  --pass-bg:#e7f6ee;--fail-bg:#fbe9ec;--warn-bg:#fbf1e2;--shadow:0 1px 2px rgba(30,20,40,.04),0 4px 16px rgba(30,20,40,.05);
}
:root[data-theme="dark"]{
  --bg:#141118;--surface:#1d1922;--surface-2:#221d2b;--ink:#ece8f1;--muted:#a49bad;--hair:#2f2838;--hair-2:#272130;
  --accent:#3ec7cf;--accent-soft:#123033;--plum:#c79ac2;--pass:#4cd28c;--fail:#f2788a;--warn:#e0a94a;
  --pass-bg:#12291e;--fail-bg:#2c1620;--warn-bg:#2a2012;--shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.55;
  -webkit-font-smoothing:antialiased;font-size:16px}
.wrap{max-width:960px;margin:0 auto;padding:0 24px}
h1,h2,h3{text-wrap:balance;margin:0}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.eyebrow{font-family:var(--serif);font-style:italic;color:var(--plum);font-size:15px;letter-spacing:.01em}

/* top bar */
.topbar{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--hair)}
.topbar .row{display:flex;align-items:center;gap:14px;height:56px}
.brand{font-weight:700;letter-spacing:-.01em;font-size:15px;display:flex;align-items:center;gap:9px}
.brand .dot{width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.topbar .spacer{flex:1}
.mini{font-family:var(--mono);font-size:13px;font-weight:600;color:var(--accent)}
.tbtn{border:1px solid var(--hair);background:var(--surface);color:var(--muted);border-radius:8px;
  height:34px;padding:0 12px;font-size:13px;cursor:pointer;font-family:var(--sans)}
.tbtn:hover{color:var(--ink);border-color:var(--accent)}
.tbtn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* hero */
.hero{padding:56px 0 38px}
.hero h1{font-size:clamp(28px,5vw,44px);font-weight:800;letter-spacing:-.025em;line-height:1.04;margin:14px 0 0}
.hero .stand{color:var(--muted);font-size:18px;max-width:62ch;margin-top:16px}
.scorecard{display:flex;align-items:stretch;gap:0;margin-top:32px;border:1px solid var(--hair);
  border-radius:16px;background:var(--surface);box-shadow:var(--shadow);overflow:hidden;flex-wrap:wrap}
.score{padding:22px 26px;display:flex;flex-direction:column;gap:4px;min-width:140px;flex:1}
.score+.score{border-left:1px solid var(--hair)}
.score .k{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:600}
.score .v{font-family:var(--mono);font-size:40px;font-weight:700;line-height:1;letter-spacing:-.02em}
.score .sub{font-size:12.5px;color:var(--muted)}
.score.big .v{color:var(--accent)}
.score.money .v{color:var(--warn);font-size:32px}
.runmeta{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:18px;color:var(--muted);font-size:13px}
.runmeta b{color:var(--ink);font-weight:600}

/* sections */
section{padding:38px 0;border-top:1px solid var(--hair)}
section h2{font-size:25px;font-weight:750;letter-spacing:-.02em}
section .lede{color:var(--muted);margin-top:8px;max-width:66ch}

/* criterion bars */
.crits{display:flex;flex-direction:column;gap:9px;margin-top:22px}
.crit{display:grid;grid-template-columns:230px 1fr 74px;gap:14px;align-items:center}
@media(max-width:640px){.crit{grid-template-columns:1fr;gap:5px}}
.crit .cname{font-family:var(--mono);font-size:12.5px;color:var(--ink);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.crit .cbar{height:16px;border-radius:6px;background:var(--hair-2);overflow:hidden}
.crit .cfill{height:100%;border-radius:6px;min-width:2px;transition:width .3s}
.cfill.ok{background:var(--pass)} .cfill.mid{background:var(--warn)} .cfill.bad{background:var(--fail)}
.crit .cnum{font-family:var(--mono);font-size:12.5px;color:var(--muted);text-align:right}

/* scenario cards */
.tasks{display:flex;flex-direction:column;gap:10px;margin-top:22px}
.task{border:1px solid var(--hair);border-radius:13px;background:var(--surface);box-shadow:var(--shadow);overflow:hidden}
.task.bad{border-color:color-mix(in srgb,var(--fail) 45%,var(--hair))}
.thead{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;padding:15px 18px;
  cursor:pointer;user-select:none}
.thead:hover{background:var(--surface-2)}
.tname{font-weight:650;font-size:15.5px;letter-spacing:-.01em;display:flex;align-items:center;gap:9px}
.tname .caret{color:var(--muted);transition:transform .18s;font-size:12px}
.task.open .caret{transform:rotate(90deg)}
.tid{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:3px}
.meter{display:flex;align-items:center;gap:10px}
.meter .segs{display:flex;gap:3px}
.seg{width:13px;height:17px;border-radius:3px;background:var(--hair-2)}
.seg.p{background:var(--pass)} .seg.f{background:var(--fail)}
.meter .mlab{font-family:var(--mono);font-size:12px;color:var(--muted)}
.tbody{display:none;border-top:1px solid var(--hair-2)}
.task.open .tbody{display:block}
.runrow{padding:13px 18px;border-bottom:1px solid var(--hair-2)}
.runrow:last-child{border-bottom:none}
.runmetaline{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:baseline;font-size:12.5px;color:var(--muted)}
.runmetaline .rn{font-family:var(--mono);font-weight:700;color:var(--ink)}
.runmetaline .stat.shipped{color:var(--pass)} .runmetaline .stat.err{color:var(--fail)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.chipg{font-family:var(--mono);font-size:11px;font-weight:600;border-radius:6px;padding:3px 8px;cursor:default}
.chipg.p{background:var(--pass-bg);color:var(--pass)}
.chipg.f{background:var(--fail-bg);color:var(--fail)}
.reasons{margin-top:9px;display:flex;flex-direction:column;gap:5px}
.reason{display:flex;gap:8px;font-size:12.5px;align-items:baseline}
.reason .gmark{font-family:var(--mono);font-weight:700;color:var(--fail);flex-shrink:0}
.reason .gtxt{color:var(--muted)} .reason .gtxt b{color:var(--ink);font-weight:600}
.errbox{margin-top:9px;font-family:var(--mono);font-size:11.5px;background:var(--fail-bg);
  color:var(--fail);border-radius:8px;padding:9px 12px;white-space:pre-wrap;max-height:180px;overflow:auto}
.empty{border:1px dashed var(--hair);border-radius:13px;padding:28px;text-align:center;
  color:var(--muted);font-size:14px;margin-top:22px}

footer{border-top:1px solid var(--hair);padding:30px 0 60px;color:var(--muted);font-size:13.5px}
footer code{font-family:var(--mono);background:var(--surface-2);padding:2px 6px;border-radius:5px;font-size:12.5px}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>

<div class="topbar"><div class="wrap row">
  <span class="brand"><span class="dot"></span>sorry, inc. · swarm eval</span>
  <span class="spacer"></span>
  <span class="mini" id="minirate"></span>
  <button class="tbtn" id="theme">◐ theme</button>
</div></div>

<div class="wrap">
  <header class="hero">
    <div class="eyebrow">The Hardest Part is saying you're sorry — eval harness</div>
    <h1>Does the swarm actually apologize well?</h1>
    <p class="stand">Every scenario runs through the full crisis swarm — decompose, fan-out,
      synthesize, critique — and the final package is graded by rule-based checks
      (shape, tweet length, banned liability language, required phrases) plus an
      LLM judge for the things rules can't see.</p>
    <div class="scorecard">
      <div class="score big"><span class="k">Pass rate</span><span class="v" id="sr"></span><span class="sub" id="srsub"></span></div>
      <div class="score"><span class="k">Scenarios</span><span class="v" id="sn"></span><span class="sub" id="snsub"></span></div>
      <div class="score"><span class="k">Runs each</span><span class="v" id="sruns"></span><span class="sub">pass rate, not pass/fail</span></div>
      <div class="score money"><span class="k">Total cost</span><span class="v" id="scost"></span><span class="sub">swarm runs, all scenarios</span></div>
    </div>
    <div class="runmeta" id="runmeta"></div>
  </header>

  <section>
    <h2>Per-criterion pass rates</h2>
    <p class="lede">Each bar is one grader across every run of every scenario. A weak bar
      here points at a swarm behavior to fix — or a grader to distrust.</p>
    <div class="crits" id="crits"></div>
  </section>

  <section>
    <h2>Per-scenario results</h2>
    <p class="lede">One segment per run. Click a scenario to see every run's grades —
      failing graders show their reasons; hover any chip for its full reason.</p>
    <div class="tasks" id="tasks"></div>
  </section>

  <footer>
    <div id="foot"></div>
    <div style="margin-top:10px">Reproduce: <code>.venv/bin/python evals/run_evals.py</code>
      — writes <code>evals/results.json</code>; rebuild this page with
      <code>.venv/bin/python evals/build_report.py</code>.</div>
  </footer>
</div>

<script>
const DATA = __DATA__;

const esc = s => String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const pct = x => (100 * (x || 0)).toFixed(0) + "%";
const S = DATA.summary || {};
const RUNS = Array.isArray(DATA.runs) ? DATA.runs : [];
const TASKS = Array.isArray(DATA.tasks) ? DATA.tasks : [];
const CFG = DATA.config || {};
const nRuns = CFG.num_runs || RUNS.length || 0;
const nTasks = CFG.num_tasks || TASKS.length || 0;
const byCrit = S.by_criterion || {};
const nCrit = Object.keys(byCrit).length
  || ((RUNS[0] && RUNS[0][0] && RUNS[0][0].grades) ? RUNS[0][0].grades.length : 0);

// hero
sr.textContent = pct(S.overall);
minirate.textContent = "pass " + pct(S.overall);
srsub.textContent = `${nRuns} runs × ${nTasks} scenarios × ${nCrit} criteria`;
sn.textContent = nTasks;
snsub.textContent = TASKS.map(t => t.id).slice(0, 3).join(", ") + (nTasks > 3 ? "…" : "");
sruns.textContent = nRuns;
scost.textContent = "$" + (S.total_cost || 0).toFixed(3);
runmeta.innerHTML =
  `<span>manifest <b>${esc(CFG.manifest || "?")}</b></span>` +
  `<span>started <b>${esc((DATA.started_at || "?").slice(0, 19).replace("T", " "))}</b></span>` +
  `<span>wall clock <b>${(S.wall_s || 0).toFixed(1)}s</b></span>` +
  `<span>workers <b>${CFG.max_workers ?? "?"}</b></span>`;

// per-criterion bars
const critRows = Object.entries(byCrit).map(([name, c]) => {
  const rate = c.n ? c.passed / c.n : 0;
  const cls = rate >= 0.8 ? "ok" : rate >= 0.5 ? "mid" : "bad";
  return `<div class="crit"><span class="cname" title="${esc(name)}">${esc(name)}</span>
    <div class="cbar"><div class="cfill ${cls}" style="width:${(100 * rate).toFixed(1)}%"></div></div>
    <span class="cnum">${c.passed}/${c.n}</span></div>`;
});
crits.innerHTML = critRows.join("") ||
  `<div class="empty">No criterion data — run <span class="mono">evals/run_evals.py</span> first.</div>`;

// per-scenario cards
function runHTML(r, i) {
  if (!r) return `<div class="runrow"><div class="runmetaline"><span class="rn">run ${i + 1}</span><span>missing</span></div></div>`;
  const grades = r.grades || [];
  const chips = grades.map(g => {
    const ok = g.score === 1.0;
    const label = g.label || g.type;
    return `<span class="chipg ${ok ? "p" : "f"}" title="${esc(g.reason)}">${ok ? "✓" : "✗"} ${esc(label)}</span>`;
  }).join("");
  const fails = grades.filter(g => g.score !== 1.0).map(g =>
    `<div class="reason"><span class="gmark">✗</span><span class="gtxt"><b>${esc(g.label || g.type)}</b> · ${esc(g.reason)}</span></div>`
  ).join("");
  const statusCls = r.status === "shipped" ? "shipped" : (r.status === "error" ? "err" : "");
  return `<div class="runrow">
    <div class="runmetaline"><span class="rn">run ${i + 1}</span>
      <span class="stat ${statusCls}">${esc(r.status ?? "?")}</span>
      <span>$${(r.cost || 0).toFixed(4)}</span><span>${(r.elapsed_s || 0).toFixed(1)}s</span>
      <span>${r.passed ? "all graders passed" : (grades.filter(g => g.score !== 1.0).length + " failing")}</span></div>
    <div class="chips">${chips}</div>
    ${fails ? `<div class="reasons">${fails}</div>` : ""}
    ${r.error ? `<div class="errbox">${esc(String(r.error).slice(-1200))}</div>` : ""}
  </div>`;
}
function taskHTML(t) {
  const rs = RUNS.map(run => (run || []).find(r => r && r.task_id === t.id) || null);
  const passed = rs.filter(r => r && r.passed).length;
  const segs = rs.map(r => `<span class="seg ${r ? (r.passed ? "p" : "f") : ""}"></span>`).join("");
  return `<div class="task ${passed === 0 && rs.length ? "bad" : ""}">
    <div class="thead" tabindex="0" role="button" aria-expanded="false">
      <div><div class="tname"><span class="caret">▶</span>${esc(t.title || t.id)}</div>
        <div class="tid">${esc(t.id)}${t.scenario_tag ? " · " + esc(t.scenario_tag) : ""}</div></div>
      <div class="meter"><div class="segs">${segs}</div><span class="mlab">${passed}/${rs.length}</span></div>
    </div>
    <div class="tbody">${rs.map(runHTML).join("")}</div>
  </div>`;
}
tasks.innerHTML = TASKS.map(taskHTML).join("") ||
  `<div class="empty">No scenarios in results.json.</div>`;

// expand / collapse
document.querySelectorAll(".task").forEach(el => {
  const head = el.querySelector(".thead");
  const toggle = () => { el.classList.toggle("open"); head.setAttribute("aria-expanded", el.classList.contains("open")); };
  head.addEventListener("click", toggle);
  head.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
});

// footer
foot.innerHTML = `Total judge+swarm cost <b>$${(S.total_cost || 0).toFixed(4)}</b> ·
  generated from <code>evals/results.json</code> (started ${esc(DATA.started_at || "?")})
  by <code>evals/build_report.py</code>.`;

// theme toggle
theme.addEventListener("click", () => {
  const cur = document.documentElement.getAttribute("data-theme");
  const next = cur === "dark" ? "light" : cur === "light" ? "dark"
    : (matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark");
  document.documentElement.setAttribute("data-theme", next);
});
</script>
"""


def build(results_path=DEFAULT_RESULTS, out_path=DEFAULT_OUT) -> pathlib.Path:
    """Inject results.json verbatim into the HTML template and write it."""
    data = pathlib.Path(results_path).read_text()
    out = HTML.replace("__DATA__", data)
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out)
    print(f"wrote {out_path}, {len(out)} bytes")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the swarm eval HTML report.")
    ap.add_argument("--results", default=str(DEFAULT_RESULTS),
                    help=f"results JSON path (default {DEFAULT_RESULTS})")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help=f"output HTML path (default {DEFAULT_OUT})")
    args = ap.parse_args()
    build(results_path=args.results, out_path=args.out)
