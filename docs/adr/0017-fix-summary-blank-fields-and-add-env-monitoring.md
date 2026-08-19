17. 修正 Summary 欄位空白與新增溫濕度監控功能
日期: 2026-03-26

狀態: 已接受並實施

背景 (Context)
在目前的鈣鈦礦太陽能電池量測系統中，發現兩個主要問題：

數據遺失：Summary_report.csv 中的電性參數欄位出現大量空白。經查是因為 iv_curve_logger.py 產出的分析結果鍵值（Key）與 summary_logger.py 預期讀取的鍵值不匹配（例如 Forward_Raw 與 F_Raw 的差異）。

環境監控需求：原本的溫度與濕度資訊僅記錄在 CSV 檔案頂部的靜態資訊區。使用者需要能夠隨時監測每個量測點的溫濕度數值，以便繪製趨勢圖（Trend Chart）來分析環境穩定性對元件性能的影響。

根本原因分析 (Root Cause Analysis)
命名不一致：程式碼中對於掃描方向與數據類型的命名邏輯分散，導致 results 字典在傳遞過程中，SummaryLogger 找不到對應的標籤，進而填入空值。

資料結構限制：舊有的資料結構將環境資訊視為「量測前的一次性快照」，並未將其納入「每行量測數據」的動態欄位中，導致無法進行時間序列的環境追蹤。

Template 格式不符：原始輸出的欄位順序與使用者要求的 Excel 報表格式（Template）存在落差，缺乏必要的空欄位間隔，影響閱讀與後續數據處理。

決策 (Decision)
為了提升數據的完整性與分析價值，我們決定採取以下修改措施：

統一 Key 值命名規範：

將所有分析結果統一命名為 Forward_Raw、Reversed_Raw、Forward_Corr、Reversed_Corr。

確保 iv_curve_logger 與 summary_logger 使用相同的字典鍵值進行讀寫，徹底解決空白欄位問題。

重新規劃環境數據存放位置：

修改 Summary_report.csv 的標頭結構，將 Temp(oC) 與 Hum(RH%) 從檔案頂部移除，移至數據行末端（位於 Raw_Data_File 欄位之前）。

在每次量測記錄時，同步寫入當下的感測器讀值。

完整對齊 Template 格式：

增加電性參數至 10 個核心項（含 Pmpp, Vmpp, Impp, Jmpp 等）。

在 F_Raw、R_Raw、F_Corr、R_Corr 數據組之間插入空欄位，以符合使用者提供的 Excel 視覺間隔需求。

代碼優化 (Refactoring)：

使用迴圈處理重複的數據組合邏輯，雖然縮減了代碼行數，但大幅提升了欄位對齊的準確性與程式的可維護性。

後果 (Consequences)
正面影響：

Summary_report 現在包含完整的環境趨勢數據，使用者可直接繪製 PCE 隨環境變化的趨勢圖。

解決了數據遺失問題，確保所有計算結果（Raw & Corrected）都能正確記錄。

報表格式現在完全符合實驗室要求的 Template，無需手動調整 Excel 格式。

負面影響：

若主程式未正確傳遞感測器數值，溫濕度欄位將顯示 N/A（已在程式碼中加入防錯機制）。

修改後的 CSV 標頭與舊版數據檔案不相容，建議新實驗使用新的 Summary 檔案。