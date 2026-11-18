# 陽明院區檢驗科採檢查詢

以使用者指定的115年採檢手冊PDF提供ICU採檢快查及全文、參考值原頁查詢。

## 資料與顯示原則

- 主資料是 `data/manual115.pdf`，共105頁。來源檔名及SHA256記錄於 `data/source_manifest.json`。
- 品牌為「臺北市立聯合醫院陽明院區檢驗科」。原手冊頁首為中興院區；原頁保留，不把其他院區資料改名為陽明已核定內容。
- 六項ICU快查採用已完成程式、Claude及Codex核對的論點；共30項通過論點的追溯表在 `data/verified_claims.json`，每項標示來源頁碼。
- 成人血液培養量另列CDC外部指引補充，保留「範例目標」與「以現用血瓶規格確認」的限制。不能把手冊第25頁的6–20mL（每瓶）直接當作成人每瓶通則。
- 參考值、年齡、性別、院區與量測不確定度以原始表格頁面呈現，不再用固定位置猜欄位，也不按項目名稱刪掉不同族群的列。
- 其他檢驗項目皆可全文檢索並開啟原頁，包含完整表格及臨床意義。原頁屬直接來源檢視，不宣稱所有來源段落均已逐條完成語意核對。
- 不以Git checkout或伺服器檔案時間充當內容修訂日期。

## 執行

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 更新資料

明確取得並核對新版PDF後，才重新產生來源索引：

```powershell
python build_source_index.py '採檢手冊.pdf'
python -m pytest -q
```

更新快查規範時須同步完成使用者要求的三重核對及追溯表，不能只換PDF便沿用不相符的快查內容。

GitHub Actions已改成唯讀驗證，移除每10天抓取網站並覆寫資料庫的排程。舊的SQLite資料與更新腳本不再供新程式使用；歷史版本仍可由Git查回。

## 驗證

```powershell
python -m pytest -q
```

驗證來源雜湊、105頁全文一致、中英文別名、全形代碼、參考值原頁完整性，以及實際Streamlit搜尋與原頁開啟流程。桌面及390px手機畫面另以瀏覽器檢視。
