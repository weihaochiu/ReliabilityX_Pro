# 20. 新增通知中心與 Telegram 整點摘要機制

- **日期**: 2026-03-30
- **狀態**: 已接受並實施

## 背景 (Context)

ReliabilityX Pro 目前已具備完整的量測流程、即時 IV/Trend 視窗、摘要 CSV 輸出，以及集中式日誌管理能力；然而，當系統發生重大錯誤、開始量測，或需要在固定時段回報目前各通道的 IV 參數時，仍缺乏一個統一且可設定的通知機制。

在本次需求提出前，系統已具備以下可利用的整合點：

1. `gui/system_config_dialog.py` 已作為系統設定分頁的集中管理器，負責建立分頁、載入設定、收集 `get_settings()` 結果並寫回 JSON 設定檔。
2. `gui/main_window.py` 已負責將 UI、`MeasureEngine`、IV Monitor、Trend Chart 串接起來，並接收 `scan_started`、`scan_finished`、`channel_measurement_finished` 等信號。
3. `core/measure_engine.py` 已作為核心量測協調者，對外提供量測生命週期信號與量測完成結果。
4. `core/log_manager.py` 已集中處理系統日誌、未捕捉例外、Qt 訊息與檔案輸出。

因此，本次變更的重點不是重新設計量測架構，而是在既有架構上新增一個**通知子系統**，讓通知功能可以：

- 透過 UI 設定 Telegram 基本參數。
- 在「開始量測」時主動推播。
- 在「重大錯誤」發生時主動告警。
- 依使用者設定的每日整點時段，自動整理目前最新的 IV 參數摘要並推播。
- 為未來 Email / LINE 等通知通道預留擴充位置。

## 根本原因分析 (Root Cause Analysis)

在需求分析過程中，確認了下列幾個根本問題：

1. **通知設定缺乏獨立責任邊界**
   - 現有系統只有 `config_settings.json`、`user_settings.json`、`hardware_map.json` 等設定檔，但沒有一個專門用來存放通知行為與通知通道參數的設定檔。
   - 若直接把 Telegram 設定塞進既有硬體或環境設定，會讓設定責任變得混雜。

2. **通知需求跨越多個事件來源，但尚無集中協調者**
   - 「開始量測」來自 `MeasureEngine.scan_started`。
   - 「每通道最新 IV 結果」來自 `channel_measurement_finished`。
   - 「重大錯誤」來自 `LogManager` 所管理的 logger 與例外攔截鏈。
   - 若將通知邏輯分散在各模組中，會使責任切割不清，並提高重複發送與後續維護成本。

3. **定時摘要需要彈性，但不適合硬編碼固定兩個時段**
   - 使用者需求不是固定 09:00 / 21:00，而是可在 UI 中選擇「每日回報次數」，並動態指定多個整點時段。
   - 這代表通知設定 UI 必須支援動態控制項，而不適合直接沿用靜態 `.ui` 表單做死。

4. **系統不應為此引入不必要的新外部依賴**
   - 現有應用程式已使用 Qt 事件循環，若再引入額外排程框架，將增加打包與維護成本。
   - Telegram 發訊本質上是簡單 HTTP POST，不一定需要額外的第三方 HTTP 套件。

## 決策 (Decision)

為解決上述問題，我們決定新增一個**通知中心 (Notification Center)**，並以 Telegram 作為第一個實作通道。具體決策如下：

1. **新增 `config/notification_settings.json` 作為通知專用設定檔**
   - 不將通知設定混入 `config_settings.json` 或 `user_settings.json`。
   - 使用單一檔案統一管理 `GENERAL`、`TELEGRAM`、`EMAIL`、`LINE` 等通知相關設定。
   - 其中 `EMAIL` 與 `LINE` 先保留結構，但暫不啟用。

