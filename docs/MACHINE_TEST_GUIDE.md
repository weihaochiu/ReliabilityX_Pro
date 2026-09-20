# 2026-09-20 多通道上機測試說明

本版處理 OI-050（失敗誤算完成）、OI-051（卡片讀錯欄位），並更新 OI-017
為量測期間可個別啟動／暫停通道。本文件的「可測試」指可交付測試機驗證，
不代表已通過實體儀器、接線或長時間實驗驗收。

## 1. 在測試機準備

1. 將更新 ZIP 按原目錄結構覆蓋到同版本的完整專案；保留該機自己的
   `config_settings.json`、`channel_settings.json`、`calibration_settings.json`、
   `user_settings.json` 和資料／Log。本更新包沒有這些本機檔案。
2. 初次設定時安裝 Python 3.11（含 Python launcher），雙擊根目錄
   `setup_and_check.bat`。它建立 `.venv`、安裝 runtime 與 pytest、執行離線測試。
   首次下載套件需要網路。已有可用 `.venv` 會直接使用。套件版本未全部鎖定，
   因此測試機上仍須執行整套測試。開發驗證環境使用 Python 3.12。
3. 腳本必須顯示 `[PASS]`，若失敗保留完整輸出，不要直接略過。
   `pytest` 使用 Mock 裝置並阻擋實體 VISA／Serial／socket 通訊。
4. 測試機的 NI-VISA／USB Serial／廠商驅動另行確認；Python 套件安裝不包含它們。
5. 雙擊 `執行.bat` 開啟正式程式。它優先使用 `.venv`。
   程式開啟時會初始化／連接硬體，但不自動開始 IV 掃描。

## 2. 第一次多通道測試

由熟悉機台的人員確認 DUT 接線、Relay 正負端、SMU compliance、輸出與停止方式。

1. 在系統設定確認 SMU 位址、Relay COM／baudrate、資料與 Log 目錄可寫。
2. 建立至少兩個 Channel，填妥使用者、專案、設備名稱、面積、Relay pair、
   掃描起迄電壓、步距、電流限制、延遲與間隔。先採適合該 DUT 的短掃描。
3. 每個實際 Relay pair 都要有本機有效且未過期的 R-line 校正；不可用
   example 檔裡的數值代替實機校正。量測前後的輸出保護仍依實際儀器確認。
4. 先用 `interval_min=0` 做兩通道各一次的測試。勾選需要測試的通道，
   等待設定儲存完成，按「啟動全部循環量測」並確認。
5. 驗證依序完成兩個通道正逆掃，通道間沒有同時選通其他路徑。每個設備目錄
   有 IV curve 與 Summary，卡片顯示與同方向／同 Raw-Corr 類型的結果一致。
6. 成功後設定正數間隔，再按一次全域啟動。每個通道會自動按自己的間隔重複，
   同時到期時由單一 SMU 依序處理。間隔需容納整體掃描時間；注意超載警告。

## 3. 個別通道啟動／暫停

- 全域運行中，取消某 Channel 勾選並確認：儲存成功後送出暫停請求。
  若它正在掃描，完成正逆掃及清理後暫停；若正在等待，下一個安全邊界移出待測。
  其他通道繼續量測。
- 重新勾選並確認：儲存成功後排入下一個可用時段，之後按其間隔循環，
  不補測暫停期間。原先未納入的完整通道也可用同一操作加入。
- 所有通道都暫停時，全域排程保持等待，可直接勾選個別通道恢復。
- 全域未啟動時，勾選只代表下次參與量測；仍須按一次全域啟動。
- 修改接線、掃描參數或做校正時，先停止全域量測，完成後再重新啟動。
- 「停止全部循環量測」會等當前通道完成及清理後停止；個別暫停也不是緊急停機。

## 4. 錯誤與結果判讀

| 現象 | 本版行為／處理 |
|---|---|
| SMU／Relay／分析／寫檔失敗 | 停止全域排程，成功次數不增加，Log 和結束訊息記錄分類；排除原因後人工重新啟動 |
| 校正缺失或過期 | 禁止該次量測，顯示校正問題；不算成功 |
| 清理無法確認 | 回報失敗；依機台程序確認真實 SMU／Relay 狀態 |
| 卡片「正掃／校正」 | 顯示正式 Corr 欄位的 Voc 與 PCE |
| 卡片「正掃／原始」 | 校正顯示值不可用，退回完整 Raw 數值對並標示警告 |
| 卡片「無有效正掃數據」 | 顯示 `—`，不製造零值 |
| 原始 IV 已存在但 Summary 失敗 | 保留已寫的 IV；仍視為失敗，不假裝已完整存檔 |
| 設定儲存失敗 | 彈窗、Log 記錄；失敗變更不送到排程 |

Log 中搜尋 `status=failed_read`、`failed_analysis`、`failed_logger`、
`relay_failure`、`cleanup_failure`、`blocked_config`、`blocked_calibration`。
`runtime_schedule_state.json` 的 `last_channel_failure` 可協助追蹤最近一次失敗。
完成次數是本次全域運行成功量測的累計次數，循環量測可大於通道數。

## 5. 現場驗收紀錄

依序記錄：兩通道單次結果、至少兩輪循環結果、暫停其中一個而其他繼續、
恢復單一通道、全部暫停後恢復、全域停止，以及資料／Log 路徑。
不要以拔除通電中的接線來製造故障；軟體故障路徑已有離線注入測試。
長時間可靠度試驗、環境控制器與真實裝置斷線行為仍需現場另行驗證。

## 建置資訊

本次沒有新增圖片或 `.ui` 資源，既有 `--add-data` 資產清單不需擴充。
`build_and_deploy.py` 已改用完整 runtime registry 檢查建置依賴：

```python
from dependency_bootstrap import RUNTIME_DEPENDENCIES
REQUIRED_PACKAGES = [
    (dependency.module, dependency.package) for dependency in RUNTIME_DEPENDENCIES
] + [("PyInstaller", "pyinstaller")]
```

此次交付為原始碼更新，未宣稱已建置或驗證 EXE。
