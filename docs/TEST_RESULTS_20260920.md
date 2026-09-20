# 2026-09-20 驗證結果

## 實際執行

- `.venv/Scripts/python.exe -m pytest -q`：**96 passed in 26.71s**。
- Git tracked/new source 的 Python AST 語法檢查：**118 個 Python 檔案通過**。
- `.venv/Scripts/python.exe -m pip check`：**No broken requirements found**。
- `git diff --check`：通過。

全部 pytest 皆為離線 mock；全域 gate 阻擋實體 VISA、Serial、socket、production
SMU ON 及實體 Relay 操作。完整 GUI 使用 `QT_QPA_PLATFORM=offscreen`，包含真實
MainWindow、卡片、非同步設定寫入及 QThread 工作迴圈。

## 覆蓋內容

- 原有分析公式、校正、schema、logger、cold-switching、備份流程回歸。
- SMU read、Relay、analysis exception/invalid flag、IV logger、Summary logger、
  mapping、缺失／過期校正與 cleanup fault：不增加成功數，停止後續通道，持久化分類。
- 四通道獨立 Relay pair 與資料檔案；不同正數 interval 的多輪虛擬時鐘回歸。
- 掃描中暫停当前及等待通道、恢復、動態加入原先未啟動通道、全暫停後恢復。
- 完整 GUI 的全域啟動／停止入口、個別 checkbox pause/resume、儲存失敗復原。
- 連續寫入前一筆成功／後一筆失敗時的狀態一致性及重複請求去重。
- 正式 Corr/Raw 值、legacy fallback、NaN／缺值／無限值、合法零值及卡片顯示。

## 環境

Windows；Python 3.12.14；pytest 9.1.1；PyQt6 6.11.0；numpy 2.5.3；
scipy 1.18.1；pyqtgraph 0.14.0；matplotlib 3.11.2。

測試機安裝依賴版本可能不同，需再執行 `setup_and_check.bat`。
本次未驗證 Python 3.11 實際環境、EXE 打包、實體 SMU/Relay/Chamber、
廠商驅動、實際 DUT 接線／compliance 與長時間可靠度實驗。
明天的現場步驟見 [MACHINE_TEST_GUIDE.md](MACHINE_TEST_GUIDE.md)。
