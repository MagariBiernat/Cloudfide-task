#!/usr/bin/env python3
"""Render the sticky PR comment / job summary from pipeline artefacts.

Inputs (all optional except pr.json/decision.json), read from --out-dir:
  pr.json, decision.json, changes.json, agent-status.json, report.json,
  gate.json, verify.json
Outputs: pr-comment.md (starts with a hidden marker used to update the sticky
comment in place) and summary.md (same body, for $GITHUB_STEP_SUMMARY).

Every string that originates from the agent or the PR is treated as untrusted:
HTML is escaped, @-mentions are neutralised, length is capped, and table cells
cannot break the Markdown structure.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

MARKER = "<!-- unit-test-agent:sticky -->"
MAX_CELL = 220
MAX_BODY = 60000


def load(out: Path, name: str):
    try:
        return json.loads((out / name).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def safe(text, limit: int = MAX_CELL) -> str:
    text = "" if text is None else str(text)
    text = html.escape(text, quote=False).replace("@", "@​").replace("|", "\\|")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def code(text) -> str:
    return f"`{safe(text).replace('`', '')}`" if text else "–"


def pct(v) -> str:
    return "–" if v is None else f"{v:.1f}%"


def delta(before, after) -> str:
    if before is None or after is None:
        return ""
    d = after - before
    return f" ({'+' if d >= 0 else ''}{d:.1f})"


ICON = {"passed": "✅", "failed": "❌", "flaky": "⚠️", "error": "❌", "not_run": "–", None: "–"}
DECISION = {"create": "🆕 create", "update": "✏️ update", "skip": "⏭️ skip", "flag_suspected_bug": "🐞 suspected bug"}


def headline(decision, agent, verify, gate, publish_mode) -> str:
    if decision and not decision.get("run_agent"):
        return f"⏭️ **No tests generated** — {safe(decision.get('reason'))}"
    if agent and not agent.get("ran"):
        return f"⚪ **Agent skipped** — {safe(agent.get('reason'))}"
    if gate and not gate.get("accepted"):
        return "⛔ **Patch rejected by the security gate** — nothing was committed"
    status = (verify or {}).get("status")
    if status == "passed":
        action = {"commit": "committed to this branch", "suggest-only": "attached as a patch (suggest-only)",
                  "dry-run": "ready (local dry-run, nothing published)"}.get(publish_mode, publish_mode)
        return f"✅ **Tests generated and verified** — {action}"
    if status == "no_changes":
        return "ℹ️ **Agent decided no test changes are needed**"
    if status == "failed":
        return "❌ **Verification failed** — nothing was committed"
    return f"⚠️ **Pipeline incomplete** — {safe((verify or {}).get('reason') or status)}"


def render(out: Path, publish_mode: str, run_url: str | None) -> str:
    pr = load(out, "pr.json") or {}
    decision = load(out, "decision.json") or {}
    changes = load(out, "changes.json") or {"targets": []}
    agent = load(out, "agent-status.json")
    report = load(out, "report.json") or {}
    gate = load(out, "gate.json")
    verify = load(out, "verify.json") or {}

    lines = [MARKER, "## 🧪 Unit Test Agent", "", headline(decision, agent, verify, gate, publish_mode), ""]
    meta = [f"mode `{safe(pr.get('mode'))}`",
            f"base `{safe(str(pr.get('base_sha', ''))[:10])}` → head `{safe(str(pr.get('head_sha', ''))[:10])}`"]
    if agent and agent.get("ran"):
        cost = agent.get("cost_usd")
        meta.append(f"agent {agent.get('duration_s')}s" + (f", ${cost:.2f}" if isinstance(cost, (int, float)) else "")
                    + (f", {agent.get('turns')} turns" if agent.get("turns") else ""))
    if run_url:
        meta.append(f"[workflow run]({run_url})")
    lines += [" · ".join(meta), ""]

    if report.get("summary"):
        lines += [f"> {safe(report['summary'], 600)}", ""]

    # Per-file decisions: agent report where available, deterministic pre-decision otherwise.
    reported = {f.get("source"): f for f in report.get("files", [])}
    test_results = verify.get("test_files", {})
    rows, skipped = [], []
    for t in changes.get("targets", []):
        if pr.get("mode") == "backfill" and t["path"] not in reported:
            continue
        f = reported.get(t["path"])
        if f:
            tfs = f.get("test_files") or []
            verdicts = []
            for tf in tfs:
                r = test_results.get(tf)
                if r:
                    v = ICON.get(r.get("status"), "⚠️") + f" {r['result'].get('passed', 0)} passed ×{r.get('repeat', 1)}"
                    if r.get("fails_on_base") is True:
                        v += " · fails on base ✔"
                    elif r.get("weak"):
                        v += " · ⚠️ also passes on base"
                    verdicts.append(v)
            agent_claim = ICON.get((f.get("verification") or {}).get("status"))
            rows.append((code(t["path"]), DECISION.get(f.get("decision"), safe(f.get("decision"))), safe(f.get("reason")),
                         "<br>".join(code(x) for x in tfs) or "–",
                         "<br>".join(verdicts) or (f"agent: {agent_claim}" if tfs else "–")))
        elif t["pre_decision"] == "skip":
            skipped.append(f"{code(t['path'])} — {safe(t.get('skip_reason'))}")
        else:
            rows.append((code(t["path"]), "– not analysed", "not reported by the agent", "–", "–"))
    if rows:
        lines += ["| File | Decision | Reason | Test file | Independent verification |",
                  "|---|---|---|---|---|"]
        lines += [f"| {' | '.join(r)} |" for r in rows]
        lines.append("")
    if skipped:
        lines += [f"<details><summary>⏭️ {len(skipped)} file(s) skipped without analysis "
                  "(not production code / outside coverage scope / cosmetic)</summary>", ""]
        lines += [f"- {s}" for s in skipped[:100]]
        lines += ["", "</details>", ""]

    suites = verify.get("suites", {})
    cov = verify.get("coverage", {})
    if suites:
        lines += ["### Test suites & coverage (measured by the pipeline, not by the agent)", "",
                  "| Stack | Before | After | Lines | Branches | Changed lines covered |", "|---|---|---|---|---|---|"]
        for stack, s in suites.items():
            c = cov.get(stack, {})
            b, a = c.get("before") or {}, c.get("after") or {}
            cb = ((c.get("changed_before") or {}).get("totals") or {}).get("pct")
            ca = ((c.get("changed_after") or {}).get("totals") or {}).get("pct")
            lines.append(
                f"| {stack} | {ICON.get(s['before'].get('status'))} {s['before'].get('passed', 0)} passed "
                f"| {ICON.get(s['after'].get('status'))} {s['after'].get('passed', 0)} passed"
                f"{', ' + str(s['after'].get('failed')) + ' failed' if s['after'].get('failed') else ''} "
                f"| {pct(b.get('lines_pct'))} → **{pct(a.get('lines_pct'))}**{delta(b.get('lines_pct'), a.get('lines_pct'))} "
                f"| {pct(b.get('branches_pct'))} → {pct(a.get('branches_pct'))} "
                f"| {pct(cb)} → {pct(ca)} |")
        lines.append("")

    if verify.get("dropped"):
        lines += ["**Dropped (not committed):** " + "; ".join(
            f"{code(d['path'])} — {safe(d['reason'])}" for d in verify["dropped"]), ""]

    bugs = report.get("suspected_bugs") or []
    if bugs:
        lines += ["### 🐞 Suspected bugs (reported, not 'fixed' by weakening tests)", ""]
        lines += [f"- {code(b.get('source'))}: {safe(b.get('description'), 500)}"
                  + (f"<br>evidence: {safe(b.get('evidence'), 500)}" if b.get("evidence") else "") for b in bugs]
        lines.append("")

    if gate and gate.get("problems"):
        lines += ["<details><summary>Security gate findings</summary>", ""]
        lines += [f"- {safe(p, 300)}" for p in gate["problems"][:30]]
        lines += ["", "</details>", ""]

    failures = [(tf, r) for tf, r in test_results.items() if r.get("status") != "passed"]
    if failures:
        lines += ["<details><summary>Failure details</summary>", ""]
        for tf, r in failures:
            for f in r["result"].get("failures", [])[:3]:
                lines += [f"**{code(tf)}** — {safe(f.get('test'))}", "", "```text",
                          html.escape(str(f.get("message", ""))[:1200]).replace("@", "@​"), "```", ""]
        lines += ["</details>", ""]

    extras = []
    if report.get("skills_used"):
        extras.append("skills: " + ", ".join(code(s) for s in report["skills_used"]))
    validation = (agent or {}).get("report_validation") or {}
    if validation and not validation.get("valid", True):
        extras.append(f"⚠️ agent report failed validation ({len(validation.get('errors', []))} error(s))")
    for w in (report.get("warnings") or [])[:5]:
        extras.append(f"⚠️ {safe(w, 300)}")
    if extras:
        lines += ["<sub>" + " · ".join(extras) + "</sub>", ""]
    lines.append("<sub>Generated tests are verified by an independent job: security gate → "
                 "repeated & shuffled runs → fails-on-base check → full suites with coverage. "
                 "Add label <code>test-agent:skip</code> to opt out.</sub>")

    body = "\n".join(lines)
    return body if len(body) <= MAX_BODY else body[:MAX_BODY] + "\n\n…(truncated)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--publish-mode", default="dry-run", choices=["dry-run", "commit", "suggest-only"])
    parser.add_argument("--run-url")
    args = parser.parse_args(argv)
    import os
    body = render(args.out_dir, args.publish_mode, args.run_url or os.environ.get("RUN_URL"))
    (args.out_dir / "pr-comment.md").write_text(body + "\n")
    (args.out_dir / "summary.md").write_text(body.replace(MARKER + "\n", "") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
