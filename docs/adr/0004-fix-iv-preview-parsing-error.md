# 4. 修正 IV 曲線預覽功能的 CSV 解析錯誤

- **日期**: 2026-03-16
- **狀態**: 已接受並實施

## 背景 (Context)

在實現了「IV 曲線預覽懸浮視窗」功能後 (見 ADR-0003)，發現當滑鼠懸停在數據點上時，應用程式日誌會拋出大量 `Error tokenizing data. C error: Expected 12 fields in line 34, saw 19` 的錯誤，導致預覽視窗無法顯示。

此錯誤發生在 `trend_chart_window.py` 的 `_on_mouse_moved` 函式中，當中的 `pandas.read_csv` 指令在嘗試解析 `..._IV curve.csv` 檔案時失敗。

## 根本原因分析 (Root Cause Analysis)

`iv_curve_logger.py` 生成的 CSV 檔案包含一個複雜的結構。在主要的 19 欄位數據區塊之前，存在一個只有 12 個欄位的「分析摘要」標頭行。**此行沒有被 `#` 符號註解**。

因此，`pd.read_csv(..., comment='#', header=0)` 的解析邏輯發生了混淆：
1.  它跳過了所有以 `#` 開頭的元數據行。
2.  它遇到的第一個**非註解行**是那個只有 12 個欄位的分析摘要標頭，因此 `pandas` 將其誤認為是整個檔案的數據標頭 (header)。
3.  當解析器繼續往下讀，遇到真正的、包含 19 個欄位的數據行時，欄位數量不匹配，從而觸發了 `Error tokenizing data` 錯誤。

## 決策 (Decision)

為了在不修改 `iv_curve_logger.py` 現有輸出格式（避免影響已存檔的數據）的前提下修正此錯誤，我們決定讓**讀取端**變得更加健壯和明確。

具體決策如下：
1.  **修改 `trend_chart_window.py`**：在 `_on_mouse_moved` 函式中，對 `pd.read_csv` 的呼叫進行強化。
2.  **明確定義欄位**：
    - 在 `trend_chart_window.py` 頂層定義一個包含 19 個字串的列表 `IV_DATA_COLUMN_NAMES`，該列表與 `..._IV curve.csv` 檔案中數據區塊的 19 個欄位嚴格對應。
    - 修改 `pd.read_csv` 指令，加入兩個關鍵參數：
        - `header=None`：指示 `pandas` 不要嘗試自動偵測任何標頭行。
        - `names=IV_DATA_COLUMN_NAMES`：指示 `pandas` 使用我們提供的列表作為欄位名稱。
3.  **更新數據提取邏輯**：相應地，更新後續從 DataFrame 中提取數據的程式碼，使用 `IV_DATA_COLUMN_NAMES` 中定義的、明確的欄位名稱 (如 `'fwd_v_corr'`)，而不是依賴 `pandas` 自動生成的名稱 (如 `'Voltage_Corr(V).1'`)。

## 影響 (Consequences)

### 正面影響
- **錯誤修正**：徹底解決了 `Error tokenizing data` 的問題，讓 IV 曲線預覽功能恢復正常。
- **健壯性提升**：新的讀取邏輯不再依賴於 CSV 檔案中標頭行的位置和內容，只要數據區塊的 19 個欄位結構不變，就能穩定解析。這使得程式對未來可能在元數據區塊發生的格式微調具有更強的抵抗力。
- **兼容性**：此修正對所有已生成的、包含此格式問題的舊 CSV 檔案都有效。

### 負面影響
- 無明顯的負面影響。此修正是對讀取邏輯的強化，目標精準，不涉及對其他模組的修改。
