
# 0022. 以立即停止旗標修正停止量測延遲，並新增開始 / 停止 Telegram 通知

- **日期**: 2026-04-01
- **狀態**: 已接受並實施

## 背景 (Context)

原本的停止量測流程為：

`ControlPanel -> MainWindow.request_stop_scan -> MeasureEngine.stop_scan_cycle()`

此流程完全依賴 Qt queued signal 將 `stop_scan_cycle()` 排入 `MeasureEngine` 所在的 worker thread。  
然而 `MeasureEngine.start_scan_cycle()` 本身是一個長時間執行的 slot，內部持續執行：

- `while` 掃描迴圈
- 單通道量測流程
- `_interruptible_sleep()`
- `SMUDriver.read_vi()` 的 VISA query
- `RelayDriver` 的 serial command / retry / timeout

當 worker thread 被這些 blocking 操作佔住時，queued stop slot 可能長時間排不到執行，導致：

1. 使用者按下「停止量測」後沒有即時反應。
2. `stop_scan_cycle()` 中的停止 log 也不會立刻出現。
3. Telegram 只有開始通知，沒有停止 / 完成通知。
4. UI 與通知系統無法區分「正常完成」與「使用者中止」。

## 決策 (Decision)

### 1. 在 `MeasureEngine` 中新增立即停止旗標

我們新增 `MeasureEngine.request_stop_immediately(source)`，其職責只有：

- 設下 thread-safe stop flag
- 將 `is_running` 標示為 `False`
- 記錄 stop source 與 stop reason
- 不執行任何耗時硬體操作

`start_scan_cycle()`、`measure_single_channel()`、`scan_sequence()` 與 `_interruptible_sleep()` 會持續檢查此 stop flag。

### 2. 保留 queued stop slot 作為補強，而非唯一入口

`MainWindow.on_stop_clicked()` 改成雙路徑：

1. 先直接呼叫 `engine.request_stop_immediately("UI_STOP_BUTTON")`
2. 再補送 `request_stop_scan.emit()`

如此一來，停止請求是否生效不再依賴 worker thread 先有空處理 queued slot；  
而 `stop_scan_cycle()` 則保留作為補強與記錄用途。

### 3. 補齊 UI 層開始 / 停止操作日誌

`MainWindow` 在 `on_start_clicked()` 與 `on_stop_clicked()` 會立即寫入 UI 層 log，改善可觀測性，使使用者按下按鈕的當下就能在 log 視窗中看見紀錄。

### 4. 在 `MeasureEngine` 中新增量測結束上下文

我們新增 `last_scan_finish_context`，於 `scan_finished.emit()` 前寫入：

- `reason`
- `message`
- `requested_by_user`
- `stop_source`
- `started_at`
- `finished_at`
- `channel_count`
- `channels`

其用途是讓 UI 與通知系統能夠在 `scan_finished` 當下辨識：

- 正常完成
- 使用者手動停止
- 異常中止
- 未成功啟動

### 5. 新增開始 / 停止 Telegram 通知

`NotificationManager` 保留原有開始通知，並在 `on_scan_finished()` 中讀取 `engine.last_scan_finish_context`，依狀態發送：

- `ReliabilityX 停止量測`
- `ReliabilityX 量測完成`
- `ReliabilityX 量測中止`
- `ReliabilityX 量測結束`

### 6. 降低 driver 對 stop latency 的放大效應

#### SMU Driver
- 將 VISA timeout 預設縮短。
- 發生 `VisaIOError` 時，不在 driver 內做同步自動重連。
- 通訊錯誤後關閉連線，交由後續硬體初始化流程處理。

#### Relay Driver
- 縮短 serial command timeout。
- 降低 `_send_command()` 重試成本。
- 修正 `WARNING` log level 路由。

## 影響 (Consequences)

### 正面影響

- **停止量測回應顯著改善**：停止旗標可由 UI thread 立即設下，不再完全依賴 queued stop slot。
- **使用者可觀測性提升**：開始與停止按鈕的操作在 UI 當下就會留下 log。
- **通知語意更完整**：Telegram 不再只有開始通知，也能區分停止、完成與異常中止。
- **結束狀態一致化**：`last_scan_finish_context` 讓 UI、通知、後續擴充功能都能共用同一份結束狀態資料。
- **降低 driver 對 stop latency 的放大效應**：較短的 timeout 與較低的 retry 成本可減少 worker thread 長時間被 driver 卡住的機率。

### 代價與限制

- **仍非硬即時停止**：若程式當下已卡在單次 VISA query 或單次 serial read，仍需等待該次 I/O timeout 結束後才會跳出；本次修改是顯著降低上限，而非完全消除 blocking I/O。
- **通知設定頁相容策略**：core 端已支援 `notify_on_measurement_stop`，但若 UI 設定頁尚未新增此欄位，會暫時回退沿用 `notify_on_measurement_start` 作為 stop/end 通知開關。
- **`MeasureEngine` 仍偏大型**：本次修正聚焦於 stop path、通知與 driver latency，尚未完成更大規模的職責拆分。
