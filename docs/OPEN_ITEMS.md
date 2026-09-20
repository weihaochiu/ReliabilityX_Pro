# OPEN_ITEMS.md — ReliabilityX Pro 待辦與技術債追蹤

> 本文件是 ReliabilityX Pro 的正式 open item / backlog / technical debt 追蹤表。  
> 每次 AI 或維護者修改程式後，若新增、完成、延後、取消或發現任何待辦事項，必須同步更新本檔。  
> 本文件取代根目錄舊版 `ToDo list.txt` 作為唯一待辦追蹤來源；`ToDo list.txt` 僅保留指向本檔的提示。

---

## 0. 本版稽核摘要

- Audit source: `ReliabilityX Pro_202605142227.zip`、既有 `OPEN_ITEMS.md`、近期使用者決策。
- Static check: 全專案 Python 語法檢查可通過，但這不等於 GUI runtime test 或硬體實測。
- 主要結論：目前已完成 dynamic logical channel、per-channel scheduler、全域循環量測控制、channel 開始/暫停語意化；下一階段應優先補齊資料安全、量測正確性、thread boundary、scheduler 持久化與測試基礎。
- 2026-08-19 public Git baseline audit: repository hygiene 已排除 runtime data/log/cache、local hardware/user config、historical snapshots、第三方 manuals 與 secret material；新增安全 config examples。OI-012 的本機 legacy 檔實體集中整理仍維持 Open，本次不刪除或搬移使用者檔案。

---

## 1. 欄位定義

| 欄位 | 說明 |
|---|---|
| ID | 穩定追蹤編號。完成後不重編號。 |
| Priority | `P0` = 會影響安全、資料正確性、secret 或重大流程；`P1` = 重要功能或高風險技術債；`P2` = 改善可維護性、使用體驗或中期架構；`P3` = 低風險整理、文件或打包品質。 |
| Status | `Open`, `In Progress`, `Blocked`, `Done`, `Deferred`, `Cancelled`。 |
| Area | 主要影響模組或功能區。 |
| Evidence | 依據目前程式、文件或使用者討論確認的現況。 |
| Next Action | 建議下一步，供 AI 或維護者接續執行。 |
| Impact / Risk | 說明該問題對安全性、資料正確性、thread safety、使用體驗、維護性或打包品質的影響。 |
| Next Action | 建議下一步，供 AI 或維護者接續執行。 |
| Acceptance Criteria | 驗收標準。完成後應用此欄逐項確認。 |
| Notes for future AI maintainers | 給後續 AI / 維護者的注意事項、避免誤修方向、相依 open item 或測試提醒。 |

---

## 2. P0 — 優先處理：安全、資料正確性、secret、thread-boundary

### OI-001 — Channel 診斷流程改為 queued signal / worker-thread 安全架構

| 欄位 | 內容 |
|---|---|
| Priority | P0 |
| Status | Done |
| Area | `gui/channel_setting_dialog.py`, `gui/widgets/channel_action_widget.py`, `core/measure_engine.py`, `core/diagnostics/diagnostics_service.py` |
| Evidence | `ChannelSettingDialog` / channel action widget 仍可能直接呼叫 `MeasureEngine.measure_line_resistance()` 與 `MeasureEngine.perform_spot_check()`；但 `MeasureEngine` 已被 `moveToThread()` 到 worker thread。GUI thread 直接呼叫 worker method 會造成 thread-boundary 風險與 UI 阻塞風險。 |
| Next Action | 新增 request/result signals，例如 `request_measure_line_resistance`, `line_resistance_measured`, `line_resistance_failed`, `request_spot_check`, `spot_check_completed`, `spot_check_failed`。由 MainWindow 或 controller 使用 queued connection 轉接。 |
| Acceptance Criteria | 線阻/spot check 的硬體 I/O 全部在 worker thread；GUI 不阻塞；錯誤可由 result signal 回傳 dialog；校準 JSON 與 rline history 寫入行為維持相容。 |


**Completed 2026-05-15 update:** see ADR-0043. Implemented in current codebase.

---

### OI-013 — 移除真實 Telegram token / chat_id，改用外部 secret

| 欄位 | 內容 |
|---|---|
| Priority | P0 |
| Status | Done |
| Area | `config/notification_settings.json`, `core/notification_manager.py`, `gui/config_tabs/notification_tab.py`, build/release package |
| Evidence | 最新專案 ZIP 的 `config/notification_settings.json` 內含真實 Telegram bot token 與 chat ID。即使 `enabled=false`，只要 ZIP 被備份、上傳或分享，就等同 secret 已外流。 |
| Next Action | 立即 rotate Telegram bot token；專案內只保留 `notification_settings.example.json` 或遮罩後設定；真實 token 改由本機 private config、環境變數或使用者 GUI 輸入；build/release package 預設排除真實 config。 |
| Acceptance Criteria | repo / patch / release ZIP 不再含真實 token 或 chat ID；notification UI 能讀取本機私有設定；README 說明如何設定 Telegram secret；舊 token 已重發/失效。 |


**Completed 2026-05-15 update:** see ADR-0043. Implemented in current codebase.

---

### OI-018 — 電流 offset 尚未真正套用於 scan_sequence 的 corrected data

| 欄位 | 內容 |
|---|---|
| Priority | P0 |
| Status | Done |
| Area | `core/measure_engine.py`, `core/iv_curve_logger.py`, `core/summary_logger.py`, `config/calibration_settings.json` |
| Evidence | `scan_sequence()` 目前有 `v_corr = v_msd - (i_msd * r_line_ohm)`，但 `i_corr` 仍等於 `i_msd`；尚未套用 calibration offset。這會影響 corrected current、corrected voltage、Jsc、PCE、Rs/Rsh 與 trend。 |
| Next Action | 在量測點建立時套用 `i_corr = i_msd - offset_current`，再用 `v_corr = v_msd - i_corr * r_line_ohm`；將 offset 與 R_line 寫入 curve / summary metadata。 |
| Acceptance Criteria | Raw 與 Corr 兩路數據明確不同；summary metadata 可追蹤使用哪一筆 offset/R-line；unit test 或 mock scan 能驗證 corrected value。 |


**Completed 2026-05-15 update:** see ADR-0043. Implemented in current codebase.

---

## 3. P1 — 重要功能與高風險技術債

### OI-002 — 完成 MeasureEngine Phase 1 service wiring

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Partially Done |
| Area | `core/measure_engine.py`, `core/measurement_scheduler.py`, `core/hardware/hardware_manager.py`, `core/hardware/relay_path_service.py`, `core/diagnostics/diagnostics_service.py` |
| Evidence | 2026-05-15 已先將 per-channel due-time / conflict queue / drift-free cadence 抽到 `core/measurement_scheduler.py`。但 `MeasureEngine` 仍直接實作硬體 probe/reconnect、relay reset/path、line resistance、spot check。 |
| Next Action | 已完成 scheduler boundary；下一步再分階段把 probe/reconnect、安全關閉、relay path setup/cleanup、diagnostics 移到 service；保留 `MeasureEngine` 作為 scan lifecycle orchestrator 與 Qt signal API。 |
| Acceptance Criteria | `MeasureEngine` 不再重複保留完整硬體/relay/diagnostics implementation；service 實際被 import/使用；`CODEBASE_MAP.md` 中狀態從 scaffold 改為 active runtime。 |

---

### OI-003 — Telegram active-scope PDF report dispatch

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `core/notification_manager.py`, `gui/trend_snapshot_renderer.py`, `config/notification_settings.json`, `gui/config_tabs/notification_tab.py`, `core/trend_scope_utils.py` |
| Evidence | `trend_pdf_enabled` 與 PDF renderer 已存在；本次已接上 `NotificationManager._dispatch_trend_reports()`，會在定時摘要時優先依 `trend_pdf_enabled` 產生 active-scope grouped PDF，失敗時退回 PNG / text summary。 |
| Impact / Risk | 若未依 active scope 分組，Telegram 可能把不同使用者/專案/device 畫在同一張圖或同一份報告，造成可靠度判讀混淆。 |
| Next Action | 後續可擴充 `environment_project` group mode 與 GUI preview；核心 active-scope PDF dispatch 已完成。 |
| Acceptance Criteria | Telegram 定時摘要在 `trend_pdf_enabled=true` 時可依 `overall` / `user_project` 分組產生 PDF；PDF 一頁一個 metric，必要時包含 environment subplot；若 PDF 產生失敗會記錄 warning 並 fallback。 |

---

### OI-004 — Trend chart 跨停止/重啟的完整 degradation history

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `gui/trend_chart_window.py`, `core/trend_scope_utils.py`, `core/channel_identity.py`, `core/summary_logger.py`, summary/curve logs, dynamic logical channel archive |
| Evidence | 本次新增 `experiment_uid` / `run_session_id`，`trend_scope_utils.make_series_key()` 優先使用 `experiment_uid`；`TrendChartWindow.set_active_scope()` 會掃描 historical `Summary_report.csv`，將符合 active scope 的歷史點載入 bounded GUI cache。 |
| Impact / Risk | 若無跨重啟 history，長效 degradation curve 會被切斷，容易誤判元件衰退與 recovery。 |
| Next Action | 後續可加入 UI 手動選擇 historical experiment / archived channel viewer；active-scope 自動接續已完成。 |
| Acceptance Criteria | 停止程式或全域排程後重新啟動，同一 `experiment_uid` 的 device/experiment 可接續顯示先前 Summary 資料；不同 project/device 不互相混線；歷史點會被標記 `history_source=summary_csv`。 |

---

### OI-005 — Environment runtime / chamber 溫濕度讀取與 ISOS closed-loop control

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Open |
| Area | `driver/chamber_driver.py`, `core/environment_manager.py`, environment tabs, `core/measure_engine.py` |
| Evidence | Environment subsystem 目前主要是設定管理與 GUI 結構；`MeasureEngine` 仍只持有傳統 `chamber_driver` 狀態，尚未完整接入 environment recipe runtime control。 |
| Next Action | 定義 chamber telemetry schema（temperature, humidity, setpoint, alarm, timestamp），建立 environment runtime manager 或 adapter，把讀值送到 status panel、trend env subplot、logger 與 notification。 |
| Acceptance Criteria | 主畫面環境監控顯示真實 PV/SV；trend 可選擇顯示環境子圖；異常溫濕度或 chamber disconnect 可記錄/通知；不阻塞 IV measurement worker。 |

