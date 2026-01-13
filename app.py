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
    /* 隱藏頁首和頁尾 */
    [data-testid="stHeader"], footer { 
        visibility: hidden; 
    }
    
    /* 表格樣式優化 */
    div[data-testid="stTable"] {
        font-size: 1rem;
        overflow: visible !important;
        height: auto !important;
    }
    
    /* 強制換行並優化顯示 */
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
    
    /* 移除表格底部多餘空白 */
    div[data-testid="stTable"] table {
        margin-bottom: 0 !important;
    }
    
    /* 移除空白容器 */
    div[data-testid="stVerticalBlock"] > div:empty {
        display: none !important;
    }
    
    /* 自訂 HTML 表格樣式 */
    .custom-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 1rem;
        margin-bottom: 0 !important;
        table-layout: auto;
    }
    
    .custom-table thead {
        position: sticky;
        top: 0;
        z-index: 10;
    }
    
    .custom-table th {
        background-color: #f0f2f6;
        border: 1px solid #ddd;
        padding: 10px;
        text-align: left;
        font-weight: bold;
        white-space: nowrap;
    }
    
    .custom-table td {
        border: 1px solid #ddd;
        padding: 8px;
        vertical-align: top;
        white-space: pre-wrap;
        word-wrap: break-word;
        line-height: 1.6;
        max-width: 300px;
    }
    
    .custom-table tbody tr {
        page-break-inside: avoid;
    }
    
    /* 確保表格後面沒有多餘空間 */
    .custom-table + * {
        margin-top: 0 !important;
    }
    
    /* 搜尋框樣式 */
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

# ==================== 輔助函數 ====================
def is_valid_value(value: str) -> bool:
    """檢查值是否有效"""
    if not value or value.lower() in INVALID_VALUES:
        return False
    if value in HOSPITAL_NAMES:
        return False
    # 排除純數字（包含小數和百分比）
    if re.match(r'^\d+(\.\d+)?\s*%?$', value):
        return False
    # 排除單獨的1-2位數字
    if re.match(r'^\d{1,2}$', value):
        return False
    return True

def is_reference_value(text: str) -> bool:
    """判斷文字是否為參考值格式"""
    if not text:
        return False
    # 數字開頭或包含單位/符號
    return (re.match(r'^[0-9]', text) or 
            any(indicator in text.lower() for indicator in ['<', '>', 'mg/dl', 'u/l', 'mmol']))

def clean_text(text: str, remove_newlines: bool = True) -> str:
    """清理文字"""
    text = str(text).strip()
    if remove_newlines:
        text = text.replace('\n', ' ')
        text = re.sub(r'\s+', ' ', text)
    return text

def extract_sub_item(raw_col3: str) -> str:
    """提取組套細項"""
    if not raw_col3 or raw_col3 in INVALID_VALUES:
        return "無"
    
    # 常見的非細項值
    non_sub_items = ['血清', '血漿', '全血', '尿', 'CSF', '胸水', '腹水']
    if raw_col3 in non_sub_items:
        return "無"
    
    # 如果是 negative，作為參考值而非細項
    if raw_col3.lower() == 'negative':
        return "無"
    
    # 過濾 CBC 項目標題（包含「CBC」和「項目」的標題行）
    if 'CBC' in raw_col3 and '項目' in raw_col3:
        return None  # 標記為跳過此行
    
    # 所有其他情況都視為有效的細項
    return raw_col3

def extract_reference_value(row: pd.Series) -> str:
    """提取參考值"""
    raw_col3 = str(row.get('欄位_3', '')).strip()
    raw_col5 = str(row.get('欄位_5', '')).strip()
    raw_col9 = str(row.get('欄位_9', '')).strip()
    
    ref_values = []
    
    # 檢查 col3
    if is_reference_value(raw_col3):
        ref_values.append(raw_col3)
    elif raw_col3.lower() == 'negative':
        return "Negative"
    
    # 檢查 col5
    if is_valid_value(raw_col5):
        ref_values.append(raw_col5)
    
    # 檢查 col9（作為備選）
    if not ref_values and raw_col9 and is_valid_value(raw_col9):
        ref_values.append(raw_col9)
    
    return " | ".join(ref_values) if ref_values else "無"

