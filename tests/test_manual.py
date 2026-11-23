from pathlib import Path
import hashlib
import json
import fitz
from streamlit.testing.v1 import AppTest

from manual_search import load_index, search_pages, find_quick_items, find_nhi_items, expanded_terms, normalized

ROOT = Path(__file__).resolve().parents[1]
INDEX = load_index(ROOT / "data/manual_pages.json")
QUICK = json.loads((ROOT / "data/quick_items.json").read_text(encoding="utf-8"))
NHI = json.loads((ROOT / "data/nhi_items.json").read_text(encoding="utf-8"))


def test_index_is_the_exact_approved_pdf():
    manifest = json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
    source = ROOT / "data" / manifest["file"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["sha256"]
    with fitz.open(source) as doc:
        assert len(doc) == len(INDEX) == 89
        for item, page in zip(INDEX, doc):
            assert item["text"] == page.get_text()


def test_aliases_and_fullwidth_code_find_the_right_collection_page():
    for query in ["血氨", "Ammonia", "NH3", "０９０３７"]:
        assert 10 in [r["page"] for r in search_pages(INDEX, query)]
        assert find_quick_items(QUICK, query)[0]["id"] == "ammonia"
    assert 11 in [r["page"] for r in search_pages(INDEX, "Lactic acid")]
    assert 11 in [r["page"] for r in search_pages(INDEX, "CBC")]
    assert 40 not in [r["page"] for r in search_pages(INDEX, "Ammonia")]  # 氨基酸 page
    assert search_pages(INDEX, "[") == []
    assert search_pages(INDEX, "") == []


def test_reference_rows_are_never_collapsed_or_relabelled():
    matches = search_pages(INDEX, "CBC", category="reference")
    assert {32, 33, 34}.issubset({m["page"] for m in matches})
    assert 34 in {m["page"] for m in search_pages(INDEX, "08008", category="reference")}
    page = INDEX[32]["text"]
    assert "陽明" in page and "仁愛" in page and "中興" in page
    assert "0天-14天" in page.replace(" ", "")
    assert all(m["category"] == "reference" for m in matches)


def test_clinical_quick_facts_have_verified_claims_and_valid_pages():
    evidence = json.loads((ROOT / "data/verified_claims.json").read_text(encoding="utf-8"))
    for item in QUICK:
        assert item["claim_ids"]
        assert set(item["claim_ids"]).issubset(evidence)
        assert all(1 <= page <= 89 for page in item["pages"])
    culture = next(x for x in QUICK if x["id"] == "blood_culture")
    assert "CDC" in culture["notice"] and "10 mL" in culture["amount"]
    assert "C23" not in culture["claim_ids"]  # 陽明手冊未列去抗生素血瓶
    coag = next(x for x in QUICK if x["id"] == "coagulation")
    assert "2 mL" in coag["amount"] and "2.7" in coag["amount"]


def test_source_is_the_yangming_manual():
    manifest = json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["document_number"] == "TCHYM-QP-7.2-2-(1)"
    assert manifest["source_header"] == "陽明院區檢驗科"
    assert "本院區各病房及檢驗室" in INDEX[1]["text"].replace(" ", "")


def test_app_search_and_source_page_render():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    app.text_input[0].set_value("血氨").run()
    assert not app.exception
    assert app.text_input[0].value == "血氨"
    assert any("Ammonia" in x.value for x in app.subheader)
    app.button(key="ammonia_p10").click().run()
    assert not app.exception
    assert any("10 / 89" in x.value for x in app.subheader)
    app.radio[0].set_value("參考值與臨床意義").run()
    assert not app.exception


def test_nhi_codes_are_exact_identifiers_and_never_expand_into_other_codes():
    assert expanded_terms("０８０１４") == ["08014"]
    for code in ["08014", "08011", "09037", "08026", "08036", "08079"]:
        hits = search_pages(INDEX, code)
        assert hits
        import re
        for hit in hits:
            original = re.search(r"(?<!\d)" + code + r"(?!\d)", normalized(hit["text"]))
            assert original or (hit["match_kind"] == "continuation" and re.search(r"(?<!\d)" + code + r"(?!\d)", normalized(" ".join(hit.get("topics", [])))))
    sample = [{"page": 1, "category": "collection", "text": "08011 CBC-I", "section": "CBC"},
              {"page": 2, "category": "collection", "text": "1080140", "section": "Other"}]
    assert search_pages(sample, "08014") == []
    assert {x["code"] for x in find_nhi_items(NHI, "０８０１１")} == {"08011"}
    assert {x["code"] for x in find_nhi_items(NHI, "PT")} == {"08026"}
    cbc = find_nhi_items(NHI, "CBC")
    assert {x["code"] for x in cbc} == {"08014", "08011"}
    assert len(find_nhi_items(NHI, "09041")) == 2  # Same code, different source rows.


def test_nhi_mappings_are_verified_and_bound_to_the_source_manifest():
    manifest = json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((ROOT / "data/nhi_items.json").read_bytes()).hexdigest() == manifest["nhi_sha256"]
    claims = json.loads((ROOT / "data/verified_claims.json").read_text(encoding="utf-8"))
    assert len(NHI) == 10
    for item in NHI:
        assert item["claim_id"] in claims
        assert item["code"] in claims[item["claim_id"]]["quote"]
        assert str(item["page"]) == str(claims[item["claim_id"]]["page"])


def test_nhi_lookup_ui_opens_the_correct_original_page():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio[0].set_value("健保碼查詢").run()
    app.text_input[0].set_value("０８０１１").run()
    assert not app.exception
    texts = [x.value for x in app.markdown]
    assert any("08011" in value and "CBC-I" in value for value in texts)
    assert not any("08014" in value for value in texts)
    app.button(key="nhi_N06").click().run()
    assert not app.exception
    assert any("11 / 89" in x.value for x in app.subheader)


def test_last_updated_and_feedback_are_visible():
    import app as app_module
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    captions = " ".join(c.value for c in app.caption)
    assert f"最新更新日期：{app_module.LAST_UPDATED}" in captions
    assert any(f"最新更新：{app_module.LAST_UPDATED}" in x.value for x in app.info)
    assert ":" in app_module.LAST_UPDATED  # 含時間
    assert app_module.FEEDBACK_PHONE in captions
    assert any(h.value == "錯誤回報" for h in app.subheader)


def test_feedback_url_never_carries_search_text(monkeypatch):
    from urllib.parse import parse_qs, urlsplit
    import app as app_module
    monkeypatch.setattr(app_module, "FEEDBACK_PREFILL", {"page": "entry.2", "version": "entry.3"})
    monkeypatch.setattr(app_module, "FEEDBACK_FORM_URL", "https://docs.google.com/forms/d/e/TEST/viewform?usp=sf_link#top")
    parts = urlsplit(app_module.feedback_url(12))
    params = parse_qs(parts.query)
    assert parts.path.endswith("/viewform") and parts.fragment == "top"
    assert params == {"usp": ["pp_url"], "embedded": ["true"], "entry.2": ["第12頁"], "entry.3": [app_module.APP_VERSION]}
    assert "entry.2" not in parse_qs(urlsplit(app_module.feedback_url(None)).query)
    monkeypatch.setattr(app_module, "FEEDBACK_FORM_URL", "")
    assert app_module.feedback_url(12) == ""


def test_feedback_button_hidden_until_form_is_configured():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    app.query_params["q"] = "王小明 1234567"
    app.run()
    assert not app.get("link_button")
    assert any(h.value == "錯誤回報" for h in app.subheader)


def test_quick_buttons_fill_search():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.button(key="quick_btn_血氨").click().run()
    assert not app.exception
    assert app.text_input[0].value == "血氨"
    assert any("Ammonia" in x.value for x in app.subheader)