---

### OI-006 — Relay / logical channel 對照表與診斷矩陣同步

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Partially Done |
| Area | `gui/config_tabs/relay_tab.py`, `config/hardware_map.json`, `config/channel_settings.json`, `core/channel_identity.py`, dynamic channel list |
| Evidence | 本次新增 `build_relay_occupancy()`，Relay config tab 會從 active `channel_settings.json` 推導 relay 佔用狀態，表格新增 Active +R / −R owner 欄位，64 relay 按鈕也會以黃色提示 active channel 佔用。 |
| Impact / Risk | 若 relay matrix 只看舊 `hardware_map.json`，會把 template 誤認為 active assignment，造成 operator 誤判可用 relay。 |
| Next Action | 後續可再加入 polarity-conflict 專用顏色、faulty/maintenance 狀態與一鍵跳轉到 Channel 設定。 |
| Acceptance Criteria | Config tab 可即時看出每個 relay 被哪個 CH_x## / Device / Project 使用；本階段已完成 active occupancy 顯示，進階衝突/維修狀態仍待延伸。 |

---


### OI-047 — 使用者 Email 報告排程、專案 PDF 分信寄送與主管 CC

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Open |
| Area | `gui/system_config_dialog.py`, Users & Projects config tab, `config/user_registry.json`, `config/project_registry.json`, `config/notification_settings.json`, `core/report_scheduler.py`, `core/email_report_service.py`, `core/project_report_builder.py`, `core/email_sender.py`, `core/notification_manager.py`, `core/log_manager.py`, PDF/trend report pipeline, `logs/email_report_log.csv` |
| Evidence | 使用者要求在「使用者 / Users」人員資訊中新增 Email、每人期望報告時間，以及上級主管下拉選單；到指定時間時，系統需將該人員名下每個專案的 PDF 報告寄到該使用者信箱。若同一人有兩個專案，必須分成兩封 email / 兩份 PDF，而不是混在同一封或同一份報告中；若該人員設定主管，需可自動 CC 到主管信箱。 |
| Impact / Risk | 若報告仍以全域 Telegram / 單一 summary 發送，可能把不同使用者或不同專案資料混在一起，造成科研判讀與資料歸屬混淆。若沒有個人報告時間、主管 CC 與寄送紀錄，PI / supervisor 無法穩定追蹤學生專案進度；若沒有去重機制，程式重啟可能重複寄信或漏寄。 |
| Next Action | 建立正式 User Profile / Project Ownership schema：使用者資料需包含 `user_id`, `display_name`, `email`, `role`, `preferred_language`, `report_enabled`, `report_times`, `supervisor_user_id`, `cc_supervisor`；主管下拉選單只顯示 role 為 `Supervisor` / `PI` / `Admin` 且有 email 的人員。建立 project registry 或擴充既有 project metadata，標記 project owner、status(active/inactive) 與 report_enabled。新增 email report service：依 user report time 掃描 active projects，逐 project 產生 PDF 並分別寄送，必要時 CC supervisor。 |
| Acceptance Criteria | (1) Users & Projects 頁可輸入/編輯每位使用者 email、角色、偏好語言、報告時間與主管。 (2) 主管欄位為下拉選單，來源為 user registry 中具備主管角色的人員，不靠手動輸入 email。 (3) 到達某使用者指定報告時間時，系統只處理該使用者 active projects。 (4) 同一使用者有 N 個 active projects 時，產生 N 份 PDF 並寄出 N 封獨立 email。 (5) 若 `cc_supervisor=true` 且主管有 email，該封 email 自動 CC 主管。 (6) 每次寄送結果寫入 `logs/email_report_log.csv`，包含 timestamp、user_id、project_id、pdf_path、to、cc、status、error_message 與 dedupe key。 (7) Email server / SMTP secret 不得寫入一般 release config 或 log；密碼需遮蔽並與 release package 隔離。 (8) PDF 產生失敗、email 缺漏、主管 email 缺漏或 SMTP 失敗時不造成 GUI / measurement worker 崩潰。 |
| Notes for future AI maintainers | 報告派送規則固定為「一位使用者 + 一個專案 = 一封 email + 一份 PDF」。不要把多個 project 合併成一封信，除非未來另開 option 且預設仍保持分信。Email 寄送不可寫在 GUI slot 內，必須由 service / scheduler 負責，GUI 只管理設定與測試信。SMTP token/app password 屬於 secret，需遵守 OI-013 / OI-044 的 sanitization 與 release exclusion 規則。 |

---

### OI-014 — 移除根目錄殘留 `CHANGESET_MANIFEST.md`，避免與新交付規則衝突

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | project root, `build_and_deploy.py`, `.gitignore`, release package |
| Evidence | AI instructions 已改為不預設交付 `CHANGESET_MANIFEST.md`，但 release/patch 包仍需明確排除該檔與 runtime cache，避免維護者誤以為它是正式 source of truth。 |
| Impact / Risk | 若根目錄 `CHANGESET_MANIFEST.md`、runtime cache 或個人設定混入 ZIP，會造成交付包不可重現、混淆版本追蹤來源，也可能洩漏本機路徑或實驗資料。 |
| Next Action | 已完成：打包流程新增 release cleanup，會排除 `CHANGESET_MANIFEST.md`、`__pycache__`、`.pyc/.log/.tmp`、local-only config；`.gitignore` 也加入 runtime/local-only artifacts 規則。後續若新增新型 runtime artifact，需同步加入 exclusion list。 |
| Acceptance Criteria | patch/release ZIP 不再包含根目錄 `CHANGESET_MANIFEST.md`；正式追蹤來源保留於 `docs/version_history.txt`、ADR 與 `docs/OPEN_ITEMS.md`；build/release 清理邏輯會在 zip 前移除排除項目。 |
| Notes for future AI maintainers | 不要重新建立根目錄 `CHANGESET_MANIFEST.md` 作為長期追蹤文件；短期交付摘要可放在 final response，永久紀錄放 version history / ADR / OPEN_ITEMS。 |

**Completed 2026-05-15 update:** implemented release exclusion for `CHANGESET_MANIFEST.md` and runtime/cache artifacts in `build_and_deploy.py`, plus `.gitignore` rules.

---

### OI-015 — 拆分 `is_running`，建立正式 runtime state machine

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Open |
| Area | `core/measure_engine.py`, `gui/main_window.py`, `gui/widgets/control_panel.py` |
| Evidence | `is_running` 同時被正式循環量測、line resistance、spot check 等流程使用。UI 很難判斷目前是 scan running、diagnostic running、hardware busy 還是 safe stopping。 |
| Next Action | 建立 `scan_running`, `diagnostic_running`, `hardware_busy`, `stop_requested` 或 enum state：Idle / SchedulerRunning / MeasuringChannel / DiagnosticRunning / SafeStopping / Error。 |
| Acceptance Criteria | 狀態列能正確顯示目前狀態；全域停止、channel 移除、診斷、reconnect 不互相誤判；錯誤狀態可追蹤。 |

---

### OI-016 — Scheduler `next_due_time` 持久化，支援長效實驗重啟續跑

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `core/measure_engine.py`, `config/runtime_schedule_state.json` 或 `data/run_state/*`, summary logger |
| Evidence | 目前 per-channel scheduler 啟動時會在 memory 內建立 `next_due`；程式重啟後所有啟用 channel 容易被視為立即到期，而非延續原本 interval。 |
| Next Action | 新增 runtime schedule state，儲存 `channel_label`, `last_measured_at`, `next_due_time`, `interval_min`, `run_session_id`；啟動時可選擇 resume 或 reset schedule。 |
| Acceptance Criteria | 程式重啟後能延續長效排程；使用者可選擇「接續排程」或「立即重新開始」；狀態寫入具備 crash safety。 |


**Completed 2026-05-15 update:** see ADR-0043. Implemented in current codebase.

---

### OI-017 — 量測中切換 channel checkbox 的 scheduler 一致性規則

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `gui/main_window.py`, `gui/settings_save_controller.py`, `core/measure_engine.py` scheduler startup contract |
| Evidence | Channel checkbox 代表「開始/暫停循環量測」。若全域 scheduler 已在執行，直接即時更改 worker queue 會造成 UI 顯示與實際 worker schedule 不一致，尤其在單 SMU/Relay 資源與 active measurement 中途。 |
| Impact / Risk | 量測中即時改 queue 可能導致某些 channel 被漏量、重複量、或與目前 relay path 狀態不一致；若使用者以為 checkbox 即時生效，可能誤判長效測試狀態。 |
| Next Action | 2026-09-20 依使用者需求改為 live boundary controls（ADR-0061）：設定成功保存後經 SimpleQueue 傳送；worker 僅在正逆掃與清理後套用個別啟動／暫停。全暫停保持等待，恢復時不補測暫停期間。 |
| Acceptance Criteria | 完整 Qt GUI/worker 測試通過：按一次全域啟動、個別／全部暫停、單獨恢復、全域停止；儲存失敗不送出失敗變更；同一通道正逆掃不中斷，其他通道繼續；獨立週期保持 scheduled_due + interval。 |
| Notes for future AI maintainers | 未來若要支援即時 scheduler update，必須新增明確 queued signal 與 state machine，不可直接在 UI thread 修改 worker 內部資料結構。 |

**Updated 2026-09-20:** 原 next-global-start-only 政策由 ADR-0061 取代。GUI 只 enqueue copied requests；不在 GUI thread 直接修改 scheduler 或操作儀器。全域 stop 同樣經 queue，避免被長時間 worker slot 擋住。

---