2. **在 `config.py` 新增通知設定的載入/儲存 API**
   - 新增 `NOTIFICATION_SETTINGS_FILE`。
   - 新增 `load_notification_settings()` / `save_notification_settings()`。
   - 提供通知系統與設定視窗共用的預設結構。

3. **新增純 Python 的 `gui/config_tabs/notification_tab.py`**
   - 不使用 `.ui` 檔，避免動態控制項與打包資源路徑管理的額外複雜度。
   - 由 `NotificationTab` 提供：
     - Telegram 啟用開關
     - Bot Token / Chat ID 欄位
     - 重大錯誤、開始量測、每日摘要等事件勾選
     - 「每日回報次數」下拉選單
     - 依回報次數動態生成多個整點時間下拉選單
     - 測試訊息按鈕與預覽/結果區塊
   - 未來擴充 Email / LINE 時，優先沿用此分頁，而不是再開新分頁。

4. **新增 `core/notification_manager.py` 作為通知協調者**
   - `NotificationManager` 負責：
     - 載入通知設定
     - 發送 Telegram 訊息
     - 接收量測生命週期事件
     - 累積每個通道最新的量測結果
     - 依整點排程發送每日 IV 摘要
     - 監聽錯誤等級 log 並做重大錯誤通知
   - 為避免新增外部依賴：
     - Telegram HTTP 呼叫使用 Python 標準函式庫 `urllib`。
     - 定時摘要使用 Qt 的 `QTimer`，不另外引入排程框架。

5. **由 `gui/main_window.py` 負責通知子系統的生命週期管理**
   - 在 `MainWindow` 初始化時建立 `NotificationManager`。
   - 將 `MeasureEngine.scan_started` / `scan_finished` / `channel_measurement_finished` 連接到 `NotificationManager`。
   - 在使用者按下開始量測時，先將當次啟用通道資料交給 `NotificationManager`，使開始量測通知可帶出通道/專案/設備名稱。
   - 設定視窗儲存後，於 UI 層觸發通知設定重新載入。

6. **重大錯誤通知採用 logger handler 方式整合，而非分散在各模組手動呼叫**
   - `NotificationManager` 透過自訂 logging handler 訂閱 `LogManager.logger` 的錯誤事件。
   - 僅對 `ERROR` 以上等級進行 Telegram 告警。
   - 加入 cooldown 與簡單去重鍵，避免相同錯誤在短時間內重複洗版。

## 影響 (Consequences)

### 正面影響
- **通知責任明確化**：通知設定、通知邏輯、量測事件來源與 UI 分頁各自有清楚邊界。
- **符合既有依賴方向規則**：GUI 依賴 `core.notification_manager`，但 `core` 不反向依賴 GUI。
- **與現有 signal 架構自然整合**：開始量測、量測完成、錯誤告警都可透過既有事件接入。
- **擴充性提升**：日後新增 Email / LINE 時，可沿用 `notification_settings.json` 與 `NotificationTab` 的同一個框架。
- **打包風險較低**：通知設定頁採純 Python，不新增 `.ui` 檔；HTTP 與排程也不新增外部第三方依賴。
- **使用者可自行調整整點回報策略**：不再被固定於兩個時段。

### 負面影響
- **Bot Token 目前仍存於 `notification_settings.json`**
  - 這是為了先快速落地功能。
  - 後續若需要更高安全性，可再改為 Windows Credential Manager / DPAPI 等安全儲存方式。

- **定時摘要目前基於主程式執行期間的記憶體快照**
  - `NotificationManager` 使用 `channel_measurement_finished` 所收到的最新結果作為摘要來源。
  - 若程式重啟且尚未有新的量測完成事件，則摘要內容可能為空或僅含啟動後的結果。

- **通知發送仍依賴外部網路與 Telegram Bot API 可用性**
  - 若網路中斷或 Telegram API 回應失敗，通知將無法送達。
  - 因此測試訊息功能與錯誤回報結果顯示仍然重要。
