import streamlit as st
import pandas as pd
import sqlite3
import re
from typing import List, Dict, Optional

# ==================== 配置 ====================
DB_FILE = "lab_test.db"
CACHE_TTL = 600

# 無效值集合
INVALID_VALUES = {'無', 'None', 'nan', 'null', '', '*'}
HOSPITAL_NAMES = {'忠孝', '仁愛', '和平', '陽明', '中興', '松德', '林森', '婦幼'}

# ==================== 網頁設定 ====================
st.set_page_config(
    page_title="TCH 檢驗查詢", 
    page_icon="🏥", 
    layout="wide"
)

# ==================== 免責聲明 ====================
DISCLAIMER = """
⚠️ **免責聲明**

本應用系統僅供參考之用，不構成任何醫療建議。使用者因使用本系統所產生的任何損害、損失或傷害，本應用開發者不承擔任何責任。

- 本系統提供的檢驗資料來源於資料庫，可能存在誤差或延遲
- 檢驗結果的解釋需由合格的醫療專業人士進行評估
- 患者應就醫療相關問題咨詢其主治醫生或專科醫生
- 任何醫療決定應基於全面的臨床評估，而不應僅依賴本系統
- 本應用不對資料的準確性、完整性或及時性做出任何保證

使用本系統即表示您已同意上述免責聲明。
"""

# ==================== CSS 樣式 (極致高對比 + 精準搜尋 + 預設收合版) ====================
st.markdown("""
<style>
    /* --- 全域設定 --- */
    html, body, [class*="css"] {
        font-size: 22px !important; /* 基礎字級加大 */
        font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif;
        background-color: #1a1a1a !important;
        color: #FFFFFF !important;
    }

    [data-testid="stHeader"], footer { visibility: hidden; }

    .stApp {
        background-color: #1a1a1a !important;
    }
    
    /* --- 標題優化 --- */
    h1 { 
        font-size: 3rem !important; 
        color: #FFFFFF !important; 
        font-weight: 800 !important;
        background-color: transparent !important;
    }
    h2 { 
        font-size: 2.4rem !important; 
        color: #FFFFFF !important; 
        font-weight: 800 !important;
        background-color: transparent !important;
    }
    h3, h4, h5, h6 { 
        color: #FFFFFF !important;
        background-color: transparent !important;
    }
    
    .stMarkdown p, .stMarkdown li, .stMarkdown div {
        font-size: 1.3rem !important;
        color: #FFFFFF !important; /* 白色字體 */
        line-height: 1.6 !important;
        background-color: transparent !important;
    }

    /* --- 搜尋框 (極致顯眼) --- */
    div[data-testid="stTextInput"] label {
        font-size: 1.6rem !important;
        color: #FFFFFF !important;
        font-weight: bold !important;
        background-color: transparent !important;
    }
    div[data-testid="stTextInput"] input {
        font-size: 1.8rem !important;
        color: #000000 !important;
        background-color: #FFFFFF !important; /* 白底輸入框 */
        border: 3px solid #0088FF !important;
    }
    
    /* --- Expander (摺疊卡片) 樣式核心 --- */
    /* 卡片標題頭：未展開時 */
    .streamlit-expanderHeader {
        background-color: #2a2a2a !important; /* 深灰底 */
        border: 2px solid #0088FF !important;
        border-radius: 8px !important;
        padding: 15px !important;
        margin-top: 10px !important;
    }
    
    /* 針對標題內的文字強制白色加粗 (確保看得很清楚) */
    .streamlit-expanderHeader p, 
    .streamlit-expanderHeader span,
    .streamlit-expanderHeader div {
        font-size: 1.5rem !important;
        font-weight: 900 !important; /* 極粗體 */
        color: #FFFFFF !important;   /* 白色 */
    }
    
    /* 滑鼠滑過時的效果 */
    .streamlit-expanderHeader:hover {
        background-color: #3a3a3a !important;
        border-color: #00CCFF !important;
    }

    /* 展開後的內容區塊 */
    .streamlit-expanderContent {
        background-color: #1a1a1a !important;
        border: 2px solid #0088FF;
        border-top: none;
        padding: 20px !important;
        color: #FFFFFF !important;
    }
    
    /* --- 表格內容 --- */
    div[data-testid="stTable"] td {
        font-size: 1.2rem !important;
        color: #FFFFFF !important;
    }

    /* 錯誤與提示訊息 */
    div[data-testid="stAlert"] {
        font-size: 1.4rem !important;
        font-weight: bold !important;
        color: #FFFFFF !important;
    }
    
    /* 確保所有 markdown 內容文字可見 */
    .stMarkdown * {
        background-color: transparent !important;
    }
    
    /* Columns 和其他容器 */
    .stColumn {
        background-color: transparent !important;
    }
</style>
""", unsafe_allow_html=True)

# ==================== 資料庫操作 ====================
@st.cache_data(ttl=CACHE_TTL)
def load_data() -> pd.DataFrame:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            df = pd.read_sql("SELECT * FROM tests", conn)
            for col in df.columns:
                df[col] = df[col].astype(str).str.replace('\n', ' ').str.replace(r'\s+', ' ', regex=True)
            return df.fillna("")
    except Exception as e:
        st.error(f"❌ 資料庫載入失敗: {e}")
        return pd.DataFrame()

def get_db_last_update() -> str:
    try:
        import os
        if os.path.exists(DB_FILE):
            mod_time = os.path.getmtime(DB_FILE)
            from datetime import datetime
            return datetime.fromtimestamp(mod_time).strftime("%Y年%m月%d日 %H:%M:%S")
        else:
            return "尚未建立"
    except:
        return "未知"

# ==================== 輔助函數 ====================
def is_valid_value(value: str) -> bool:
    if not value or value.lower() in INVALID_VALUES: return False
    if value in HOSPITAL_NAMES: return False
    return True