### OI-019 — R-line 診斷歷程與可設定校正提醒完整化

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `gui/channel_setting_dialog.py`, `gui/widgets/channel_action_widget.py`, `gui/config_tabs/measurement_tab.py`, `config.py`, `config/config_settings.json`, `core/measure_engine.py`, `core/iv_curve_logger.py`, `core/summary_logger.py`, `data/rline_history.csv` |
| Evidence | 線阻量測原先只寫入 `calibration_settings.json` 最新值，缺少完整歷程 CSV、原始 V/I、operator/device/project/channel traceability，也沒有校正年齡檢查；使用者進一步要求 Channel 設定頁在存檔前若從未量過 R-line 必須阻擋，且校正提醒天數應可在全域 Config 設定為 30 / 60 天或自訂值。 |
| Impact / Risk | 若 relay pair 從未校正或使用過期 R-line，`V_cell = V_source - I_corr * R_line` 會套用錯誤或 0 Ω 補償，影響 corrected IV、PCE、Rs/Rsh 與長效趨勢。沒有歷程紀錄也會讓後續無法追溯當時使用哪一筆線阻校正。 |
| Next Action | 已完成第一版：`CALIBRATION_SETTINGS.RLINE_MAX_AGE_DAYS` 進入全域量測與安全 Config 頁；Channel 設定頁顯示 R-line 年齡與紅色過期提醒；若選定 SMU+/SMU− relay pair 從未做過 R-line 量測，Channel 設定頁與全域啟動流程都會阻擋；若超過提醒天數，存檔/啟動前需使用者確認；每次 R-line 量測追加到 `data/rline_history.csv`。後續若要更嚴格，可將過期從 warning 改成 hard-block policy。 |
| Acceptance Criteria | 每次 R-line 量測會寫入最新 `line_resistance_map` 與 append-only `data/rline_history.csv`，包含 timestamp、operator/user、project、device、channel_label、environment、pos/neg pin、source current、measured voltage/current、resistance、request_id 與 status。Channel 設定頁可依全域天數顯示正常/過期狀態；從未校正的 relay pair 不可儲存為有效 Channel 設定，也不可啟動量測。IV curve / Summary metadata 會記錄 R-line value/date/age/expired/max-age。 |
| Notes for future AI maintainers | 不要把 R-line 提醒天數硬寫在 widget 裡；必須透過 `config.get_rline_calibration_max_age_days()` 讀取全域設定。若修改 R-line schema，需保留 legacy numeric record 讀取能力。 |

**Completed 2026-05-15 update:** implemented configurable R-line max-age setting, save/start hard-block for never-calibrated relay pairs, expired-calibration warning confirmation, R-line history CSV, and R-line metadata propagation into IV/Summary outputs.

---

### OI-020 — IV / Summary / Trend 欄位單位全面對齊

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `core/measurement_schema.py`, `core/IV_parameter_analysis_utils.py`, `core/summary_logger.py`, `core/iv_curve_logger.py`, `core/trend_spec.py`, `gui/trend_chart_window.py`, `gui/widgets/iv_analysis_widget.py`, `gui/trend_snapshot_renderer.py` |
| Evidence | 先前 analysis utils、summary logger、trend labels、IV analysis widget 彼此硬編碼 label，曾出現 `Rs (Ω·cm²)`、`Rsh (kΩ·cm²)`、`Jmpp(mA/cm2)` 等不一致標示；widget 與 logger 各自定義單位會提高未來 drift 風險。 |
| Impact / Risk | 同一物理量若在 IV CSV、Summary、Trend、Telegram/PDF 中使用不同單位或名稱，會造成資料誤讀，尤其是 Rsh kΩ vs Ω、Isc/Impp mA vs A、Jsc/Jmpp mA/cm² vs A/cm²。 |
| Next Action | 已完成：新增 `core/measurement_schema.py` 作為 IV summary/reporting unit registry。Summary/IV curve analysis matrix、Trend selector、Trend chart lookup、Trend snapshot renderer、IV analysis widget 改用同一 schema。標準 summary-scale 單位為 Voc(V)、Isc(mA)、Jsc(mA/cm²)、FF(%)、PCE(%)、Rs(Ω)、Rsh(kΩ)、Pmpp(W)、Vmpp(V)、Impp(mA)、Jmpp(mA/cm²)。 |
| Acceptance Criteria | Summary CSV header、IV curve analysis matrix、Trend dropdown / y-axis、IV analysis table 使用同一套 schema；legacy `Hysteresis_Index` label 仍可被解析為 `Hysteresis Index`。Data-point raw columns 仍清楚標示 raw current in A 與 current density in A/cm²，避免與 summary-scale mA/mA/cm² 混淆。 |
| Notes for future AI maintainers | 不要在 widget/logger 中直接新增硬編碼 metric label；新增參數時先修改 `core/measurement_schema.py`，再讓各 UI/logger 從 schema 讀取。 |

**Completed 2026-05-15 update:** central IV unit schema implemented and connected to Summary, IV curve, Trend, snapshot, and IV analysis table labels.

---

### OI-008 — 無硬體 GUI smoke test 與 Mock driver 測試模式

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | In Progress |
| Area | `main.py`, `tests/`, drivers, GUI smoke tooling, requirements/build tooling |
| Evidence | 2026-08-19 已建立 56 項 offline pytest baseline、`MockSMU` / `MockRelay` / `MockEnvironment`、production MeasureEngine mock integration，以及 VISA/Serial/socket/output safety gate；但尚未加入可啟動完整 GUI 的 `RELIABILITYX_MOCK_HW=1` runtime mode 或 offscreen GUI interaction test。 |
| Impact / Risk | Core scientific、logger、config、measurement sequencing 與 cleanup 已可自動回歸，但新增 channel、checkbox confirmation、global scheduler status、dialog navigation 等 GUI interaction 仍只能人工驗證。 |
| Next Action | 2026-09-20 已加入 offscreen 完整 MainWindow 與真實 QThread 的 global start/stop、個別 pause/resume、coalesced save failure 測試。尚待 standalone opt-in mock runtime、建立/移除 channel 及設定頁導覽測試，故維持 In Progress。 |
| Acceptance Criteria | 沒有 SMU/relay/chamber 的電腦可啟動 GUI、建立/移除 channel、切換環境/relay、執行短流程 mock scan；CI/offscreen mode 可跑基本 smoke test。 |
| Notes for future AI maintainers | 不可移除 `tests/conftest.py` 的全域硬體 gate；GUI mock mode 必須是明確 opt-in，production startup 不得預設使用 mock。 |

---

### OI-009 — 建立真正的緊急停止與 graceful stop 分層

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Done |
| Area | `core/shutdown_manager.py`, `gui/widgets/control_panel.py`, `gui/main_window.py`, `core/measure_engine.py`, relay/SMU safety |
| Evidence | 2026-05-15 已新增 `ShutdownManager` 與「🛑 安全關閉程式」入口；按下後可選 `安全流程關閉` 或 `緊急停止並關閉`。安全流程會停止 scheduler、等待現有 graceful boundary、強制 SMU output OFF、relay reset_all、關閉硬體與 worker thread；緊急流程會立即設定 abort 狀態並強制硬體 safe state。 |
| Next Action | 後續可再強化 Telegram shutdown notification、硬體層級 kill-switch 或長按式 emergency UI，但核心分層已完成。 |
| Acceptance Criteria | Operator 能清楚區分 graceful stop、safe process shutdown 與 emergency shutdown；`[SHUTDOWN]` log 可追蹤選擇、SMU OFF、Relay reset_all、worker thread close 與 emergency reason。 |

**Completed 2026-05-15:** see ADR-0044. `MainWindow.closeEvent()` no longer directly bypasses the shutdown manager; OS close and control-panel close now use the same confirmation flow.

---

### OI-010 — Channel archival / draft cleanup / restore workflow

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Partially Done |
| Area | `config/archived_channel_settings.json`, `gui/main_window.py`, `gui/channel_setting_dialog.py`, `core/channel_identity.py` |
| Evidence | 本次 formalized archive schema：`_archive_channel_record()` 改用 `build_archive_record()`，archive record 包含 `archive_id`, `experiment_uid`, `run_session_id`, `internal_ch_id`, `channel_label`, user/project/device, environment, relay pins, measurement settings, `ended_at`, `final_status`, `data_path` 與原始設定快照。新增 Channel 仍以新 internal id 開空白 dialog。 |
| Impact / Risk | Archive schema 不一致會讓 restore / history lookup 無法判斷資料屬於哪顆元件或哪次 run。 |
| Next Action | 後續新增 archived channel viewer / restore UI；restore 前必須重新檢查 relay 衝突與 R-line 校正。 |
| Acceptance Criteria | 結束 channel 後 active list 不顯示；archive record schema 一致；新增 channel 不自動沿用前一個 user/project/device；GUI restore viewer 仍待實作。 |

---

### OI-021 — AI_INSTRUCTIONS 的 MVC 規則與目前 Qt worker-object 架構對齊

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Open |
| Area | `AI_INSTRUCTIONS.md`, `core/measure_engine.py`, `core/log_manager.py`, `core/notification_manager.py` |
| Evidence | `AI_INSTRUCTIONS.md` 寫 Model/core 禁止導入 PyQt6，但目前 `core/measure_engine.py`、`core/log_manager.py`、`core/notification_manager.py` 都使用 QObject / signal / QTimer。這是 Qt worker-object 架構的一部分，但文件規則需更新避免 AI 誤判。 |
| Next Action | 短期採「core/runtime 可有 Qt worker object；driver/analysis/service 保持 pure Python」規則；長期再考慮 controller adapter 抽離。 |
| Acceptance Criteria | AI instructions 與實際架構一致；未來 AI 不會因規則衝突錯誤重構 core；CODEBASE_MAP 清楚標註 Qt-bound runtime modules。 |

---

### OI-022 — 移除 Widget 內物理單位換算

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Open |
| Area | `gui/widgets/iv_plot_widget.py`, `core/IV_parameter_analysis_utils.py`, possible `core/iv_display_units.py` |
| Evidence | 規範要求 widget 不做 `*1000` 或 `/1000` 物理換算，但 `iv_plot_widget.py` 仍有 current/power/current-density 轉換。 |
| Next Action | 新增 display-unit service 或由 analysis utils 產出 display arrays；widget 只負責畫圖與格式化，不負責物理單位換算。 |
| Acceptance Criteria | `gui/widgets/*` 不再包含物理單位換算；測試確認 IV plot 與 summary/trend 單位一致。 |

