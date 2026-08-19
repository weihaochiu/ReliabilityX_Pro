# ADR-0019: 強化日誌系統穩定性，並導入 Session / Part 分檔機制

- **日期**: 2026-03-27
- **狀態**: 已接受

## 背景 (Context)

目前系統的 `log_manager.py` 原始設計是在程式啟動時，以 `log_YYYYMMDD.txt` 產生日誌檔名，並透過單一 `logging.FileHandler` 持續寫入。這種做法有兩個實際問題。第一，同一天若重新啟動多次程式，不同次啟動的日誌會被混寫到同一個檔案中。第二，若單次穩定性量測連續執行數天或數週，所有內容都會持續累積在同一個文字檔內，造成單檔過大、難以檢索與追查。

除此之外，先前的日誌機制也在關閉流程中暴露出穩定性風險。`log_manager.py` 會將 `sys.stderr` 重導向到 logger，而在 logger handler、Qt 訊息或關閉程序失敗時，錯誤處理流程可能再次把訊息打回 `stderr`，形成 `logging -> stderr -> logger` 的遞迴鏈。這正是先前發生 `--- Logging error ---` 與 `WinError 233` 類型問題的根本背景：在關閉階段，logger、stream、UI signal 與 stderr redirect 的生命週期沒有被安全切開，導致收尾期間的例外處理互相回捲。

綜合考量後，我們認為日誌系統必須同時處理兩類問題：一是**關閉流程與錯誤處理的穩定性**，二是**長時間實驗下的日誌檔案生命週期管理**。因此，本次調整不再只是局部修補單一錯誤，而是將 `log_manager.py` 一次性重構為更安全、可長時間運作、且更容易追蹤單次啟動歷程的日誌架構。

## 決策 (Decision)

我們決定重構 `log_manager.py`，同時解決日誌遞迴錯誤與長時間執行的檔名管理問題，具體實施如下：

1. **強化 stderr redirect 的防遞迴保護**
   - 保留 `sys.stderr` 導入 logger 的能力，但重寫 `_StderrToLogger`，加入 `_disabled`、`_in_write` 與 lock 保護。
   - 當 logger 已進入錯誤處理、stream 失效、或發生 `OSError / ValueError` 時，redirector 會停止再寫回 logger，以切斷 `logging -> stderr -> logger` 的遞迴鏈。
   - 在必要時仍盡可能保留原始 console 輸出，避免除錯資訊完全消失。

2. **調整 shutdown 順序，避免關閉流程互相踩踏**
   - 在 `shutdown()` 中，先標記 `_is_shutting_down`，再停用 `_stderr_redirector`，接著先恢復 `sys.stderr`、`sys.excepthook` 與 `threading.excepthook`，最後才 flush / close handlers。
   - 不再在 shutdown 階段用會回碰 redirector 的方式強制 flush，避免收尾期間再次觸發 logging 連鎖錯誤。

3. **將 GUI signal 與 logger 呼叫改為安全路徑**
   - 新增 `_safe_emit()`，在 UI 已進入關閉或 QObject 不可用時，避免 `log_signal.emit(...)` 再拋出例外。
   - 新增 `_safe_logger_call()`，在 handler 或 stream 已失效時，改以 fallback 方式寫回原始 stderr，而不是再二次呼叫同一套 logging 鏈。

4. **抑制 logging framework 自身的二次錯誤輸出**
   - 在 runtime hook 安裝流程中設定 `logging.raiseExceptions = False`，避免 Python logging 在 handler emit 失敗時，又把內部 traceback 打到 `stderr`，進一步放大錯誤風暴。

5. **改為「每次啟動一個 session 檔名」**
   - 不再固定沿用單一 `log_YYYYMMDD.txt`。
   - 啟動時先掃描當日既有日誌，為本次執行分配唯一檔名：
     - 第一次啟動：`log_YYYYMMDD.txt`
     - 第二次啟動：`log_YYYYMMDD_02.txt`
     - 第三次啟動：`log_YYYYMMDD_03.txt`

6. **同一個 session 內改用按大小自動切 part**
   - 將原本單純的 `FileHandler` 改為 `RotatingFileHandler`。
   - 以 `mode="w"` 確保每次啟動都是從空白檔開始。
   - 當單一 session 檔案超過設定大小後，自動切出後續 part 檔。

7. **在啟動時額外寫入 session 基本資訊**
   - 在建立 logger 後，主動記錄本次 session 的檔名、單檔大小上限與 part 保留數量，讓後續追查時可以直接從 log 開頭確認該次執行的日誌策略。

## 影響 (Consequences)

### 正面影響
- **關閉流程穩定性提升**：透過 stderr redirect 防遞迴、`_safe_logger_call()`、`_safe_emit()` 與 shutdown 順序調整，顯著降低 `--- Logging error ---` 與 `WinError 233` 類型問題再次發生的機率。
- **不同次啟動的日誌清楚分離**：同一天多次啟動時，日誌將分散到不同的 session 檔案中，不再混在同一個 `log_YYYYMMDD.txt` 裡。
- **長時間穩定性實驗更容易維護**：單一 session 過大時會自動切 part，避免單一文字檔持續膨脹。
- **保留既有使用習慣**：仍維持 `log_YYYYMMDD...` 的檔名風格。

### 負面影響
- **日誌檔案數量會增加**：同一天多次啟動、或長時間執行後切出多個 part，資料夾中的日誌數量將明顯變多。
- **檔名規則與輪替邏輯較複雜**：現在需要額外維護 session 編號與 part 命名規則，實作複雜度上升。
- **跨檔追查需要連續查看多個 part**：若單次 session 已切出多個 part，追查完整脈絡時需要依序查看多個檔案。