def clean_text(text: str) -> str:
    return str(text).strip().replace('\n', ' ').replace('  ', ' ')

def extract_clinical_notes(row: pd.Series) -> str:
    notes = []
    all_cols = row.index.tolist()
    start_idx = 7
    if len(all_cols) > start_idx:
        potential_cols = all_cols[start_idx:]
        for col in potential_cols:
            val = str(row.get(col, '')).strip()
            if not is_valid_value(val): continue
            if len(val) < 2: continue
            if any(k in val for k in ['臨床意義', '參考值']): continue
            if re.search(r'[\u4e00-\u9fff]', val) or len(val) > 20:
                notes.append(val)
    return "\n".join(notes) if notes else "無"

# ==================== 搜尋邏輯 (精準修正版) ====================
def search_data(df: pd.DataFrame, search_term: str) -> pd.DataFrame:
    """
    搜尋邏輯修正：限制搜尋範圍以減少雜訊
    """
    if df.empty: return df
    
    search_term = search_term.strip()
    search_lower = search_term.lower()
    search_no_space = search_term.replace(' ', '').lower()
    
    target_cols = ['欄位_0', '欄位_1', '欄位_2', '欄位_3']
    valid_cols = [c for c in target_cols if c in df.columns]
    
    if not valid_cols: return df 

    subset = df[valid_cols].astype(str).apply(lambda x: ' '.join(x), axis=1).str.lower()
    mask = subset.str.contains(search_lower, case=False, regex=False)
    
    if ' ' in search_term:
        mask = mask | subset.str.replace(' ', '').str.contains(search_no_space, case=False, regex=False)
    
    return df[mask].copy()

def process_row(row: pd.Series) -> Optional[Dict[str, str]]:
    raw_code = clean_text(row.get('欄位_0', ''))
    raw_zh = clean_text(row.get('欄位_1', ''))
    raw_en = clean_text(row.get('欄位_2', ''))
    raw_col3 = clean_text(row.get('欄位_3', ''))
    
    if re.search(r'[\u4e00-\u9fff]', raw_code) and not raw_zh:
        raw_zh = raw_code
        raw_code = "無/位移"
    
    if re.match(r'^[A-Za-z\s\-\.]+$', raw_zh) and not raw_en:
        raw_en = raw_zh
    
    if not raw_zh and not raw_en:
        return None

    code = raw_code if raw_code and raw_code not in INVALID_VALUES else "無"
    zh_name = raw_zh if raw_zh and raw_zh not in INVALID_VALUES else "無"
    en_name = raw_en if raw_en and raw_en not in INVALID_VALUES else "無"
    sub_item = raw_col3 if is_valid_value(raw_col3) else "無"
    
    ref_candidates = []
    for c_idx in [4, 5, 6, 9]:
        val = clean_text(row.get(f'欄位_{c_idx}', ''))
        if is_valid_value(val) and len(val) < 50:
             ref_candidates.append(val)
    ref_value = " | ".join(ref_candidates) if ref_candidates else "請參閱臨床意義"

    clinical = extract_clinical_notes(row)

    return {
        "健保代碼": code,
        "中文名稱": zh_name,
        "英文名稱": en_name,
        "組套細項": sub_item,
        "參考值": ref_value,
        "臨床意義": clinical
    }

# ==================== 主程式 ====================
def main():
    st.title("🏥 TCH 檢驗項目查詢系統")
    
    # 修改：免責聲明預設收合 (expanded=False)，保持介面清爽
    with st.expander("⚠️ 重要：請先閱讀免責聲明 (點擊展開)", expanded=False):
        st.markdown(DISCLAIMER)
    
    st.markdown("---")
    
    df = load_data()
    if df.empty:
        st.error("❌ 資料庫為空，請確認 update_db.py 是否執行成功")
        return

    st.info(f"📅 資料庫最後更新：{get_db_last_update()} (共 {len(df)} 筆資料)")
    
    search_term = st.text_input("🔍 請輸入關鍵字搜尋 (例如: AFP, CBC, 09026)", "")

    if search_term:
        result_df = search_data(df, search_term)
        
        display_rows = []
        for _, row in result_df.iterrows():
            processed = process_row(row)
            if processed:
                display_rows.append(processed)
        
        if not display_rows:
            st.warning(f"⚠️ 找不到相符資料。請確認關鍵字是否正確。")
            with st.expander("🔧 開發者除錯：查看原始資料", expanded=False):
                st.dataframe(result_df)
        else:
            # 去除重複結果
            df_display = pd.DataFrame(display_rows)
            df_display = df_display.drop_duplicates(subset=['健保代碼', '英文名稱', '組套細項'], keep='first')
            display_rows = df_display.to_dict('records')
            
            st.success(f"✅ 找到 {len(display_rows)} 筆結果")
            for row in display_rows:
                # 標題格式：中文 | 英文 - 細項
                title_str = f"📋 {row['中文名稱']} | {row['英文名稱']}"
                if row['組套細項'] != "無":
                    title_str += f" - {row['組套細項']}"
                
                # 修改：expanded=False，預設結果收合
                with st.expander(title_str, expanded=False):
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.markdown(f"**🔹 代碼：** `{row['健保代碼']}`")
                        st.markdown(f"**🔹 中文：** {row['中文名稱']}")
                    with c2:
                        st.markdown(f"**🔹 英文：** {row['英文名稱']}")
                        st.markdown(f"**🔹 細項：** {row['組套細項']}")
                    st.markdown("---")
                    st.markdown(f"**🔸 參考值：** {row['參考值']}")
                    st.markdown(f"**🔸 臨床意義：**\n{row['臨床意義']}")

if __name__ == "__main__":
    main()