---

### OI-023 — `channel_settings.json` schema version 與 migration

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Done |
| Area | `config/channel_settings.json`, `gui/main_window.py`, `gui/channel_setting_dialog.py`, `core/channel_identity.py`, `tools/migrate_channel_settings.py`, `tools/validate_channel_settings.py` |
| Evidence | 本次採 legacy-compatible schema v2，不一次改成巢狀 `channels` 以避免破壞既有 GUI；top-level 增加 `__schema_version=2` / `__schema_note`，每個 numeric channel record 增加 `channel_schema_version`, `internal_ch_id`, `status`, `experiment_uid`。 |
| Impact / Risk | 若資料格式繼續混雜，後續 Trend history、archive restore、Telegram grouping 與 Relay matrix 會無法穩定判斷 active/draft/legacy channel。 |
| Next Action | 若未來要改成完全巢狀 `channels`，需另開 migration ADR；目前 schema v2 已可穩定支援 active runtime。 |
| Acceptance Criteria | active channel schema 穩定；新增/移除/封存 channel 不再依賴 legacy 推導；`tools/validate_channel_settings.py` 可找出 duplicate label、relay polarity conflict；舊資料可由 `tools/migrate_channel_settings.py` 升級。 |

---

### OI-024 — `hardware_map.json` 與 dynamic channel 的一致性規則

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Done |
| Area | `config/hardware_map.json`, `config/channel_settings.json`, `gui/config_tabs/relay_tab.py`, `gui/channel_setting_dialog.py`, `gui/main_window.py`, `core/channel_identity.py` |
| Evidence | 本次明確定義：active relay assignment source-of-truth 是 `channel_settings.json` numeric channel record；`hardware_map.json` 是 default template / legacy migration reference。ChannelSettingDialog 不再把 active relay assignment 回寫 hardware_map；MainWindow 結束 channel 時也不再 mutate hardware_map。 |
| Impact / Risk | 若 hardware_map 被當作 active source，舊 mapping 可能覆蓋或混淆 dynamic logical channel 的 relay assignment。 |
| Next Action | 後續可新增 reconciliation report，但 runtime source-of-truth 已明確。 |
| Acceptance Criteria | 不會因 hardware_map 殘留造成 active relay 顯示錯誤；CODEBASE_MAP/ARCHITECTURE 清楚描述資料來源；Relay tab 同時顯示 template map 與 active occupancy。 |

---

### OI-025 — `archived_channel_settings.json` schema 與 restore workflow 正式化

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Partially Done |
| Area | `config/archived_channel_settings.json`, `core/channel_identity.py`, archive viewer, restore flow |
| Evidence | 本次 archive schema formalized：`archive_schema_version=1`，records 包含 archive identity、experiment/run identity、channel label/internal id、user/project/device、environment、relay pins、measurement settings、timestamps、final_status、data_path 與 `source_channel_record`。既有 legacy archive 也已轉為新格式。 |
| Impact / Risk | Archive schema 不一致會阻礙 restore、trend history lookup 與 audit traceability。 |
| Next Action | 後續需新增 archive viewer / restore UI；restore 前必須重新檢查 relay conflict、R-line 校正與 active channel id 衝突。 |
| Acceptance Criteria | Archive record schema 一致；restore 不會直接覆蓋 active channel 或造成 relay 衝突。Schema 已完成，restore UI 尚未完成。 |

---

### OI-026 — 新增 `experiment_uid` / `run_session_id` 資料模型

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Done |
| Area | `core/channel_identity.py`, `core/measure_engine.py`, `core/summary_logger.py`, `core/iv_curve_logger.py`, `core/trend_scope_utils.py`, `gui/main_window.py`, archive, Telegram trend reports |
| Evidence | 本次新增 `experiment_uid` 與 `run_session_id`：Channel settings 保存 stable `experiment_uid`；每次「啟動全部循環量測」建立 `RUN_YYYYMMDD_HHMMSS`；MeasureEngine 保底補齊；Summary / IV curve / archive / Trend / Telegram history 均帶入 identity。 |
| Impact / Risk | 沒有 identity 時，跨重啟 Trend、archive restore、Telegram grouping 都只能用易變的資料夾或 device 名稱推測。 |
| Next Action | 後續可讓 UI 顯示/搜尋 experiment_uid；核心資料模型已完成。 |
| Acceptance Criteria | 同一 device 停止重啟後能接續同一 experiment；不同 run session 可區分；Trend/Telegram/Archive 都能引用同一 identity。 |

---

### OI-044 — Diagnostic bundle export for sanitized logs/configs

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Open |
| Area | `tools/export_diagnostics_bundle.py`, `logs/`, `config/*.json`, runtime snapshot, source patch export workflow |
| Evidence | 使用者指出 raw `logs/` 對 debug 很有價值，因為 SMU/Relay/Chamber timeout、scheduler conflict、shutdown 卡住與 JSON save failure 都會出現在 log 中；但 raw log 與 private config 可能包含本機路徑、專案名稱、device 名稱、Telegram token/chat_id 或 runtime schedule state。 |
| Impact / Risk | 若一般 source patch 完全排除 log，AI/維護者難以追蹤 runtime bug；若直接包含 raw log/private config，又可能洩漏個人路徑、secret 或實驗資料。 |
| Next Action | 新增 `tools/export_diagnostics_bundle.py`，輸出 `exports/ReliabilityX_Pro_diagnostics_YYYYMMDD_HHMMSS.zip`；內容包含 sanitized logs、sanitized config JSON、diagnostic_summary.md、environment_info.txt 與 runtime_snapshot；遮蔽 Telegram token/chat_id、本機路徑、使用者/專案/device 敏感值。 |
| Acceptance Criteria | Diagnostic bundle 可供 AI debug 使用且不包含 raw secret；保留最近 N 天或 N 個 log；config JSON 保留欄位結構但敏感值 redacted；source patch export 仍排除 raw logs/private configs。 |
| Notes for future AI maintainers | 不要把 diagnostic bundle 與 source patch 混為同一個輸出；source patch 用於套用程式修改，diagnostic bundle 用於 debug runtime error，full private backup 僅供使用者自行保存。 |

---


### OI-045 — SystemConfigDialog Shell 重構：左側導覽、右側內容、首頁總覽與進階折疊

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Done — implemented in 2026-05-16 OI-045 shell refactor patch |
| Area | `gui/system_config_dialog.py`, `gui/config_tabs/station_recipe_tab.py`, `gui/config_tabs/recipe_tab.py`, `config.py`, `config/station_recipes.json`, `config/measurement_recipes.json`, environment/station recipe configs, `docs/ARCHITECTURE.md`, `docs/CODEBASE_MAP.md` |
| Evidence | 目前全域 config 頁面把人員/專案、SMU、Relay、環境控制、量測與安全、量測 Recipe、Environment、Environment Recipe、通知等多個大型頁面放在同一層 tab，功能持續增加後視覺與操作動線變得雜亂。使用者已明確要求全域 config 頁面做 SystemConfigDialog Shell 重構：左側導覽、右側內容、首頁總覽、進階折疊；且 Recipe 清單需分成「量測 Recipe」與「設備/站台 Recipe」，避免把量測條件與硬體配置混在同一清單。本次已完成 Phase 1 shell：左側 navigation + 右側 stacked content + Dashboard + Advanced collapsed panels + Measurement Recipe / Station Recipe 分離。 |
| Impact / Risk | 若繼續使用單層 tab，後續加入 Station Recipe、Email 報告、主管 CC、雙語 UI、Relay occupancy matrix、Chamber telemetry、Notification report 等功能會讓設定頁越來越難維護。使用者可能誤改進階硬體設定，或搞不清楚哪些設定是實驗前必填、哪些只是診斷/開發用途。Recipe 若不分層，也會讓資料追蹤時無法分辨差異來自測量條件還是硬體/環境站台。 |
| Next Action | Phase 1 已完成。後續可在 OI-046 導入 i18n/bilingual helper，並在 OI-047 導入 user email report scheduling / supervisor CC。若要讓 Station Recipe 實際套用到硬體連線與 report metadata，可另開 open item 將 `station_recipes.json` 接入 startup/runtime provenance。 |
| Acceptance Criteria | (1) 全域設定視窗不再以大量同層 tabs 作為主要導航。 (2) 左側導覽可切換右側頁面，且目前頁面標題/說明清楚。 (3) Dashboard 能顯示關鍵狀態與快速跳轉入口。 (4) Measurement Recipe 與 Station Recipe 是獨立頁面與資料模型：Measurement Recipe 管理 IV scan / delay / compliance / area / NPLC；Station Recipe 管理 SMU/Relay/Chamber/Environment/Calibration profile/Notification defaults。 (5) 進階設定預設收合，避免一般使用者誤改。 (6) 既有設定檔與現有 tab 元件可被包入 shell，第一階段不要求重寫所有 tab 內部功能。 (7) 更新 `ARCHITECTURE.md` / `CODEBASE_MAP.md` 說明新 shell 與 config tab 分工。 |
| Notes for future AI maintainers | 第一階段重點是資訊架構與 shell，不要一次重寫所有 config tabs，以免引入大量 regression。若拆分 Recipe schema，需保留既有 `measurement_recipes.json` 的 migration / fallback。Station Recipe 命名建議固定為 `Station Recipe` / `Hardware Recipe`，避免與 device/sample 名稱混淆。 |

---

