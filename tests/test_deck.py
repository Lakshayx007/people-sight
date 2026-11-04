"""Phase 11: the insight deck builds, has 12 slides with notes, and every number on it traces to insights.md."""
import importlib.util
import re
from pathlib import Path

import pytest

pytest.importorskip("pptx", reason="analysis extras not installed (pip install -r requirements-analysis.txt)")
pytest.importorskip("scipy", reason="analysis extras not installed")
from pptx import Presentation  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def deck(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("deck06", ROOT / "pipeline" / "06_build_deck.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path_factory.mktemp("deck")
    mod.DECK, mod.TRACE = out / "deck.pptx", out / "trace.md"
    mod.I.CHARTS = out / "charts"
    mod.build()
    mod.write_trace()
    return mod


def _texts(prs):
    for i, slide in enumerate(prs.slides, 1):
        parts = []
        for shp in slide.shapes:
            if shp.has_text_frame:
                parts.append(shp.text_frame.text)
            if shp.has_table:
                parts += [c.text for r in shp.table.rows for c in r.cells]
        yield i, " ".join(parts), slide.notes_slide.notes_text_frame.text


def test_twelve_slides_with_notes_and_charts(deck):
    prs = Presentation(str(deck.DECK))
    assert len(prs.slides) == 12
    assert abs(prs.slide_width / prs.slide_height - 16 / 9) < 0.01
    for i, body, notes in _texts(prs):
        assert len(notes) > 80, f"slide {i} needs speaker notes"
    pics = [sum(1 for s in sl.shapes if s.shape_type == 13) for sl in prs.slides]
    assert all(p == 1 for p in pics[2:10]) and pics[0] == pics[1] == pics[10] == pics[11] == 0


def test_every_number_traced(deck):
    rows = deck.TRACE_ROWS
    assert len(rows) > 150
    ins = (ROOT / "analysis" / "insights.md").read_text(encoding="utf-8").splitlines()
    dq = (ROOT / "analysis" / "dq_note.md").read_text(encoding="utf-8").splitlines()
    for slide, where, tok, file, line, _ in rows:
        src = ins if file == "insights.md" else dq
        assert tok.lstrip("+") in src[line - 1], (slide, where, tok)
    assert {r[0] for r in rows} == set(range(1, 13))


def test_no_names_or_ids_on_slides(deck):
    names = set(deck.I.names.employee_name) | set(deck.I.REQ.recruiter.dropna())
    for i, body, notes in _texts(Presentation(str(deck.DECK))):
        text = body + notes
        assert not any(n in text for n in names), f"slide {i} shows a name"
        assert not re.search(r"EMP\d{5}", text), f"slide {i} shows an employee ID"
