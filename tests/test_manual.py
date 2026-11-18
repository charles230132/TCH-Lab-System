from pathlib import Path
import hashlib
import json
import fitz
from streamlit.testing.v1 import AppTest

from manual_search import load_index, search_pages, find_quick_items

ROOT = Path(__file__).resolve().parents[1]
INDEX = load_index(ROOT / "data/manual_pages.json")
QUICK = json.loads((ROOT / "data/quick_items.json").read_text(encoding="utf-8"))


def test_index_is_the_exact_approved_pdf():
    manifest = json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
    source = ROOT / "data" / manifest["file"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["sha256"]
    with fitz.open(source) as doc:
        assert len(doc) == len(INDEX) == 105
        for item, page in zip(INDEX, doc):
            assert item["text"] == page.get_text()


def test_aliases_and_fullwidth_code_find_the_right_collection_page():
    for query in ["血氨", "Ammonia", "NH3", "０９０３７"]:
        assert 12 in [r["page"] for r in search_pages(INDEX, query)]
        assert find_quick_items(QUICK, query)[0]["id"] == "ammonia"
    assert 13 in [r["page"] for r in search_pages(INDEX, "Lactic acid")]
    assert 14 in [r["page"] for r in search_pages(INDEX, "CBC")]
    assert 22 not in [r["page"] for r in search_pages(INDEX, "Ammonia")]
    assert search_pages(INDEX, "[") == []
    assert search_pages(INDEX, "") == []


def test_reference_rows_are_never_collapsed_or_relabelled():
    matches = search_pages(INDEX, "CBC", category="reference")
    assert {77, 78, 79}.issubset({m["page"] for m in matches})
    assert 80 in {m["page"] for m in search_pages(INDEX, "08008", category="reference")}
    page = INDEX[76]["text"]
    assert "陽明" in page and "仁愛" in page and "中興" in page
    assert "0天-14天" in page.replace(" ", "")
    assert all(m["category"] == "reference" for m in matches)


def test_clinical_quick_facts_have_verified_claims_and_valid_pages():
    evidence = json.loads((ROOT / "data/verified_claims.json").read_text(encoding="utf-8"))
    for item in QUICK:
        assert item["claim_ids"]
        assert set(item["claim_ids"]).issubset(evidence)
        assert all(1 <= page <= 105 for page in item["pages"])
    culture = next(x for x in QUICK if x["id"] == "blood_culture")
    assert "CDC" in culture["notice"] and "10 mL" in culture["amount"]


def test_app_search_and_source_page_render():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    app.text_input[0].set_value("血氨").run()
    assert not app.exception
    assert app.text_input[0].value == "血氨"
    assert any("Ammonia" in x.value for x in app.subheader)
    app.button(key="ammonia_p12").click().run()
    assert not app.exception
    assert any("12 / 105" in x.value for x in app.subheader)
    app.radio[0].set_value("參考值與臨床意義").run()
    assert not app.exception