def extract_age(raw_col4: str) -> str:
    """提取年齡資訊"""
    if not raw_col4:
        return "無"
    
    age_indicators = ['歲', '天', 'M', 'F', 'year', 'day', 'month']
    if any(indicator in raw_col4 for indicator in age_indicators):
        return raw_col4
    
    return "無"

def extract_clinical_notes(row: pd.Series) -> str:
    """提取臨床意義"""
    notes = []
    
    # 獲取所有 col >= 10 的欄位
    clinical_cols = sorted(
        [c for c in row.index if c.startswith('欄位_') and int(c.split('_')[1]) >= 10],
        key=lambda x: int(x.split('_')[1])
    )
    
    for col in clinical_cols:
        val = str(row.get(col, '')).strip()
        
        # 基本過濾
        if not is_valid_value(val):
            continue
        
        # 過濾標題行
        if any(keyword in val for keyword in ['臨床意義', '參考值']):
            continue
        
        # 必須包含中文
        if not re.search(r'[\u4e00-\u9fff]', val):
            continue
        
        notes.append(val)
    
    return "\n".join(notes) if notes else "無"

def is_garbage_row(clinical_text: str, en_name: str) -> bool:
    """檢查是否為垃圾行"""
    # D-Dimer 錯位檢查
    if "D-Dimer" in clinical_text and "D-Dimer" not in en_name:
        return True
    
    # 血型錯位檢查
    if "血型" in clinical_text and not any(word in en_name for word in ["Blood", "Type"]):
        return True
    
    return False

# ==================== 搜尋邏輯 ====================
def search_data(df: pd.DataFrame, search_term: str) -> pd.DataFrame:
    """執行搜尋並處理數據"""
    safe_term = re.escape(search_term.strip())
    
    # 建立搜尋遮罩 - 增加對欄位_3 (組套細項) 的搜尋
    mask_code = df['欄位_0'].astype(str).str.contains(safe_term, case=False, na=False)
    mask_zh = df['欄位_1'].astype(str).str.contains(safe_term, case=False, na=False)
    
    # 英文名稱使用字邊界匹配
    regex_pattern = f"(?<![a-zA-Z]){safe_term}(?![a-zA-Z])"
    mask_en = df['欄位_2'].astype(str).str.contains(regex_pattern, case=False, regex=True, na=False)
    
    # 新增：搜尋組套細項（欄位_3）
    mask_sub = df['欄位_3'].astype(str).str.contains(regex_pattern, case=False, regex=True, na=False)
    
    mask = mask_code | mask_zh | mask_en | mask_sub
    return df[mask].copy()