### OI-046 — 中英文 / 雙語使用者介面與 i18n 字串治理

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Open |
| Area | `utils/i18n.py` 或 `core/i18n.py`, `config/i18n/zh_TW.json`, `config/i18n/en_US.json`, `config/user_settings.json`, `gui/**/*.py`, `assets/style.qss`, report/PDF title strings, email subject/body templates |
| Evidence | 實驗室同時有本國學生與外籍學生使用 ReliabilityX Pro。使用者要求介面需方便中文使用者與英文使用者共同操作。現況多數 GUI label / button / tooltip 為硬編碼中文或英文，若直接散落翻譯會造成後續維護困難，也可能讓 CSV/JSON key 因語言切換而不一致。 |
| Impact / Risk | 若沒有正式 i18n 架構，外籍生可能看不懂安全模式、R-line 校正、Relay mapping、Measurement Recipe 等高風險設定；本國生若切全英文也可能增加操作錯誤。若把資料欄位一起翻譯，會破壞 Summary/Trend/PDF/CSV 的資料解析與跨版本相容性。 |
| Next Action | 新增 UI language setting：`zh_TW`, `en_US`, `bilingual`。建立集中翻譯字典與 helper，例如 `tr(key)` / `tr_pair(key)`；雙語模式顯示「中文 / English」。先從全域設定頁、主畫面、Channel 設定、安全模式說明、Measurement/Station Recipe、通知報告與 Email 相關頁面開始替換硬編碼字串。建立專業詞彙 glossary：Voc、Jsc、PCE、FF、Rs、Rsh、NPLC、Compliance Current、Line Resistance、Safety Mode 等需固定中英文對照。 |
| Acceptance Criteria | (1) 全域設定可選擇繁中、英文、中文+英文三種 UI language。 (2) GUI label/button/tooltip/help dialog 不再大量硬編碼中文；新增字串需進入 i18n registry。 (3) 雙語模式重要按鈕與危險/安全相關提示同時顯示中英文。 (4) CSV / JSON / log 的 canonical keys 維持英文，不因 UI 語言切換而改變。 (5) PDF/email 報告標題與段落可依使用者偏好語言輸出。 (6) 缺少翻譯 key 時有 fallback，不造成 GUI crash。 (7) 新增/修改 README 或 docs 說明如何新增翻譯 key 與避免資料欄位被翻譯。 |
| Notes for future AI maintainers | 不要使用 Qt `tr()` 零散硬寫而沒有集中字典，因為本專案還需要 PDF/email/report template 使用相同翻譯。資料層 key 永遠維持英文；只有 View / report presentation layer 做翻譯。安全提示與硬體操作警告應優先雙語化。 |

---

## 5. P3 — 打包、文件、repository hygiene、低風險整理

### OI-011 — 打包依賴與 artifact 清理規則驗證

| 欄位 | 內容 |
|---|---|
| Priority | P3 |
| Status | Open |
| Area | `requirements.txt`, `build_and_deploy.py`, `.spec`, docs, root legacy files |
| Evidence | 過去曾遇到 EXE 缺少 dependency；專案整包仍包含 `__pycache__`、logs、data runtime outputs、temp files、CHANGESET_MANIFEST 等。 |
| Next Action | 建立/更新 requirements；打包時排除 `__pycache__`, logs, data runtime outputs, stamped backups, temporary analyzer artifacts, old manifests；保留互動式路徑與是否打包 config 的既有功能。 |
| Acceptance Criteria | 乾淨 release ZIP 不含 runtime data/cache/legacy；EXE 啟動無 ModuleNotFoundError；README 記載打包依賴。 |

---

### OI-012 — Legacy/snapshot 檔案集中整理

| 欄位 | 內容 |
|---|---|
| Priority | P3 |
| Status | Done |
| Area | Project tree, `_local_only/`, `docs/CODEBASE_MAP.md`, `.gitignore` |
| Evidence | 2026-08-19 repository-wide audit 確認 103 個 stamped snapshot / delivery manifest / obsolete build spec 不屬於 runtime、build、test 或正式 Git history；已保留相對路徑集中搬至本機 `_local_only/legacy_snapshots/`。另外的 manuals、private Office documents 與 scratch utilities 亦按類別集中，完整搬移清單保存在 local-only manifest。 |
| Next Action | 已完成。後續 local-only 文件只放入 `_local_only/`；若要重新加入 Git，必須先驗證 private metadata、redistribution rights、runtime necessity 與 tracking policy。 |
| Acceptance Criteria | active source tree 中只保留正式 runtime module；AI 與維護者不會誤改歷史備份檔；正式發行包更乾淨。 |

---

### OI-027 — 整理 ADR 重複編號與 ADR_INDEX 一致性

| 欄位 | 內容 |
|---|---|
| Priority | P3 |
| Status | Open |
| Area | `docs/adr/`, `docs/ADR_INDEX.md` |
| Evidence | `docs/adr/` 存在多個重複編號，如 0023、0024、0025 系列。ADR_INDEX 規則若要求不可重複，現況會造成引用混亂。 |
| Next Action | 保留歷史檔但標註 duplicate/superseded，或重新編號並在 ADR_INDEX 記錄 renumbered/superseded 關係；後續新增 ADR 從目前最大編號後嚴格遞增。 |
| Acceptance Criteria | ADR_INDEX 可唯一定位每個架構決策；重複編號不再造成引用混亂。 |

---

### OI-028 — README 改寫為正式入口文件

| 欄位 | 內容 |
|---|---|
| Priority | P3 |
| Status | Open |
| Area | `docs/README.md` |
| Evidence | README 目前偏向近期功能追加紀錄，尚不像正式安裝/操作/打包入口文件。 |
| Next Action | 改成：專案目的、安裝需求、啟動方式、使用流程、設定檔位置、動態 Channel 工作流、安全停止/緊急停止、測試方式、打包方式、已知限制/OPEN_ITEMS。 |
| Acceptance Criteria | 新使用者能只靠 README 完成安裝、啟動、基本操作與打包；README 不再只是 change log。 |

---

### OI-029 — `main.py` 載入 QSS 改用 `config.get_resource_path()`

| 欄位 | 內容 |
|---|---|
| Priority | P3 |
| Status | Done |
| Area | `main.py`, `config.py`, PyInstaller packaging |
| Evidence | `main.py` 仍可能直接讀取 `assets/style.qss`；在 PyInstaller 或不同 working directory 下可能失敗。 |
| Next Action | 將 QSS 與外部資源讀取改成 `config.get_resource_path("assets/style.qss")`；補 pyinstaller add-data 設定。 |
| Acceptance Criteria | `python main.py` 與 onefile EXE 都能載入 QSS；換 working directory 也不失敗。 |

**Completed 2026-05-15 update:** `main.py` now loads `assets/style.qss` via `config.get_resource_path("assets/style.qss")`, so startup no longer depends on the process working directory. Syntax check passed for `main.py`.

---

### OI-030 — `user_settings.json` 個人路徑 release 隔離

| 欄位 | 內容 |
|---|---|
| Priority | P3 |
| Status | Done |
| Area | `config/user_settings.json`, `config/user_settings.example.json`, `build_and_deploy.py`, `.gitignore`, config defaults |
| Evidence | Uploaded project ZIPs contained `config/user_settings.json` with personal/cloud drive paths. These paths are local runtime preferences and should not be part of a release artifact. |
| Impact / Risk | Personal path leakage can expose user directory structure and can break another machine at startup if it tries to use unavailable drives. It also makes release packages environment-specific instead of reproducible. |
| Next Action | 已完成：`config/user_settings.json` was sanitized to blank local defaults; `config/user_settings.example.json` added; release build excludes `user_settings.json`; `.gitignore` marks it as local-only. Runtime still creates/uses safe default `data/` and `logs/` through existing config path resolution. |
| Acceptance Criteria | Release ZIP does not contain real personal paths; example file documents expected keys; first startup can use default local data/log directories; user may still change paths in GUI without those paths entering future release packages. |
| Notes for future AI maintainers | Do not commit or ship real local paths. If you need to demonstrate user settings, update `user_settings.example.json`, not `user_settings.json`. |

**Completed 2026-05-15 update:** user settings release isolation implemented and local path file sanitized.

---

### OI-031 — UI generated files 與 `.ui` 檔案一致性檢查

| 欄位 | 內容 |
|---|---|
| Priority | P3 |
| Status | Open |
| Area | `gui/ui/*.ui`, `gui/ui/*_ui.py`, `compile_ui.py`, build/deploy tooling |
| Evidence | 專案同時存在 `.ui` 與編譯後 `_ui.py`，若只改 `.ui` 未重新 compile，runtime 可能不一致。 |
| Next Action | 新增 `tools/check_ui_compiled.py` 或在 build 前自動跑 `compile_ui.py`；檢查 timestamp/hash。 |
| Acceptance Criteria | 修改 UI 後 `_ui.py` 必定同步；build/deploy 會阻止 stale generated UI。 |

---

### OI-032 — logs/data/cache 不應進入 patch/release 包

| 欄位 | 內容 |
|---|---|
| Priority | P3 |
| Status | Done |
| Area | `build_and_deploy.py`, `.gitignore`, release profile, patch packaging discipline |
| Evidence | Earlier whole-project ZIPs included runtime data, logs, and `__pycache__`. These are not source artifacts and can contain private experimental output or make patch packages unnecessarily large. |
| Impact / Risk | Shipping logs/data/cache increases ZIP size, leaks private experiment traces, and creates confusion about which files are runtime outputs versus active source. It can also cause stale `.pyc` files to be inspected by future maintainers. |
| Next Action | 已完成：`build_and_deploy.py` sanitizes onedir output before zipping and removes `__pycache__`, `.pyc/.pyo`, logs/tmp files, runtime schedule state, local user settings, notification settings, and `CHANGESET_MANIFEST.md`. `.gitignore` also documents these exclusions. |
| Acceptance Criteria | Release package is reproducible and excludes runtime data/cache/secrets; empty `data/` may be created for runtime use but does not contain previous experiment outputs; patch packages should continue to include only modified/new files. |
| Notes for future AI maintainers | If new runtime output folders are added, update both build exclusion rules and `.gitignore`. Never include `__pycache__` in patch ZIPs. |

**Completed 2026-05-15 update:** release cleanup implemented in build script and `.gitignore`.

---

