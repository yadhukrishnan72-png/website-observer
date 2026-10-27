"""Score the detection pipeline against the labelled test set in evaluation/fixtures.py.

Runs the real cleaner, noise rules, analyzer, evidence check and draft check on each case. No network, Slack
or Attio is used. With no ANTHROPIC_API_KEY the analyzer is the keyword stand-in, so the numbers measure
that heuristic, not an AI; set the key and re-run to score Claude.

    python evaluate.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "demo_scripts"))

import generate_demo_sites as sites  # noqa: E402
from evaluation.fixtures import BASES, FIXTURES, NOISE, SIGNAL  # noqa: E402
from observer import analyzer, config, outreach  # noqa: E402
from observer.cleaner import clean, content_hash  # noqa: E402
from observer.differ import diff_blocks  # noqa: E402
from observer.noise_rules import filter_noise  # noqa: E402
from observer.pipeline import _boilerplate_changes  # noqa: E402

COMPANY = "Northwind Analytics"
CONTACT = ("Jordan Lee", "Head of Revenue Operations")
SILENT = {"unchanged", "ignored_rule", "ignored_llm"}


def page_html(page, body, shell_edits=()):
    html = sites.shell(COMPANY, "northwind-analytics", page, page.capitalize(), body)
    for old, new in shell_edits:
        assert old in html, f"shell edit target not found: {old!r}"
        html = html.replace(old, new, 1)
    return html


def run_fixture(f):
    """Returns a dict: outcome (pipeline status), result (analyzer output or None), evidence_ok, draft_ok."""
    old_body = BASES[f["page"]]
    new_body = old_body
    for old, new in f.get("edits", ()):
        assert old in new_body, f"edit target not found: {old!r}"
        new_body = new_body.replace(old, new, 1)
    new_body += f.get("add", "")

    old_blocks, old_bp = clean(page_html(f["page"], old_body))
    new_blocks, new_bp = clean(page_html(f["page"], new_body, f.get("shell_edits", ())))
    out = {"outcome": "unchanged", "result": None, "evidence_ok": None, "draft_ok": None, "note": ""}
    if content_hash(old_blocks) == content_hash(new_blocks) and old_bp == new_bp:
        return out

    added, removed, _ = filter_noise(diff_blocks(old_blocks, new_blocks))
    if not (added or removed):
        out["outcome"] = "ignored_rule"
        return out

    ctx = {"company": COMPANY, "industry": "SaaS", "priority": "High", "page_type": f["page"], "url": "eval",
           "added": added, "removed": removed}
    try:
        result, _ = analyzer.analyze(ctx)
    except Exception as e:                       # provider failure counts against the case
        out.update(outcome="error", note=f"{type(e).__name__}: {e}")
        return out
    error = analyzer.validate(result, ctx)
    out["outcome"], out["note"] = analyzer.route(result, error)
    out["result"] = result
    if result.get("meaningful"):
        out["evidence_ok"] = error is None
    if out["outcome"] == "alert_ready":
        dctx = dict(ctx, contact_name=CONTACT[0], contact_title=CONTACT[1], owner="Yedhu",
                    signal_type=result["signal_type"], change_summary=result["change_summary"],
                    why_it_matters=result["why_it_matters"], outreach_angle=result["outreach_angle"],
                    evidence=result["evidence"])
        try:
            draft, _ = outreach.draft(dctx)
            out["draft_ok"] = outreach.validate(draft, dctx) is None
        except Exception:
            out["draft_ok"] = False
    return out


def pct(n, d):
    return None if d == 0 else 100 * n / d


def main():
    provider = config.llm_provider()
    label = (f"Claude ({config.model_name()})" if provider == "claude"
             else "mock-heuristic stand-in (keyword rules, not AI)")
    print(f"Analyzer: {label}\n")

    rows = [(f, run_fixture(f)) for f in FIXTURES]
    print(f"{'case':26} {'expected':24} {'outcome':13} {'signal found':24} ok")
    for f, r in rows:
        expected = "no alert" if f["kind"] == NOISE else f["expect"]
        found = (r["result"] or {}).get("signal_type") or ""
        good = (r["outcome"] in SILENT) if f["kind"] == NOISE else (r["outcome"] == "alert_ready" and found == f["expect"])
        print(f"{f['id']:26} {expected:24} {r['outcome']:13} {found:24} {'yes' if good else 'NO'}")

    noise = [r for f, r in rows if f["kind"] == NOISE]
    signal = [(f, r) for f, r in rows if f["kind"] == SIGNAL]
    detected = [(f, r) for f, r in signal if r["outcome"] == "alert_ready"]
    meaningful = [r for _, r in rows if r["evidence_ok"] is not None]
    metrics = [
        ("Noise rejection", pct(sum(r["outcome"] in SILENT for r in noise), len(noise)), 100,
         f"{sum(r['outcome'] in SILENT for r in noise)}/{len(noise)} noise cases produced no alert"),
        ("Signal detection", pct(len(detected), len(signal)), 90, f"{len(detected)}/{len(signal)} signals alerted"),
        ("Classification accuracy",
         pct(sum(r["result"]["signal_type"] == f["expect"] for f, r in detected), len(detected)), 85,
         f"{sum(r['result']['signal_type'] == f['expect'] for f, r in detected)}/{len(detected)} detected signals typed correctly"),
        ("Evidence validity", pct(sum(r["evidence_ok"] for r in meaningful), len(meaningful)), 100,
         f"{sum(r['evidence_ok'] for r in meaningful)}/{len(meaningful)} quotes found verbatim in the changed text"),
        ("Draft validity", pct(sum(bool(r["draft_ok"]) for _, r in detected), len(detected)), 100,
         f"{sum(bool(r['draft_ok']) for _, r in detected)}/{len(detected)} drafts passed the draft checks"),
    ]
    print()
    failed = 0
    for name, value, target, detail in metrics:
        ok = value is not None and value >= target
        failed += not ok
        shown = "n/a" if value is None else f"{value:.0f}%"
        print(f"{'PASS' if ok else 'FAIL'}  {name:24} {shown:>5}  (target {target}%)  {detail}")
    if provider != "claude":
        print("\nThese scores measure the keyword stand-in. Set ANTHROPIC_API_KEY and re-run to score Claude.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
