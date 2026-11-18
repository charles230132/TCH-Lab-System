"""Yangming laboratory lookup backed by a versioned source PDF."""
from pathlib import Path
import hashlib
import json

import fitz
import streamlit as st

from manual_search import load_index, search_pages, find_quick_items

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
st.set_page_config(page_title="陽明院區檢驗科｜採檢查詢", page_icon="🔬", layout="wide")


@st.cache_data(show_spinner=False)
def get_data(source_revision: str):
    manifest = json.loads((DATA / "source_manifest.json").read_text(encoding="utf-8"))
    pdf = (DATA / manifest["file"]).read_bytes()
    if hashlib.sha256(pdf).hexdigest() != manifest["sha256"]:
        raise ValueError("Source PDF does not match the pinned manifest")
    index = load_index(DATA / "manual_pages.json")
    if hashlib.sha256((DATA / "manual_pages.json").read_bytes()).hexdigest() != manifest["index_sha256"]:
        raise ValueError("Index does not match the pinned manifest")
    if len(index) != manifest["pages"]:
        raise ValueError("Source page count mismatch")
    quick = json.loads((DATA / "quick_items.json").read_text(encoding="utf-8"))
    return manifest, pdf, index, quick


@st.cache_data(show_spinner=False, max_entries=16)
def page_image(pdf_bytes: bytes, page: int):
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc[page - 1].get_pixmap(matrix=fitz.Matrix(1.65, 1.65)).tobytes("png")


@st.cache_data(show_spinner=False, max_entries=16)
def one_page_pdf(pdf_bytes: bytes, page: int):
    with fitz.open(stream=pdf_bytes, filetype="pdf") as source, fitz.open() as target:
        target.insert_pdf(source, from_page=page - 1, to_page=page - 1)
        return target.tobytes()


def choose_query(value):
    st.session_state["search_query"] = value
    st.session_state.pop("open_page", None)
    st.query_params["q"] = value


def update_query():
    st.query_params["q"] = st.session_state["search_query"].strip()
    st.session_state.pop("open_page", None)
    st.session_state["quick_choice"] = None


def choose_shortcut():
    selected = st.session_state.get("quick_choice")
    if selected:
        choose_query(selected)


def open_page(page, context):
    st.session_state["open_page"] = page
    st.session_state["open_context"] = context


def source_buttons(pages, prefix):
    for page in pages:
        st.button(f"查看手冊第 {page} 頁", key=f"{prefix}_p{page}", on_click=open_page, args=(page, f"quick_{prefix}"))


def show_source(pdf_bytes, index, manifest, context):
    if st.session_state.get("open_context") != context or "open_page" not in st.session_state:
        return
    page = st.session_state["open_page"]
    st.subheader(f"採檢手冊原文　第 {page} / {manifest['pages']} 頁")
    st.caption("保留原文件版面及頁首；查詢服務由陽明院區檢驗科提供。")
    st.caption("手機查看寬表時，可下載本頁PDF後放大閱讀。")
    st.image(page_image(pdf_bytes, page), width="stretch")
    st.download_button("下載這一頁PDF", one_page_pdf(pdf_bytes, page), file_name=f"採檢手冊_第{page}頁.pdf", mime="application/pdf", key=f"download_{context}_p{page}")
    with st.expander("原文文字（輔助閱讀）"):
        st.text_area("本頁擷取文字；表格欄位請以原圖為準", index[page - 1]["text"], height=300, disabled=True, key=f"text_{context}_p{page}")