### OI-033 — Scheduler overload warning 與 skip / catch-up policy

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `core/measurement_scheduler.py`, `core/measure_engine.py`, `gui/main_window.py`, `gui/config_tabs/measurement_tab.py`, `core/summary_logger.py`, `config/config_settings.json` |
| Evidence | Previous implementation had GUI overload warning and flexible catch-up metadata, but no operator-selectable strict skip policy or max delay threshold. Therefore a permanently overloaded schedule could keep measuring stale overdue occurrences indefinitely. |
| Impact / Risk | In long-term reliability experiments, excessive delay can invalidate intended cadence. Without a strict policy, a 10-minute channel could be measured hours late while still appearing as a normal delayed point. Without summary metadata, skipped/catch-up behavior cannot be audited. |
| Next Action | 已完成：Config / Measurement tab now exposes scheduler policy (`flexible_catch_up` or `strict_skip`) and `MAX_ALLOWED_DELAY_SEC`; `MeasurementScheduler` applies strict skip when `delay_sec` exceeds threshold; `MeasureEngine` records skipped occurrences into Summary with `Scheduler_Policy`, `Scheduler_Max_Allowed_Delay_Sec`, and `Scheduler_Skip_Reason`, while preserving cadence by advancing `next_due` from scheduled due + interval. |
| Acceptance Criteria | Flexible mode measures overdue channels and records delay/conflict. Strict skip mode skips overdue occurrences beyond threshold, writes `strict_skip_delay_exceeded` to log/Summary, advances next due without drift, and does not attempt IV measurement for skipped occurrence. Startup overload dialog displays the active policy. |
| Notes for future AI maintainers | Do not calculate next due from actual skip/finish time. The scientific cadence rule remains scheduled_due + interval. If adding per-channel policy later, retain global defaults and record policy metadata in Summary. |

**Completed 2026-05-15 update:** strict skip / max delay policy implemented with Config UI, scheduler logic, summary metadata, and log traceability.

---

### OI-035 — Remove `locals()` / undefined `data_dict` hack in SummaryLogger metadata

| 欄位 | 內容 |
|---|---|
| Priority | P0 |
| Status | Done |
| Area | `core/summary_logger.py` |
| Evidence | Confirmed in `SummaryLogger.update_summary_report()`: the `#Offset_current_A:` header uses `self._get_meta(results if "results" in locals() else data_dict, ...)`. `data_dict` is not defined in this function scope. The code currently survives only because `results` exists in `locals()`, but this is fragile and misleading. |
| Impact / Risk | This is a hidden maintenance hazard. A future refactor, variable rename, extracted helper, or alternate call path may trigger a `NameError` during summary header creation. Because this path runs during data persistence, failure can interrupt summary logging and cause missing metadata for offset-current traceability. |
| Next Action | Replace the expression with `self._get_meta(results, "offset_current", "offset_current_A", default="")`. Add a small regression test or script that calls `update_summary_report()` with minimal results and with offset metadata present/missing. |
| Acceptance Criteria | `core/summary_logger.py` contains no reference to undefined `data_dict` inside `update_summary_report()`. Summary header writes `#Offset_current_A:` correctly when provided and blank when absent. Minimal summary logging works without relying on `locals()`. |
| Notes for future AI maintainers | Avoid `locals()` as a control-flow mechanism in logger code. Logger functions should be deterministic and explicit because they define scientific traceability. |

**Completed 2026-05-15 update:** `core/summary_logger.py` now calls `self._get_meta(results, "offset_current", "offset_current_A", default="")` directly. The undefined `data_dict` fallback and `locals()` control flow were removed.

---

### OI-036 — Invalid numeric parsing should not be silently coerced into scientific zeroes

| 欄位 | 內容 |
|---|---|
| Priority | P0 |
| Status | Done |
| Area | `core/numeric_utils.py`, `core/IV_parameter_analysis_utils.py`, `core/summary_logger.py`, `core/iv_curve_logger.py`, `core/trend_spec.py`, `gui/trend_chart_window.py`, `gui/trend_snapshot_renderer.py`, `gui/widgets/iv_analysis_widget.py` |
| Evidence | Earlier code had scattered parsing policies: some paths used `float(..., default=0.0)` or logger helper defaults, making it hard to distinguish physical zero from invalid strings/blank/non-finite values. Phase 1 reduced some risk but lacked a central policy and invalid warnings. |
| Impact / Risk | If malformed values enter as `0.0`, they can create false degradation/recovery points in PCE/Jsc/FF/HI and pollute Summary/Trend outputs. Long reliability datasets are especially vulnerable because one bad point can look like a real transient event. |
| Next Action | 已完成 phase 2：新增 `core/numeric_utils.py` with `parse_float_or_nan`, `parse_float_or_none`, `is_valid_number`, and optional warning logs. IV analysis arrays convert invalid point values to NaN, not 0.0; Summary/IV curve loggers render invalid values as blanks; Trend and snapshot renderers omit invalid y values; valid `0` / `0.0` remains accepted. |
| Acceptance Criteria | Empty strings, `None`, invalid text such as `abc`, `NaN`, and `inf` are not plotted or summarized as scientific zero. Valid numeric zero remains `0.0`. Invalid parsing can produce warning logs with field/context. Summary and trend display blanks/omissions instead of fake zeros. |
| Notes for future AI maintainers | Use `core.numeric_utils` for all new parsing. Do not add new `except Exception: return 0.0` logic in analysis, logging, or plotting code. |

**Completed 2026-05-15 update:** centralized invalid numeric policy implemented and connected to analysis, loggers, Trend, snapshot, and IV analysis UI.

---

### OI-037 — Trend chart GUI cache now has bounded in-memory growth

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `gui/trend_chart_window.py`, trend history loading, long-term monitoring UI |
| Evidence | Confirmed pre-fix: `TrendChartWindow.add_new_data()` appended every completed measurement to `self.all_data_history` with no retention limit. Long reliability runs could accumulate hundreds of thousands of Python dicts in the GUI. |
| Impact / Risk | Unbounded GUI memory could cause slow filtering, slow repaint, and eventual out-of-memory. The scientific archive should be CSV, not an unlimited live-monitor list. |
| Next Action | Completed first implementation: `TrendChartWindow` uses `config.get_trend_runtime_settings()` and defaults to 50,000 in-memory GUI points. When the limit is exceeded, oldest GUI cache entries are dropped and per-series cache is rebuilt. Raw CSV data is not deleted. |
| Acceptance Criteria | Trend chart memory remains bounded during long runs; old raw data remains available on disk; cache trimming is logged with dropped point count. |
| Notes for future AI maintainers | Do not solve GUI cache growth by deleting raw data files. The live chart cache and canonical scientific CSV archive are separate. A future lazy-loader/downsampler may extend this if users need historical browsing beyond the live cache. |

**Completed 2026-05-15 update:** bounded trend GUI cache implemented with configurable max in-memory points.

---

### OI-038 — Main-thread config file writes can freeze the GUI

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `gui/main_window.py`, `gui/settings_save_controller.py`, `config.save_json_file()`, channel enable/disable workflow |
| Evidence | `MainWindow.on_channel_toggled()` previously called `config.save_json_file(config.CHANNEL_SETTINGS_FILE, all_settings)` synchronously after user confirmation. If config was on Google Drive/network disk or blocked by antivirus/cloud sync, the Qt main thread could freeze. |
| Impact / Risk | A frozen UI during long hardware operation can be mistaken for a crash and delays operator response. Rapid toggling could also write the same JSON repeatedly, increasing I/O load and race risk. |
| Next Action | 已完成：新增 `JsonDebouncedSaveController` using QTimer debounce + background QRunnable. Channel checkbox changes update pending in-memory state immediately, coalesce rapid edits, then save latest `channel_settings.json` asynchronously. Save failures rollback the card via `ChannelCard.set_checked()` and show/log an error. |
| Acceptance Criteria | Rapid checkbox changes are coalesced; UI no longer performs immediate blocking disk write in `on_channel_toggled()`; failed async save reverts UI safely without recursive signal loop; `on_start_clicked()` reads pending in-memory settings so a just-confirmed checkbox change is honored even before debounce flush completes. |
| Notes for future AI maintainers | For critical safety settings, define whether they require immediate blocking persistence or an explicit save/flush step. For normal UI checkbox changes, use the debounced save controller. |

**Completed 2026-05-15 update:** debounced asynchronous channel settings persistence implemented.

---

### OI-039 — Trend chart update path uses throttled redraw and per-series cache

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `gui/trend_chart_window.py`, `gui/widgets/trend_plot_widget.py` |
| Evidence | Confirmed pre-fix: every new point immediately called `update_chart()`, and each visible series rebuilt itself by filtering/sorting the full `all_data_history`. This was O(N) per update and repeated during channel bursts. |
| Impact / Risk | Multiple channels finishing close together could repeatedly sort the full history and block the GUI thread, causing visible render lag and CPU spikes. |
| Next Action | Completed first implementation: `add_new_data()` now appends into a per-series ordered cache and schedules chart redraw through a single-shot `QTimer`; `update_chart()` reads `self._series_history` directly and no longer performs full-list per-series filter/sort. |
| Acceptance Criteria | During bursts of 32 channel results, redraw requests are debounced to the configured throttle interval and per-series data is reused without full-history sort. |
| Notes for future AI maintainers | This item is paired with OI-037. If historical lazy loading/downsampling is added later, update the per-series cache contract rather than reintroducing full-list scans. |

**Completed 2026-05-15 update:** render throttling and per-series ordered cache implemented.

---

### OI-040 — IVCurveLogger lacks a file-write lock

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `core/iv_curve_logger.py`, future multi-SMU / parallel measurement architecture |
| Evidence | Confirmed in `core/iv_curve_logger.py`: unlike `SummaryLogger`, `IVCurveLogger` does not define or use a `threading.Lock()` around CSV file writes. The current single-SMU flow reduces the immediate risk, but the logger is not future-proof for parallel writers. |
| Impact / Risk | If the system later supports multiple SMUs, parallel scans, queued diagnostics writing curve files, or asynchronous file writers, concurrent writes may interleave, corrupt CSVs, or produce partial headers/rows. This would damage raw IV traceability. |
| Next Action | Add `self.lock = threading.Lock()` to `IVCurveLogger` and wrap file creation/writing with `with self.lock:`. If async/batch logging is introduced later, use one writer queue per output file or an atomic write-then-rename strategy. |
| Acceptance Criteria | Concurrent simulated calls to save IV curves do not corrupt files. Headers and rows remain complete. Existing single-thread behavior and output format remain unchanged. |
| Notes for future AI maintainers | Do not assume “one SMU today” means “no lock needed forever.” Logger APIs should be safe at module boundaries. |

