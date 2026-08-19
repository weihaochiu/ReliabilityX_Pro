# 0021. 重構 Trend Monitor 的範圍選擇、群組圖例與環境子圖

- **日期**: 2026-03-31
- **狀態**: 已接受並實施

## 背景 (Context)

原本的 Trend Monitor 採用單一主圖 + 右側環境雙 Y 軸的設計，左側裝置選取也僅以扁平 `device_name` 清單呈現。這在單一專案、少量通道時仍可使用，但在下列情境會快速變得難以操作：

1. 需要同時比較不同使用者 / 不同專案底下的電池。
2. 單一專案包含多顆 cell，圖例中反覆出現相同的 `user / project` 字樣，閱讀負擔高。
3. Tooltip 只顯示 `device_name` 與單點 IV 指標，無法明確辨識該點屬於哪個使用者、哪個專案、哪個 channel。
4. Tooltip 的命中規則僅以 X 軸最近點判斷，導致滑鼠距離點位仍很遠時也可能彈出提示，造成辨識歧義。
5. 環境資料與主指標以雙 Y 軸疊圖時，在多條曲線同時顯示的情況下可讀性不佳。

此外，環境資料硬體/資料流尚未正式導入，若繼續以缺值預設 0 的方式畫線，會產生誤導性的假環境曲線。

## 根本原因分析 (Root Cause Analysis)

問題的核心不在於 `MeasureEngine` 的量測流程，而在於 Trend Monitor 的 UI 模型過於扁平：

- 左側只知道 `device_name`，不知道 `user / project / ch_id` 的階層。
- 圖表元件同時承擔曲線呈現與環境疊圖，導致顯示邏輯難以擴充。
- Tooltip 命中規則使用 1D X 軸距離近似，沒有以真正的點位距離做判斷。
- `TrendChartWindow` 沒有區分「全部已接收歷史資料」與「目前正在執行的 active scope」。

## 決策 (Decision)

我們決定在 **不改變量測排程與 `MeasureEngine` 核心職責** 的前提下，於 UI 層重構 Trend Monitor。

### 1. 將 active scope 與 all_data_history 分離

- `MainWindow.on_start_clicked()` 在送出 `request_start_scan(active_channels_data)` 前，先同步呼叫 `TrendChartWindow.set_active_scope(active_channels_data)`。
- `TrendChartWindow` 內部維護：
  - `all_data_history`: 已收到的所有量測結果
  - `active_scope`: 本輪正在執行、可出現在篩選下拉中的候選曲線
- 當掃描結束時，由 `MainWindow` 透過 `scan_finished` 將 Trend 視窗的 active scope 清空。

### 2. 左側控制區改為三層範圍選擇

將原本扁平的 device checkbox 清單重構為：

- 使用者下拉選單
- 專案下拉選單
- 電池代號 checkbox 清單

這些下拉與清單只根據 **active scope** 顯示，避免把已結束的歷史通道帶進操作面板。

### 3. grouped legend 改為左側樹狀分組面板

不再把 `user / project / cell` 直接重複拼接成平面字串，而改成：

- Top-level: `user / project`
- Child item: `device_name (CHxx)`

且只列出：
- 目前篩選後
- 且目前實際可見的曲線

### 4. 環境資料改為獨立子圖

放棄原本的雙 Y 軸疊圖，改成：

- 上方主圖：顯示 PCE / Voc / Jsc / FF 等主指標
- 下方環境子圖：顯示 Temp / Hum
- 兩圖共用 X 軸
- 顯示環境時採 **2/3 主圖 + 1/3 環境子圖**
- 未顯示環境時，主圖吃滿 100% 高度

### 5. Tooltip 改為精準命中與完整階層資訊

Tooltip 顯示內容改為：

- `User / Project / Device / Channel`
- `PCE / Voc / Jsc / FF`
- `Temp / Hum`（若尚未導入則顯示 `—`）

Tooltip 命中規則改為：
- 以主圖中資料點的**實際畫面距離**判定
- 只有滑鼠明確靠近資料點時才顯示
- 不再僅依 X 軸最近點推斷

### 6. 環境資料先保留框架，不用假值補線

由於環境資料尚未正式導入：

- 先完成環境子圖的 UI 與資料切分邏輯
- 若尚無 `temp / hum`，則不畫假 0 線
- 子圖顯示「環境資料尚未導入」佔位訊息
- `MeasureEngine` 在 summary result 中預留 `timestamp / temp / hum` 欄位，方便未來接值

## 影響 (Consequences)

### 正面影響

- **操作性提升**：使用者可直接以 `使用者 / 專案 / 電池代號` 快速縮小比較範圍。
- **閱讀性提升**：grouped legend 只顯示一次 `user / project`，避免同專案多顆 cell 時重複標頭。
- **辨識性提升**：Tooltip 可明確指出資料點屬於哪位使用者、哪個專案、哪顆 device、哪個 channel。
- **可讀性提升**：環境資料與主指標分圖顯示後，多曲線比較時不再被雙 Y 軸壓縮與干擾。
- **擴充性提升**：先完成環境子圖框架與 result metadata 預留，未來接入真實環境資料時不需再次重構整個 UI。
- **架構一致性**：本次修改完全維持既有分層方向；`MeasureEngine` 不依賴 `gui/`，篩選與 grouped legend 完全留在 UI 層處理。

### 負面影響

- **Trend UI 複雜度上升**：`TrendChartWindow`、`TrendDeviceListWidget`、`TrendPlotWidget` 的責任與程式量都增加。
- **圖表匯出邏輯變更**：由於畫面不再是單一 PlotItem，匯圖方式改為擷取整個 TrendPlotWidget，而非只匯出單一 pyqtgraph plot item。
- **active scope 為即時集合**：掃描結束後清空 scope 的設計，使得左側篩選器只面向「目前執行中」的電池；若未來需要支援「已結束 run 的歷史重播」，需再額外設計歷史模式。
