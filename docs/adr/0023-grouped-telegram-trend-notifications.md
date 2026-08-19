# ADR-0023: Telegram 定時摘要與趨勢圖改為支援 active scope 分組寄送

- **狀態**: Accepted
- **日期**: 2026-04-01
- **版本**: v5
- **決策者**: ReliabilityX Pro 維護者

## 背景

Trend Chart Window 已支援依 `使用者 / 專案 / 電池代號` 篩選與顯示曲線，但 Telegram 定時通知仍只有「整體」模式，存在以下問題：

1. **文字摘要只發整體**  
   `NotificationManager` 先前直接用整個 `latest_channel_results` 組裝一則文字摘要，無法區分不同使用者或專案。

2. **趨勢圖只畫整體**  
   `NotificationManager._dispatch_trend_images()` 先前直接將整包 `trend_history` 丟給 renderer，因此不同專案會混在同一張圖。

3. **通知與 UI 使用不同分組邏輯**  
   Trend window 的 `series_key / group_label` 規則原本寫在 `gui/trend_chart_window.py` 內部，`NotificationManager` 無法在不違反分層規則的情況下直接重用。

4. **排程通知沒有 active scope 邊界**  
   即使需求只想寄出「目前正在執行中的專案」，排程摘要仍可能把其他已停止或無關 scope 的資料一起送出去。

## 決策

採用以下設計：

### 1. 新增 `core/trend_scope_utils.py`
將 Trend 與 Notification 共用的範圍規則抽到 core 層，提供：

- `make_series_key()`
- `make_display_label()`
- `make_group_label()`
- `group_entries()`
- `annotate_scope_entries()`
- `filter_records_to_active_scope()`

這讓 `TrendChartWindow`、`NotificationManager` 與 `TrendSnapshotRenderer` 都能使用同一套 key/label/group 規則。

### 2. 通知設定新增 `trend_group_mode`
`notification_settings.json` 新增：

- `overall`
- `user_project`

本次刻意**只保留這兩種模式**，避免設定介面過於複雜。

### 3. 定時摘要與趨勢圖都只看 active scope
`MainWindow.on_start_clicked()` 既有的 `active_channels_data` 會同時送給：

- `TrendChartWindow.set_active_scope(...)`
- `NotificationManager.set_pending_scan_request(...)`

`NotificationManager` 在排程摘要與趨勢圖推播時，會先把資料過濾到 active scope，再依 `trend_group_mode` 決定是否分組。

### 4. 文字摘要與趨勢圖一起分組
排程時間到時：

1. 先送出該 group 的文字摘要
2. 再送出該 group 的趨勢圖（若啟用）

不再採用「有圖就不送文字」的互斥模式。

### 5. Renderer 改用 `series_key`
`TrendSnapshotRenderer` 不再僅依賴 `device_name` 區分曲線，而是改用 `series_key`。  
這可避免同一 project 內若出現相同 `device_name`，圖上曲線被錯誤合併。

## 影響

### 正面影響

- Telegram 定時摘要與圖表終於可對齊 Trend window 的使用者/專案視角。
- 排程通知只會寄送**目前正在執行中的 active scope**，不再混入其他專案。
- Notification 與 Trend window 共用同一套範圍規則，降低未來維護時的邏輯漂移風險。
- Renderer 的曲線識別更穩定，減少同名 `device_name` 的錯誤合併。

### 負面影響 / 代價

- 新增一個 core helper 檔，模組數量略增。
- `NotificationManager` 的流程更複雜，需要同時處理 group mode、active scope 與 schedule dispatch。
- 若未來要擴充更多 group mode（例如只依 user、只依 project、依 device），仍需再補 UI 與 normalize 規則。

## 未採用方案

### 方案 A：只在 `NotificationManager` 內重寫分組邏輯
未採用。  
原因是這會讓通知端與 Trend window 各自維護一份 `series_key / group_label` 規則，長期容易不一致。

### 方案 C：直接讓 `NotificationManager` 讀取 `TrendChartWindow` 狀態
未採用。  
原因是這會讓 core 反向依賴 GUI，違反目前架構中的依賴方向規則。

## 實作摘要

本次修改涉及：

- `core/trend_scope_utils.py`
- `core/notification_manager.py`
- `config.py`
- `gui/config_tabs/notification_tab.py`
- `gui/trend_chart_window.py`
- `gui/trend_snapshot_renderer.py`
- `docs/ARCHITECTURE.md`
- `docs/CODEBASE_MAP.md`

## 驗證重點

1. 啟用 `trend_group_mode = overall` 時，定時摘要與圖表應維持整體模式。
2. 啟用 `trend_group_mode = user_project` 時，應按 `user + project` 分組寄送。
3. 分組寄送時，文字與圖都不得混入 active scope 外的資料。
4. 同一 group 內若有多條曲線，renderer 應以 `series_key` 正確分線，不因同名 `device_name` 而合併。
5. 掃描結束後 active scope 清空，後續排程不應再持續寄送已結束專案的 grouped 摘要。