def main():
    try:
        revision = hashlib.sha256((DATA / "source_manifest.json").read_bytes()).hexdigest()
        manifest, pdf_bytes, index, quick = get_data(revision)
    except (OSError, ValueError, KeyError):
        st.error("查詢資料暫時無法載入，請聯絡檢驗科。")
        return
    st.title("陽明院區檢驗科")
    st.header("採檢與檢驗項目查詢", divider="blue")
    st.caption("臺北市立聯合醫院　｜　115年採檢手冊　｜　病房與臨床醫療人員適用")
    if "search_query" not in st.session_state:
        st.session_state["search_query"] = str(st.query_params.get("q", ""))[:200]
    st.text_input("檢驗項目、英文縮寫或健保代碼", key="search_query", placeholder="例如：血氨、Ammonia、乳酸、CBC、09037", on_change=update_query, max_chars=200)
    st.pills("ICU常用項目", ["血液培養", "血液氣體", "血氨", "乳酸", "CBC", "凝血"], key="quick_choice", on_change=choose_shortcut)
    mode = st.radio("查詢範圍", ["採檢快查", "參考值與臨床意義", "手冊全文"], horizontal=True)
    query = st.session_state["search_query"].strip()
    if query:
        items = find_quick_items(quick, query) if mode == "採檢快查" else []
        for item in items:
            with st.container(border=True):
                st.subheader(item["title"])
                if item.get("notice"):
                    st.info(item["notice"])
                left, right = st.columns(2)
                with left:
                    st.markdown("**採檢容器**")
                    st.write(item["container"])
                with right:
                    st.markdown("**採檢量／規格**")
                    st.write(item["amount"])
                st.markdown("**保存、送檢與採檢提醒**")
                for fact in item["facts"]:
                    st.markdown(f"- {fact}")
                st.caption(item["source_label"])
                with st.expander("核對來源"):
                    source_buttons(item["pages"], item["id"])
                    show_source(pdf_bytes, index, manifest, f"quick_{item['id']}")
                    if item.get("supplement_url"):
                        st.link_button("CDC成人血液培養原始指引（第1–2頁）", item["supplement_url"])
        category = "reference" if mode == "參考值與臨床意義" else None
        results = search_pages(index, query, category=category)
        st.subheader("手冊原文")
        if mode == "參考值與臨床意義":
            st.caption("保留原表的年齡、性別、院區、單位及合併儲存格；不把量測不確定度當成參考值。")
        if not results:
            st.warning("這個範圍沒有找到相符頁面。可改用英文縮寫、健保代碼，或切換「手冊全文」。")
        else:
            st.caption(f"找到 {len(results)} 個相符頁面；按頁面開啟原始表格。")
            batches = max(1, (len(results) + 7) // 8)
            batch = st.selectbox("搜尋結果頁", range(1, batches + 1), format_func=lambda x: f"第 {x} / {batches} 組", key=f"batch_{mode}_{query}") if batches > 1 else 1
            for hit in results[(batch - 1) * 8:batch * 8]:
                with st.container(border=True):
                    st.markdown(f"**第 {hit['page']} 頁　{hit['section']}**")
                    if hit["category"] == "reference":
                        st.write("參考值、適用族群與臨床意義請查看本頁原表；檢驗效能與量測不確定度另列，不與參考值合併。")
                    else:
                        st.write(hit["snippet"])
                    context = f"hit_{mode}_{hit['page']}"
                    st.button("開啟這一頁原文", key=context, on_click=open_page, args=(hit["page"], context))
                    show_source(pdf_bytes, index, manifest, context)
    else:
        st.info("輸入關鍵字，或選上方的ICU常用項目。採檢快查可查看容器與送檢提醒；參考值請對照原表的適用條件。")
    st.divider()
    with st.expander("手冊版本、資料來源與使用說明"):
        st.write("服務單位：臺北市立聯合醫院陽明院區檢驗科")
        st.write(f"主要資料：{manifest['source_name']}（{manifest['pages']}頁）")
        st.write(f"文件編號：{manifest['document_number']}")
        st.write("來源檔名標示1150420；不以伺服器檔案時間作為手冊修訂日期。")
        st.write("原始PDF頁首為中興院區；文件適用範圍列各院區病房及檢驗科。陽明院區耗材規格、作業流程及特殊檢驗要求，依現行核定規定及檢驗科確認。")
        st.write("採檢快查採用經核對的手冊內容；其他檢驗項目保留完整原頁供查閱，不把不同族群或院區的數字合併。血液培養血量另列CDC指引補充，並未將外部指引冒稱為陽明已核定的規範。")
        st.download_button("下載完整採檢手冊PDF", pdf_bytes, file_name=manifest["source_name"], mime="application/pdf")
        st.caption("請勿在搜尋欄輸入病人姓名、病歷號碼或其他個人資料。")
    st.caption("陽明院區檢驗科　｜　採檢規定如有疑義，請先與檢驗科確認。")


if __name__ == "__main__":
    main()
