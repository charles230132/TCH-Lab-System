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

# ==================== CSS 樣式 ====================
st.markdown("""
<style>
    [data-testid="stHeader"], footer { 
        visibility: hidden; 
    }
    
    div[data-testid="stTable"] {
        font-size: 1rem;
        overflow: visible !important;
        height: auto !important;
    }
    
    div[data-testid="stTable"] td {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        vertical-align: top !important;
        min-width: 100px;
        line-height: 1.6;
        padding: 8px !important;
    }
    
    div[data-testid="stTable"] th {
        white-space: nowrap !important;
        background-color: #f0f2f6 !important;
        font-weight: bold !important;
        padding: 10px !important;
    }
    
    div[data-testid="stTextInput"] > div > div > input {
        font-size: 1.1rem;
        padding: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ==================== 資料庫操作 ====================
@st.cache_data(ttl=CACHE_TTL)
def load_data() -> pd.DataFrame:
    """載入資料庫數據"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            df = pd.read_sql("SELECT * FROM tests", conn)
            return df.fillna("")
    except Exception as e:
        st.error(f"❌ 資料庫載入失敗: {e}")
        return pd.DataFrame()

def get_db_last_update() -> str:
    """取得資料庫最後更新時間"""
    try:
        import os
        if os.path.exists(DB_FILE):
            mod_time = os.path.getmtime(DB_FILE)
            from datetime import datetime
            update_time = datetime.fromtimestamp(mod_time)
            return update_time.strftime("%Y年%m月%d日 %H:%M:%S")
        else:
            return "尚未建立"
    except Exception as e:
        return f"無法取得 ({e})"

# ==================== 輔助函數 ====================
def is_valid_value(value: str) -> bool:
    """檢查值是否有效"""
    if not value or value.lower() in INVALID_VALUES:
        return False
    if value in HOSPITAL_NAMES:
        return False
    if re.match(r'^\d+(\.\d+)?\s*%?$', value):
        return False
    if re.match(r'^\d{1,2}$', value):
        return False
    return True

def is_reference_value(text: str) -> bool:
    """判斷文字是否為參考值格式"""
    if not text:
        return False
    return (re.match(r'^[0-9]', text) or 
            any(indicator in text.lower() for indicator in ['<', '>', 'mg/dl', 'u/l', 'mmol']))

def clean_text(text: str, remove_newlines: bool = True) -> str:
    """清理文字"""
    text = str(text).strip()
    if remove_newlines:
        text = text.replace('\n', ' ')
        text = re.sub(r'\s+', ' ', text)
    return text

def extract_clinical_notes(row: pd.Series) -> str:
    """提取臨床意義"""
    notes = []
    
    clinical_cols = sorted(
        [c for c in row.index if c.startswith('欄位_') and int(c.split('_')[1]) >= 10],
        key=lambda x: int(x.split('_')[1])
    )
    
    for col in clinical_cols:
        val = str(row.get(col, '')).strip()
        
        if not is_valid_value(val):
            continue
        
        if any(keyword in val for keyword in ['臨床意義', '參考值']):
            continue
        
        if not re.search(r'[\u4e00-\u9fff]', val):
            continue
        
        notes.append(val)
    
    return "\n".join(notes) if notes else "無"

def is_garbage_row(clinical_text: str, en_name: str) -> bool:
    """檢查是否為垃圾行"""
    if "D-Dimer" in clinical_text and "D-Dimer" not in en_name:
        return True
    
    if "血型" in clinical_text and not any(word in en_name for word in ["Blood", "Type"]):
        return True
    
    return False

# ==================== 搜尋邏輯（改進版）====================
def search_data(df: pd.DataFrame, search_term: str) -> pd.DataFrame:
    """執行搜尋並處理數據 - 改進版支援模糊搜尋"""
    
    # 清理搜尋詞：移除多餘空白
    search_term_clean = ' '.join(search_term.strip().split())
    
    # 轉小寫用於不區分大小寫搜尋
    search_lower = search_term_clean.lower()
    
    # 建立多種搜尋策略
    masks = []
    
    # 策略1: 直接包含搜尋（不區分大小寫）
    for col in ['欄位_0', '欄位_1', '欄位_2', '欄位_3']:
        mask = df[col].astype(str).str.lower().str.contains(search_lower, case=False, na=False, regex=False)
        masks.append(mask)
    
    # 策略2: 如果搜尋詞包含空格，也搜尋去除空格的版本
    if ' ' in search_term_clean:
        search_no_space = search_term_clean.replace(' ', '').lower()
        for col in ['欄位_0', '欄位_1', '欄位_2', '欄位_3']:
            mask = df[col].astype(str).str.lower().str.replace(' ', '').str.contains(search_no_space, case=False, na=False, regex=False)
            masks.append(mask)
    
    # 策略3: 分詞搜尋（所有詞都要出現）
    words = search_term_clean.lower().split()
    if len(words) > 1:
        for col in ['欄位_1', '欄位_2']:  # 只在中英文名稱中使用
            word_masks = [df[col].astype(str).str.lower().str.contains(word, case=False, na=False, regex=False) for word in words]
            if word_masks:
                combined_mask = word_masks[0]
                for m in word_masks[1:]:
                    combined_mask = combined_mask & m
                masks.append(combined_mask)
    
    # 合併所有搜尋結果
    final_mask = masks[0] if masks else pd.Series([False] * len(df))
    for mask in masks[1:]:
        final_mask = final_mask | mask
    
    return df[final_mask].copy()

def process_row(row: pd.Series) -> Optional[Dict[str, str]]:
    """處理單行數據"""
    code = clean_text(row.get('欄位_0', ''), remove_newlines=True)
    zh_name = clean_text(row.get('欄位_1', ''), remove_newlines=True)
    en_name = clean_text(row.get('欄位_2', ''), remove_newlines=True)
    
    raw_col3 = str(row.get('欄位_3', '')).strip()
    raw_col4 = str(row.get('欄位_4', '')).strip()
    raw_col5 = str(row.get('欄位_5', '')).strip()
    raw_col6 = str(row.get('欄位_6', '')).strip()
    raw_col9 = str(row.get('欄位_9', '')).strip()
    
    # 組套細項
    sub_item = "無"
    if raw_col3 and raw_col3 not in INVALID_VALUES:
        cleaned_col3 = re.sub(r'^\d+\s+', '', raw_col3).strip()
        
        if 'CBC' in cleaned_col3 and '項目' in cleaned_col3:
            return None
        
        if cleaned_col3 not in ['血清', '血漿', '全血', '尿', 'CSF', '胸水', '腹水', '']:
            if cleaned_col3.lower() != 'negative':
                if not is_reference_value(cleaned_col3):
                    sub_item = cleaned_col3
    
    # 年齡
    age = "無"
    if raw_col4 and any(indicator in raw_col4 for indicator in ['歲', '天', 'M', 'F', 'year', 'day', 'month', '~', '天-']):
        age = raw_col4
    
    # 參考值
    ref_value = "無"
    if sub_item == "無" and raw_col3 and is_reference_value(raw_col3):
        ref_value = raw_col3
    else:
        candidates = [raw_col5, raw_col6, raw_col9]
        for candidate in candidates:
            if not candidate or candidate in INVALID_VALUES:
                continue
            if candidate in HOSPITAL_NAMES:
                continue
            
            if is_reference_value(candidate) or candidate.lower() in ['negative', 'positive']:
                if ref_value == "無":
                    ref_value = candidate
                else:
                    if candidate not in ref_value:
                        ref_value += f" | {candidate}"
                break
    
    # 臨床意義
    clinical = extract_clinical_notes(row)
    
    if is_garbage_row(clinical, en_name):
        return None
    
    if sub_item == "無" and age == "無" and ref_value == "無" and clinical == "無":
        return None
    
    return {
        "健保代碼": code,
        "中文名稱": zh_name,
        "英文名稱": en_name,
        "組套細項": sub_item,
        "年齡": age,
        "參考值": ref_value,
        "臨床意義": clinical
    }

# ==================== 主程式 ====================
def main():
    st.title("🏥 檢驗項目查詢系統")
    
    with st.expander("📋 查看免責聲明", expanded=False):
        st.markdown(DISCLAIMER)
    
    st.markdown("---")
    
    df = load_data()
    
    if df.empty:
        st.error("❌ 資料庫是空的，請先執行 update_db.py")
        return
    
    last_update = get_db_last_update()
    st.info(f"📅 資料庫最後更新時間：{last_update}")
    
    search_term = st.text_input(
        "🔍 請輸入檢驗代碼或關鍵字：",
        "",
        placeholder="例如：Total Protein, AFP, 總蛋白, 09026...",
        help="可搜尋健保代碼、中文名稱、英文名稱或組套細項。支援模糊搜尋。"
    )
    
    if not search_term:
        st.info("💡 請在上方輸入搜尋關鍵字開始查詢")
        st.info("🔍 搜尋提示：\n- 支援中英文混合搜尋\n- 不區分大小寫\n- 可使用空格分隔多個關鍵字")
        return
    
    with st.spinner("🔍 搜尋中..."):
        result_df = search_data(df, search_term)
    
    if result_df.empty:
        st.warning(f"⚠️ 查無「{search_term}」相關資料")
        st.info("💡 搜尋建議：\n- 檢查是否有拼寫錯誤\n- 嘗試使用部分關鍵字（如：protein, 蛋白）\n- 使用健保代碼搜尋更精確")
        return
    
    display_rows = []
    for _, row in result_df.iterrows():
        processed = process_row(row)
        if processed:
            display_rows.append(processed)
    
    if not display_rows:
        st.warning("⚠️ 查無資料（有效資料過濾後為空）。")
        return
    
    final_df = pd.DataFrame(display_rows).drop_duplicates()
    
    st.success(f"✅ 找到 {len(final_df)} 筆結果")
    
    for idx, row in final_df.iterrows():
        with st.expander(f"📋 {row['中文名稱']} ({row['英文名稱']}) - {row['健保代碼']}", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**健保代碼：** {row['健保代碼']}")
                st.markdown(f"**中文名稱：** {row['中文名稱']}")
                st.markdown(f"**英文名稱：** {row['英文名稱']}")
                st.markdown(f"**組套細項：** {row['組套細項']}")
            
            with col2:
                st.markdown(f"**年齡：** {row['年齡']}")
                st.markdown(f"**參考值：** {row['參考值']}")
            
            st.markdown("---")
            st.markdown(f"**臨床意義：**\n\n{row['臨床意義']}")

if __name__ == "__main__":
    main()
