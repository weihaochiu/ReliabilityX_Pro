# ADR-0022：以 Channel Boundary Graceful Stop 取代立即中斷，並新增 Telegram 停止/完成通知

- **日期**: 2026-04-01
- **狀態**: 已接受並實施

## 背景 (Context)

原本系統的「停止量測」流程是由 `gui/main_window.py` 直接發送 `request_stop_scan` 給 `core/measure_engine.py`，而 `MeasureEngine.stop_scan_cycle()` 會立即將 `is_running=False`。

此設計有三個問題：

1. **停止語意不符合科研量測流程**
   - 使用者真正需要的不是「立刻砍掉當前 IV」，而是「讓目前元件完成正掃與逆掃，之後不再量下一顆」。
   - 立即中斷容易留下半套 IV 曲線、不完整的 summary，以及難以判讀的 trend 資料。

2. **操作風險高**
   - 停止量測原本沒有 double confirm，使用者誤觸風險較高。
   - 對於長時間 reliability 測試來說，誤觸停止的代價偏高。

3. **通知語意不完整**
   - `core/notification_manager.py` 原本只有開始通知與重大錯誤通知。
   - `on_scan_finished()` 只清空 `pending_scan_channels`，無法區分「正常完成」與「依使用者要求停止」。

## 決策 (Decision)

我們決定將停止流程重構為 **Graceful Stop at Channel Boundary**，並同步補齊通知與日誌設計。

### 1. 停止量測改為安全邊界停止

- `MainWindow.on_stop_clicked()` 先顯示 double confirm。
- 使用者兩次確認後，才發出 `request_stop_scan`。
- `MeasureEngine.stop_scan_cycle()` **不再**直接將 `is_running=False`，而是僅設定：
  - `stop_requested=True`
  - `stop_request_reason="user_requested_after_current_channel"`
- `MeasureEngine` 允許目前正在量測的 channel 完整完成：
  - 正掃
  - 逆掃
  - 分析
  - 存檔
  - `channel_measurement_finished`
- 回到 channel 迴圈邊界時，檢查 `stop_requested`，若為真則於**下一顆開始前**停止。

### 2. 將 scan_finished 升級為攜帶上下文的訊號

- `scan_finished` 由無參數訊號改為 `pyqtSignal(dict)`。
- payload 至少包含：
  - `finish_reason`
  - `finish_time`
  - `last_finished_channel_id`
  - `stop_requested`
  - `stop_request_reason`
  - `completed_channel_count`
  - `remaining_channel_count`

### 3. 新增 Telegram 停止/完成通知

- `NotificationManager.on_scan_finished(dict)` 依 `finish_reason` 分流：
  - `stopped_after_current_channel` → 發送「停止量測」通知
  - `completed` → 發送「量測完成」通知
- 「開始量測」通知邏輯維持既有設計。
- 重大錯誤通知仍由 log handler 監聽 `ERROR / CRITICAL` 事件處理。

### 4. 補強日誌可觀測性

新增 UI 與 Engine 停止流程相關 log，至少包含：

- 使用者按下停止按鈕
- 使用者取消第一層確認
- 使用者取消第二層確認
- 使用者確認 graceful stop
- Engine 收到 graceful stop request
- 當前 channel 正掃完成 / 逆掃完成
- 當前 channel 已完成，依請求不再進入下一顆
- 掃描最終結束原因

## 影響 (Consequences)

### 正面影響

1. **停止語意更符合科研量測邏輯**
   - 避免留下半套 IV 曲線與不完整 summary。
   - 使用者可明確預期停止發生於安全邊界，而非任意點位。

2. **系統行為更可追蹤**
   - UI log、Engine log、Telegram 通知三者的語意一致。
   - 之後在 debug 或稽核時，可清楚區分：
     - 正常完成
     - 使用者要求完成當前元件後停止
     - 異常中止

3. **降低誤觸停止風險**
   - double confirm 讓高風險操作更安全。

### 負面影響

1. **停止不再是瞬時行為**
   - 使用者按下停止後，需要等待當前元件的正逆掃完成。
   - 若單顆 channel 的 delay time 較長，體感停止延遲會較明顯。

2. **訊號與相依模組需要同步更新**
   - `scan_finished` 的 signature 變更要求 `MainWindow` 與 `NotificationManager` 一併調整。
   - 若其他模組仍假設 `scan_finished` 無參數，需同步修正。

## 實施摘要 (Implementation Summary)

- **`gui/main_window.py`**
  - 新增 double confirm。
  - 停止按鈕改成送出 graceful stop request。
  - 新增 UI stop/start log。
  - 接收 `scan_finished(dict)`。

- **`core/measure_engine.py`**
  - 新增 `stop_requested` / `stop_request_reason` / `last_finish_reason` / `last_finished_channel_id`。
  - `stop_scan_cycle()` 改為只登記停止請求。
  - `start_scan_cycle()` 在 channel 邊界檢查並停止。
  - `scan_finished` 改為回傳結束上下文。

- **`core/notification_manager.py`**
  - 保留開始通知。
  - 新增停止量測通知。
  - 新增正常完成通知。
  - 依 `finish_reason` 分流內容與文案。