**Completed 2026-05-15 update:** `core/iv_curve_logger.py` now imports `threading`, creates `self.lock`, and wraps the full IV CSV file-write block with `with self.lock:` while preserving the existing output format.

---

### OI-041 — Checkbox rollback can trigger a recursive signal feedback loop

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `gui/main_window.py`, `gui/widgets/channel_card.py`, dynamic channel enable/disable UI |
| Evidence | Confirmed in `MainWindow.on_channel_toggled()`: when the user cancels confirmation or config save fails, code calls `self.cards_by_ch_id[ch_id].set_checked(old_val)` or `set_checked(False)`. If `set_checked()` emits the checkbox `toggled` signal, it can re-enter `on_channel_toggled()`. |
| Impact / Risk | Programmatic UI rollback can cause duplicate confirmations, repeated file writes, inconsistent card state, or in worst cases recursive signal handling. This is especially risky if combined with async/debounced config saves. |
| Next Action | During programmatic rollback, block checkbox signals: `card.chk_enabled.blockSignals(True)`, call `card.set_checked(old_val)`, then restore `blockSignals(False)` in a `finally` block. Alternatively expose a `set_checked_silent()` method on the channel card widget. |
| Acceptance Criteria | Cancelling a toggle confirmation or simulating save failure restores the checkbox once without triggering a second confirmation or additional save attempt. Unit/manual test logs show only one user action and one rollback path. |
| Notes for future AI maintainers | Make sure blocking signals happens at the actual checkbox object, not only the wrapper widget, unless the wrapper implements silent state updates correctly. |

**Completed 2026-05-15 update:** Verified in `gui/widgets/channel_card.py`: `ChannelCard.set_checked()` blocks `chk_enabled` signals before programmatic rollback and restores them after setting the checkbox state. `MainWindow.on_channel_toggled()` rollback paths call this wrapper, so the recursive checkbox feedback loop is already mitigated in the current codebase.

---

### OI-042 — Relay reconnect must not unconditionally `reset_all()` during active measurement

| 欄位 | 內容 |
|---|---|
| Priority | P0 |
| Status | Done |
| Area | `core/hardware/hardware_manager.py`, `core/measure_engine.py`, relay reconnect policy, relay path validity |
| Evidence | Confirmed pre-fix: `HardwareManager.connect_relay_if_needed()` called `self.relay.reset_all()` immediately after `self.relay.auto_scan()` succeeded. This is safe during idle startup/shutdown, but unsafe if a transient relay disconnect/reconnect is detected while a channel path is actively being scanned. |
| Impact / Risk | An unconditional `reset_all()` during active measurement can physically open the active relay path while the scan loop still treats the channel as connected. This can create open-circuit artifacts, compliance events, invalid IV points, or uncontrolled recovery behavior. |
| Next Action | Completed first safe policy: reconnect during idle may reset all relays; reconnect during active measurement is treated as unsafe. `MeasureEngine` now tracks active channel context and refuses to perform active-measurement reconnect/reset. The affected scan is stopped/marked unsafe instead of silently continuing. Future work may add verified path restore, but must include explicit data-validity logging. |
| Acceptance Criteria | A relay transient during active measurement does not silently reset all relays and continue collecting data. The system either aborts/stops the affected channel path or, in a future implementation, explicitly restores the intended path before any further SMU reads. Logs include active channel context and the decision that reconnect/reset was blocked during measurement. |
| Notes for future AI maintainers | Treat relay state as part of the scientific measurement condition. Resetting relay paths is not merely communication recovery; it changes the physical circuit. Do not reintroduce unconditional `reset_all()` in runtime reconnect paths. |

**Completed 2026-05-15 update:** `HardwareManager.connect_relay_if_needed()` now accepts reset/context parameters and will not reset relays during active measurement. `MeasureEngine` tracks active channel context, blocks active-measurement relay reconnect/reset, logs the unsafe condition, and requests stop instead of continuing with uncertain relay state.

---

### OI-043 — SMU PyVISA backend initialization should fail explicitly with actionable guidance

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `driver/smu_driver.py`, startup diagnostics, GUI hardware status / troubleshooting |
| Evidence | Confirmed in `SMUDriver.__init__()`: it tries `pyvisa.ResourceManager()`, then falls back to `pyvisa.ResourceManager("@py")` inside the `except`. If both backends fail, the second exception propagates during object construction without a controlled error message or user-facing troubleshooting path. |
| Impact / Risk | Missing NI-VISA / pyvisa-py backend or broken VISA installation can crash startup or leave users with a raw Python exception instead of a clear instruction. This is likely during deployment on new lab PCs or packaged EXE installs. |
| Next Action | Wrap both backend attempts and raise/log a clear `VisaBackendUnavailableError` or set driver status to unavailable with a precise message: install NI-VISA or pyvisa-py, check PATH/drivers, and restart. Surface the error in LogWindow / Troubleshooter. |
| Acceptance Criteria | On a machine without usable VISA backend, the app starts far enough to show a clear hardware-not-ready message and troubleshooting guidance, or fails gracefully with a controlled dialog/log. No ambiguous `ResourceManager` traceback is the only feedback. |
| Notes for future AI maintainers | The fallback to `@py` is useful, but it should not hide deployment requirements. Make driver initialization errors actionable for non-programmer operators. |

**Completed 2026-05-15 update:** `driver/smu_driver.py` now initializes VISA backends through `_create_resource_manager()`, tries default VISA and `@py`, then raises `VisaBackendUnavailableError` with actionable guidance if both fail. `main.py` catches this exception, logs it, shows a controlled Qt critical dialog, and exits cleanly instead of exposing an ambiguous `ResourceManager` traceback.

---

## 6. 已由近期修改處理或部分處理的項目

| 原始需求 | 目前狀態 | 後續追蹤 |
|---|---|---|
| 每個 channel 使用自己的量測間隔，而非全體共用第一個 channel 的 interval | 已由 Dynamic Logical Channel Mode / per-channel scheduler 處理；2026-05-15 進一步修正為 drift-free `scheduled_due + interval` 並記錄衝突 delay | Scheduler 重啟持久化見 OI-016；overload warning / skip policy 見 OI-033。 |
| 主畫面不固定顯示 32 個 channel | 已完成 dynamic logical channel list | Relay matrix 同步見 OI-006；channel schema migration 見 OI-023。 |
| `CH_V##`, `CH_I##`, `CH_C##` 分區顯示 | 已完成 environment-grouped card layout | 若新增 environment family，需更新 label/prefix 規則。 |
| Channel checkbox 語意清楚化與二次確認 | 已完成 `開始循環量測` / `暫停循環量測` | 量測中切換同步規則見 OI-017。 |
| 左側全域控制按鈕語意清楚化 | 已完成 `▶ 啟動全部循環量測` / `⏸ 停止全部循環量測` 與狀態列 | 緊急停止分層見 OI-009；狀態機拆分見 OI-015。 |
| ZIP 交付不放 stamped backup / CHANGESET_MANIFEST | AI instructions 已更新 | 根目錄殘留 manifest 清理見 OI-014；打包規則見 OI-032。 |

---

## 7. 建議執行順序

### 第一批：安全與資料正確性

1. OI-042 — Relay reconnect must not unconditionally `reset_all()` during active measurement。
2. OI-036 — Invalid numeric parsing should not be silently coerced into scientific zeroes。
3. OI-019 — R-line history 與 30 天校正提醒。
4. OI-020 — IV / Summary / Trend 單位對齊。

> 2026-05-15 update: OI-034、OI-035、OI-042、OI-019 已完成；OI-036 已完成；OI-013、OI-018、OI-001 已於前一批 hardening 中完成。

### 第二批：長效實驗穩定性與 UI 效能

1. OI-037 — Trend chart `all_data_history` has unbounded in-memory growth。
2. OI-039 — Trend chart update path performs high-cost O(N) filter/sort on every new point。
3. OI-038 — Main-thread config file writes can freeze the GUI。
4. OI-016 — Scheduler next_due_time 持久化。
5. OI-033 — Scheduler overload warning 與 skip / catch-up policy。
6. OI-017 — 量測中切換 checkbox 的同步規則。
7. OI-004 — Trend chart 跨停止/重啟歷史。
8. OI-026 — experiment_uid / run_session_id。
9. OI-015 — runtime state machine（OI-009 shutdown 分層已於 2026-05-15 完成）。

> 2026-05-15 update: OI-037、OI-039 已完成；OI-033 已完成 GUI warning / flexible catch-up / strict skip policy；OI-041 已驗證由 `ChannelCard.set_checked()` 的 signal blocking 處理完成。

### 第三批：架構整理與測試

1. OI-015 — runtime state machine。
2. OI-002 — MeasureEngine service wiring。
3. OI-008 — Mock hardware 與 GUI smoke test。
4. OI-023 — channel_settings schema migration。
5. OI-006 — Relay matrix 與 logical channel 對照同步。

> 2026-05-15 update: OI-040、OI-043 已完成。

### 第四批：打包與文件清理

1. OI-014 — 移除根目錄 CHANGESET_MANIFEST。
2. OI-011 / OI-032 — packaging profile 與排除規則。
3. OI-027 — ADR 編號整理。
4. OI-028 — README 正式化。
5. OI-012 — legacy/snapshot 集中整理。

> 2026-05-15 update: OI-014、OI-029、OI-030、OI-032 已完成；`main.py` 會以 `config.get_resource_path()` 載入 QSS，release build 會清理 runtime/local-only artifacts。

---


### 第五批：全域設定 UX、雙語化與 Email 報告派送

1. OI-045 — SystemConfigDialog Shell 重構：左側導覽、Dashboard、進階折疊，並拆分 Measurement Recipe / Station Recipe。（Done 2026-05-16）
2. OI-046 — 中英文 / 雙語使用者介面與 i18n 字串治理。
3. OI-047 — 使用者 Email 報告排程、專案 PDF 分信寄送與主管 CC。

> 這一批主要改善多人/多國籍實驗室使用情境。SystemConfigDialog shell 已完成第一階段；下一步建議先做 OI-046 i18n registry，再接 OI-047 Email report service。