def process_row(row: pd.Series) -> Optional[Dict[str, str]]:
    """處理單行數據"""
    # 基本資料
    code = clean_text(row.get('欄位_0', ''), remove_newlines=True)
    zh_name = clean_text(row.get('欄位_1', ''), remove_newlines=True)
    en_name = clean_text(row.get('欄位_2', ''), remove_newlines=True)
    
    # 提取原始欄位
    raw_col3 = str(row.get('欄位_3', '')).strip()
    raw_col4 = str(row.get('欄位_4', '')).strip()
    raw_col5 = str(row.get('欄位_5', '')).strip()
    raw_col6 = str(row.get('欄位_6', '')).strip()
    raw_col9 = str(row.get('欄位_9', '')).strip()
    
    # === 組套細項處理 ===
    sub_item = "無"
    
    # 檢查 col3（組套細項通常在這）
    if raw_col3 and raw_col3 not in INVALID_VALUES:
        # 移除前面的數字編號（如 "3 WBC(10/ul)" -> "WBC(10/ul)"）
        cleaned_col3 = re.sub(r'^\d+\s+', '', raw_col3).strip()
        
        # 過濾標題行
        if 'CBC' in cleaned_col3 and '項目' in cleaned_col3:
            return None
        
        # 排除非細項值
        if cleaned_col3 not in ['血清', '血漿', '全血', '尿', 'CSF', '胸水', '腹水', '']:
            if cleaned_col3.lower() != 'negative':
                # 如果不是參考值格式，就視為細項
                if not is_reference_value(cleaned_col3):
                    sub_item = cleaned_col3
                else:
                    # 如果 col3 是參考值（如 ALT），則細項為「無」，稍後處理參考值
                    pass
    
    # === 年齡處理 ===
    age = "無"
    # 年齡通常在 col4，檢查是否包含年齡指標
    if raw_col4 and any(indicator in raw_col4 for indicator in ['歲', '天', 'M', 'F', 'year', 'day', 'month', '~', '天-']):
        age = raw_col4
    
    # === 參考值處理 ===
    ref_value = "無"
    
    # 如果 col3 是參考值（如 ALT 的情況）
    if sub_item == "無" and raw_col3 and is_reference_value(raw_col3):
        ref_value = raw_col3
    else:
        # 否則從 col5 或其他欄位找參考值
        # 優先順序：col5 > col6 > col9
        candidates = [raw_col5, raw_col6, raw_col9]
        
        for candidate in candidates:
            if not candidate or candidate in INVALID_VALUES:
                continue
            if candidate in HOSPITAL_NAMES:
                continue
            
            # 檢查是否為參考值格式
            if is_reference_value(candidate) or candidate.lower() in ['negative', 'positive']:
                if ref_value == "無":
                    ref_value = candidate
                else:
                    if candidate not in ref_value:
                        ref_value += f" | {candidate}"
                break
    
    # === 臨床意義 ===
    clinical = extract_clinical_notes(row)
    
    # 垃圾行檢查
    if is_garbage_row(clinical, en_name):
        return None
    
    # 只過濾完全空白的行
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
    
    # 顯示免責聲明
    with st.expander("📋 查看免責聲明", expanded=False):
        st.markdown(DISCLAIMER)
    
    st.markdown("---")
    
    # 載入資料
    df = load_data()
    
    if df.empty:
        st.error("❌ 資料庫是空的，請先執行 update_db.py")
        return
    
    # 搜尋介面
    search_term = st.text_input(
        "🔍 請輸入檢驗代碼或關鍵字：",
        "",
        placeholder="例如：AST, CBC, WBC, 09026...",
        help="可搜尋健保代碼、中文名稱、英文名稱或組套細項"
    )
    
    if not search_term:
        st.info("💡 請在上方輸入搜尋關鍵字開始查詢")
        return
    
    # 執行搜尋
    with st.spinner("🔍 搜尋中..."):
        result_df = search_data(df, search_term)
    
    if result_df.empty:
        st.warning("⚠️ 查無資料。")
        return
    
    # 處理數據
    display_rows = []
    for _, row in result_df.iterrows():
        processed = process_row(row)
        if processed:
            display_rows.append(processed)
    
    if not display_rows:
        st.warning("⚠️ 查無資料（有效資料過濾後為空）。")
        return
    
    # 建立最終 DataFrame 並去重
    final_df = pd.DataFrame(display_rows).drop_duplicates()
    
    # 顯示結果
    st.success(f"✅ 找到 {len(final_df)} 筆結果")
    
    st.dataframe(
        final_df,
        use_container_width=True,
        hide_index=True,
        height=600,  # 增加表格高度
        column_config={
            "健保代碼": st.column_config.TextColumn("健保代碼", width=80),
            "中文名稱": st.column_config.TextColumn("中文名稱", width=120),
            "英文名稱": st.column_config.TextColumn("英文名稱", width=150),
            "組套細項": st.column_config.TextColumn("組套細項", width=100),
            "年齡": st.column_config.TextColumn("年齡", width=80),
            "參考值": st.column_config.TextColumn("參考值", width=150),
            "臨床意義": st.column_config.TextColumn("臨床意義", width=500),  # 加大寬度
        }
    )

if __name__ == "__main__":
    main()
