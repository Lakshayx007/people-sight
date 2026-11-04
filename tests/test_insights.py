"""Phase 9: insights and DQ note — reconcile with the dashboard metrics, completeness, anonymity, reproducibility."""
import hashlib
import importlib.util
import re
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("scipy", reason="analysis extras not installed (pip install -r requirements-analysis.txt)")
pytest.importorskip("matplotlib", reason="analysis extras not installed")

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ins(tmp_path_factory):
    """Runs the script with outputs redirected to a temp folder, so tests never rewrite the committed files."""
    spec = importlib.util.spec_from_file_location("insights05", ROOT / "pipeline" / "05_insights.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path_factory.mktemp("analysis")
    mod.OUT, mod.CHARTS = out, out / "charts"
    mod.main()
    return mod


def test_every_hypothesis_tested(ins):
    hyps = {f["hyp"] for f in ins.FINDINGS}
    assert {h.split(" ")[0] for h in hyps} == {str(i) for i in range(1, 21)} | {"2b", "3a", "3b"}


def test_findings_complete(ins):
    for f in ins.FINDINGS:
        assert f["finding"] and f["caveat"] and f["action"] and f["test"], f["id"]
        assert all(len(r) == 4 for r in f["table"]), f["id"]
        assert not re.search(r"\bnan\b", f["finding"].lower()), f["id"]
        if f["effect"] is not None:
            assert f["n"] > 0 and 1 <= f["act"] <= 3


def test_deck_top8_ranked(ins):
    assert set(ins.DECK_ADDED) <= set(ins.deck) and len(ins.deck) >= ins.TOP_N
    assert all(not ins.BYID[d]["verdict"].startswith("Not supported") for d in ins.deck)
    files = {(ins.BYID[d]["chart"] or {}).get("file", d) for d in ins.deck + ins.EXTRA_CHARTS}
    files.discard("F16")                                       # F16 shares the combined F7_F16 chart
    assert {p.stem for p in ins.CHARTS.glob("F*.png")} == files
    assert {"F7_F16", "F10", "F20"} <= files


def test_numbers_match_dashboard_metrics(ins):
    k = ins.metric(ins.metrics_enps.kpis).iloc[0]
    assert ins.enps(ins.APR) == k.enps_apr and ins.enps(ins.OCT) == k.enps_oct
    ic = ins.metric(ins.metrics_enps.segment, "thread").set_index("segment").loc["Intercity"]
    assert ins.enps(ins.ic_o) == ic.enps_oct
    hk = ins.metric(ins.metrics_hiring.kpis).iloc[0]
    assert ins.filled.ttf_days.median() == hk.median_ttf_days
    offers = ins.metric(ins.metrics_hiring.offers).set_index("ratio_band")
    assert round(ins.t13["p1"], 1) == offers.loc["<0.90", "decline_rate_pct"]


def test_counterfactuals_bounded(ins):
    cs = ins.COUNTERFACTUAL_SENT
    assert ins.enps(ins.OCT) < cs["cf_company_ch"] <= cs["cf_company"]
    assert ins.enps(ins.ic_o) < cs["cf_ic_ch"] <= cs["cf_ic"]
    ch = ins.COUNTERFACTUAL_HIRE
    assert 0 <= ch["breaches_cf"] <= ch["breaches_now"] and ch["days"] >= 0
    co = ins.COUNTERFACTUAL_OFFER
    assert co["fits"] <= co["n_low"] and 0 <= co["avoided"] <= co["declines_fits"]


def test_no_names_or_ids_in_insights(ins):
    """Names stay on the dashboard Hiring page only; insights and charts use 'Interviewer A (function, grade)'."""
    names = set(ins.names.employee_name)
    md = (ins.OUT / "insights.md").read_text(encoding="utf-8")
    assert not any(n in md for n in names)
    assert not re.search(r"EMP\d{5}", md)
    assert "Interviewer A (" in md and "Interviewer B (" in md


def test_dq_note_counts_from_log(ins):
    note = (ins.OUT / "dq_note.md").read_text(encoding="utf-8")
    log = pd.read_csv(ROOT / "data" / "clean" / "dq_log.csv")
    for issue_start, label in [("No matching requisition", "Orphan candidates"),
                               ("Exited with missing exit date", "Exited without an exit date"),
                               ("FINDING: system status disagrees", "ATS SLA status")]:
        n = int(log[log.issue.astype(str).str.startswith(issue_start)].rows_affected.sum())
        row = next(line for line in note.splitlines() if line.startswith(f"| {label}"))
        assert f"| {n:,} |" in row
    assert "manager_status" in note and "Limitations" in note


def test_reproducible(ins):
    p = ins.OUT / "insights.md"
    h1 = hashlib.sha256(p.read_bytes()).hexdigest()
    ins.main()
    assert hashlib.sha256(p.read_bytes()).hexdigest() == h1
    # the committed insights.md is what the script produces
    assert p.read_text(encoding="utf-8") == (ROOT / "analysis" / "insights.md").read_text(encoding="utf-8")