## 8. 維護規則

1. 每次修改程式或文件後，若發現新的技術債、未完成功能或已完成項目，必須同步更新本檔。新增 open item 不得只寫標題或簡短 bullet，必須包含：Evidence、Impact / Risk、Area、Next Action、Acceptance Criteria、Priority、Status，以及必要的 Notes for future AI maintainers。
2. 若 open item 影響架構、資料流、Signal/Slot、JSON schema 或 build/deploy 規則，需同步新增或更新 ADR。
3. 若某項 open item 完成，不要刪除；將 `Status` 改為 `Done`，並在該項下方加入完成日期、修改檔案與驗證方式。
4. 若使用者明確取消或延後某項，將 `Status` 改為 `Cancelled` 或 `Deferred`，並保留理由。
5. 本檔只追蹤目前真實狀態與下一步，不應把尚未接線的 scaffold 描述成 active runtime。
6. Open item 的 Evidence 不得包含 secret、token、chat ID 或個人敏感路徑；若發現 secret，僅描述「存在真實 secret」，不要把 secret 值寫入文件。

### 2026-05-15 critical hardening closure note

The following critical items were updated in the current package: Telegram secrets removed from release config and replaced with TXT-file indirection, `offset_current` applied to corrected IV data, channel diagnostics moved to queued signal requests, scheduler `next_due` persisted, and scheduler overload warning logged. Remaining follow-up: define strict skip/catch-up UI policy for overloaded schedules if the user wants hard cadence enforcement rather than flexible delayed measurements.

---

### OI-048 — System Config active-scope readiness, environment relay ranges, and R-line diagnostics

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `config.py`, `gui/system_config_dialog.py`, `gui/config_tabs/recipe_tab.py`, `gui/config_tabs/station_recipe_tab.py`, `gui/config_tabs/relay_tab.py`, `gui/config_tabs/personnel_tab.py`, `gui/config_tabs/rline_diagnostics_tab.py`, `config/*.json`, `docs/adr/0051-active-scope-config-dashboard-and-rline-diagnostics.md` |
| Evidence | 使用者指出 Dashboard 不應因未使用的 chamber/vacuum/environment sensor 離線而阻擋量測；R-line 組合過多，應只檢查目前 active channel setting card 使用到的 pair；relay occupancy 應以環境與 SMU+/SMU- 3x2 矩陣呈現；Station Recipe 與 Environment Recipe 對使用者而言是同一功能；R-line 校正資訊需要 3D map 快速看出異常組合。 |
| Impact / Risk | 若仍以全域硬體檢查作為 readiness，未使用設備會造成假錯誤並干擾可正常執行的量測；若 relay/R-line 狀態沒有 environment/polarity 分解，研究人員很難快速判斷哪個環境仍有可用 relay capacity 或哪個 relay pair 可能異常。 |
| Next Action | 已完成第一版 GUI 與 schema 實作。後續在實機上執行 System Config smoke test：切換 Dashboard、Relay Mapping、Environment / Station Recipes、Measurement Recipes、R-line Diagnostics；確認 save/reload、environment relay range validation、safe mode 說明、R-line 3D 圖與 legacy recipe migration 行為。 |
| Acceptance Criteria | Dashboard 僅顯示 active channel 所需環境與 R-line；未使用環境離線不 blocking；Relay Mapping 可用環境分區設定 relay range 並顯示 3x2 used/free；Measurement Recipes 內建四組 PSC recipe 且可 duplicate/edit；Environment / Station Recipes 不再將 SMU/Relay/Chamber 連線欄位作為新 recipe 主體；R-line Diagnostics 可依 environment 顯示 3D pair map 與 active readiness。 |
| Notes for future AI maintainers | 不要把 `hardware_map.json` 誤當 active relay assignment source；active occupancy 應從 `channel_settings.json` 推導。不要重新把 SMU VISA / Relay COM port 放回 Environment / Station Recipe。3D R-line map 若 Matplotlib 不可用，必須保留表格 fallback。 |

**Completed 2026-05-17 update:** see ADR-0051. Implemented in current codebase; `py_compile` validation passed. GUI and hardware smoke tests remain required on target workstation.

---

### OI-049 — IV validity metadata must remain boolean through unit standardization

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `core/IV_parameter_analysis_utils.py`, `tests/unit/test_iv_parameter_analysis.py` |
| Evidence | 初次 offline regression 顯示 `_standardize_units()` 將 `valid_F_Raw=False` 當一般 numeric field 解析，輸出成 `0.0`；有效資料則會變成 `1.0`。 |
| Impact / Risk | 下游若以 strict boolean contract 判斷 malformed/insufficient IV data，numeric coercion 會模糊 metadata 語意並增加 JSON/GUI contract drift。 |
| Next Action | 已完成：unit standardization 先辨識 `valid_*` metadata 並保留 `bool`，其餘 Voc/Isc/Jsc/FF/PCE/Rs/Rsh/Pmpp 單位與公式不變。 |
| Acceptance Criteria | 空掃描的 `valid_F_Raw` / `valid_R_Corr` 為 `False` boolean；合法掃描為 `True` boolean；56 項 offline suite 全通過。 |
| Notes for future AI maintainers | 新增 analysis metadata 時不可直接套用物理單位轉換；先分類 value field 與 contract metadata。 |

**Completed 2026-08-19:** regression added and passing.

---

### OI-050 — Failed channel measurements can be counted as scheduler-completed

| 欄位 | 內容 |
|---|---|
| Priority | P0 |
| Status | Done |
| Area | `core/measure_engine.py::measure_single_channel`, `start_scan_cycle`, scan result/status semantics |
| Evidence | `measure_single_channel()` catches non-interrupt exceptions, performs safe cleanup, but returns without an explicit success/failure result. `start_scan_cycle()` then unconditionally calls `item.mark_completed()`, increments `completed_channel_count`, and logs the channel as completed. Offline injected SMU/relay/analysis/logger failures confirmed safe output cleanup but exposed this status ambiguity. |
| Impact / Risk | A failed IV read, analysis, or logger write can be represented as scheduler-completed even though no trustworthy result was persisted. Operators and automation may misinterpret completion counts or finish reason. |
| Next Action | 2026-09-20 已實作 ChannelOutcome、故障即停止全域排程、finish payload 與 runtime state 失敗分類；成功計數與結果 signal 僅於存檔及清理完成後產生。後續在測試機依 MACHINE_TEST_GUIDE.md 驗收實際硬體。 |
| Acceptance Criteria | Injected failures always produce SMU OFF / relay reset and do not increment successful completion count; `scan_finished` and persistent log include the failure classification; valid one-shot scans remain unchanged. |
| Notes for future AI maintainers | Do not fix this by removing the `finally` cleanup or by swallowing errors at a higher layer. Safety cleanup and truthful scientific completion are separate requirements. |

**Completed 2026-09-20:** ADR-0061；離線注入讀取、Relay、分析（含 invalid flag）、曲線／Summary 寫檔、校正與清理失敗，確認不誤算完成、不進入下一通道。實機驗證尚待測試機執行。

---

### OI-051 — MainWindow channel-card completion display uses stale metric aliases

| 欄位 | 內容 |
|---|---|
| Priority | P1 |
| Status | Done |
| Area | `gui/main_window.py::on_measurement_finished`, `core/measure_engine.py`, `core/measurement_schema.py` |
| Evidence | Production `channel_measurement_finished` emits canonical keys such as `Voc_F_Corr`, `PCE_F_Corr`, `Voc_F_Raw`, and `PCE_F_Raw`. `MainWindow.on_measurement_finished()` still reads legacy `Voc_f` and `Eff_f`, defaulting both to zero when absent. IV monitor, Trend, and loggers consume the canonical schema. |
| Impact / Risk | The channel card can display `Voc: 0.000V | Eff: 0.00%` after a valid measurement while CSV/Trend contain correct non-zero values, reducing operator trust and potentially hiding a live device result. |
| Next Action | 2026-09-20 已新增 central forward_card_metrics：完整且有效 Corr 優先，其次 Raw 並標示來源；缺失／NaN 顯示無有效資料，真實零值保留；已完成真實 Qt card/controller 測試。 |
| Acceptance Criteria | A known non-zero mock result produces matching channel-card, IV monitor, Trend, and Summary values; missing/NaN values display invalid state rather than a fabricated zero. |
| Notes for future AI maintainers | Do not add another hard-coded alias list in the widget; reuse a centralized result accessor so signal emitters and consumers cannot drift again. |

**Completed 2026-09-20:** ADR-0061；並修正後續「已完成」狀態覆蓋卡片數值。完整 GUI/worker 測試確認量測完成後顯示非零結果。

---

### OI-052 — Formalize legacy timing/identity column mapping for exported summaries

| 欄位 | 內容 |
|---|---|
| Priority | P2 |
| Status | Open |
| Area | `core/summary_logger.py`, `core/iv_curve_logger.py`, `core/measurement_schema.py`, data migration/export documentation |
| Evidence | Current production schema records `Start_Time`, `Experiment_UID`, `Run_Session_ID`, `Channel_Label`, `Internal_CH_ID`, scheduled/actual times, direction-specific Raw/Corrected metrics, user/project/device, and raw file path. Historical names requested for regression review (`Start_ID`, `Cycle_Count`, `Abs_Time`, `Rel_Time`, `Channel`, `Device`, `User`, `Project`) do not have a documented one-to-one current schema mapping. |
| Impact / Risk | External analysis scripts may assume legacy column names while current CSV exports use newer identity/scheduler fields. Adding guessed duplicate columns would create schema ambiguity; leaving mapping undocumented increases migration risk. |
| Next Action | Inventory historical CSV consumers and define a versioned compatibility map or export adapter. Do not rename current canonical fields until downstream migration requirements are known. |
| Acceptance Criteria | A documented schema version states exact canonical fields, legacy aliases, units, direction/path encoding, and migration rules; automated logger tests cover the mapping without duplicated contradictory data. |
| Notes for future AI maintainers | The current regression intentionally tests fields actually emitted by production. Do not invent `Start_ID`/`Cycle_Count` semantics without authoritative historical data. |
