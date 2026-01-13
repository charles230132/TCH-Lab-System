import requests
import pdfplumber
import pandas as pd
import sqlite3
import urllib3
import os
from datetime import datetime

# 🔇 忽略安全憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PDF_URL = "https://www-ws.gov.taipei/Download.ashx?u=LzAwMS9VcGxvYWQvNTEwL3JlbGZpbGUvMjUyMTYvODExOTIzNC80MjkzNWE2MS1mOTZmLTRmMjEtODUzYS01NmRlZTY3MmU0M2YucGRm&n=VENILVFQLTcuMi0xLSgxKeaOoeaqouaJi%2bWGii5wZGY%3d&icon=..pdf"
DB_NAME = "lab_test.db"

def update_job():
    print(f"[{datetime.now()}] 🤖 GitHub Action 機器人啟動！開始更新資料...")
    
    pdf_filename = "hospital_manual.pdf"
    
    # 下載
    try:
        response = requests.get(PDF_URL, timeout=60, verify=False) 
        with open(pdf_filename, 'wb') as f:
            f.write(response.content)
        print("✅ PDF 下載完成。")
    except Exception as e:
        print(f"❌ 下載失敗: {e}")
        return

    all_data = []
    
    # 解析第 68-101 頁（索引 67-100）
    try:
        with pdfplumber.open(pdf_filename) as pdf:
            start_page_index = 67  # 第 68 頁
            end_page_index = 101   # 第 101 頁
            total_pages = len(pdf.pages)
            
            print(f"📄 PDF 總頁數: {total_pages}")
            print(f"📖 解析範圍: 第 68-101 頁 (索引 {start_page_index}-{end_page_index})")
            
            if start_page_index < total_pages:
                # 取得指定頁面範圍
                target_pages = pdf.pages[start_page_index:min(end_page_index + 1, total_pages)]
                print(f"✓ 實際解析頁數: {len(target_pages)}")
                
                for idx, page in enumerate(target_pages, start=start_page_index + 1):
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            if not table: 
                                continue
                            for row in table:
                                clean_row = [str(cell).strip() if cell is not None else "" for cell in row]
                                all_data.append(clean_row)
                        print(f"  ✓ 第 {idx + 1} 頁: 解析成功")
                    else:
                        print(f"  ⚠ 第 {idx + 1} 頁: 無表格")
    except Exception as e:
        print(f"❌ 解析錯誤: {e}")
        return

    # 存檔
    if all_data:
        try:
            df = pd.DataFrame(all_data)
            df = df.replace(r'^\s*$', None, regex=True)
            df = df.ffill()
            df.columns = [f"欄位_{i}" for i in range(len(df.columns))]
            
            conn = sqlite3.connect(DB_NAME)
            df.to_sql('tests', conn, if_exists='replace', index=False)
            conn.close()
            print(f"🎉 資料庫更新成功！共 {len(df)} 筆。")
        except Exception as e:
            print(f"❌ 資料庫錯誤: {e}")
    else:
        print("⚠️ 未抓到資料。")

if __name__ == "__main__":
    update_job()
