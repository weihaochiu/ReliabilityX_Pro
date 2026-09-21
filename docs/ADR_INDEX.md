# ADR Index

本文件為 ReliabilityX Pro 的 Architecture Decision Records（ADR）總索引，用於集中管理 `docs/adr/` 目錄中的架構決策文件，方便查找、追溯、比對與維護。

---

## 1. 目的

ADR 用於記錄重要的架構與設計決策，包括：

- 為什麼要修改
- 當時考慮過哪些方案
- 最後採用哪個方案
- 對哪些模組造成影響
- 後續是否被新的 ADR 取代

本索引檔的目的，是提供一個單一入口，讓開發者可以快速掌握目前專案的架構決策歷史，避免：

- 重複做出相同決策
- 新修改與舊架構衝突
- 修 bug 時造成既有功能回歸
- 無法追溯某項功能為何如此設計

---

## 2. 使用規則

1. 所有正式 ADR 文件一律放在 `docs/adr/` 目錄下。
2. 每新增一份 ADR，必須同步更新本 `docs/ADR_INDEX.md`。
3. ADR 編號採遞增制，不可重複，不可跳號重用。
4. 若新 ADR 取代舊 ADR，必須在本索引與 ADR 正文中都明確標示。
5. 涉及架構變更時，除新增 ADR 外，也應同步檢查是否需要更新：
   - `version_history.txt`
   - `ARCHITECTURE.md`
   - `CODEBASE_MAP.md`
   - `README.md`
   - `build_and_deploy.py`（若牽涉 UI / 資產 / 部署）
6. 在修改重大功能前，應先閱讀本索引與相關 ADR，避免功能回歸。

---

## 3. ADR 檔名規範

### 3.1 編號格式
採四位數流水號：

- `ADR-0001`
- `ADR-0002`
- `ADR-0003`

### 3.2 檔名格式
建議格式如下：

    0001-short-title.md
    0002-fix-trend-tooltip.md
    0003-measure-engine-split-strategy.md

---

## 4. ADR 狀態定義

| 狀態 | 說明 |
|---|---|
| Proposed | 已提出，但尚未正式採用 |
| Accepted | 已採用，為目前有效決策 |
| Superseded | 已被後續 ADR 取代 |
| Deprecated | 不再建議沿用，但舊系統可能仍存在 |
| Rejected | 曾被討論，但最終未採用 |

---

## 5. ADR 清單

| ADR ID | 標題 | 狀態 | 檔案 |
|---|---|---|---|
| ADR-0001 | 1. 標準化 Summary Logger 的輸出格式 | Accepted | `0001-standardize-summary-logger-output.md` |
| ADR-0002 | 2. 新增專用的「關閉程式」按鈕 | Accepted | `0002-add-dedicated-exit-button.md` |
| ADR-0003 | 3. 以 IV 曲線預覽視窗取代文字 Tooltip | Superseded | `0003-replace-tooltip-with-iv-preview.md` |
| ADR-0004 | 4. 修正 IV 曲線預覽功能的 CSV 解析錯誤 | Superseded | `0004-fix-iv-preview-parsing-error.md` |
| ADR-0005 | 5. 修正 IV 預覽功能的數據類型錯誤 (TypeError) | Superseded | `0005-fix-iv-preview-type-error.md` |
| ADR-0006 | 6. 為 IV 預覽功能增加對空數據的防禦性檢查 | Superseded | `0006-defensive-check-for-empty-iv-data.md` |
| ADR-0007 | 7. 移除 IV 曲線預覽視窗，恢復為文字提示 | Accepted | `0007-remove-iv-preview-widget.md` |
| ADR-0008 | 8. 防止監控視窗在關閉時被銷毀 | Accepted | `0008-prevent-monitor-windows-destruction-on-close.md` |
| ADR-0009 | 9. 新增將圖表儲存為 JPG 檔案的功能 | Accepted | `0009-add-save-plot-to-jpg-feature.md` |
| ADR-0010 | 10. 修正 IV 監控視窗中的語法錯誤 (SyntaxError) | Accepted | `0010-fix-syntax-error-in-iv-monitor-window.md` |
| ADR-0011 | 11. 修正 GUI 視窗中的屬性錯誤 (AttributeError) | Accepted | `0011-fix-attribute-errors-in-gui-windows.md` |
| ADR-0012 | 12. 優化圖表 X 軸顯示與擴充圖片匯出選項 | Accepted | `0012-improve-axis-and-export-options.md` |
| ADR-0013 | 13. 新增 IV Monitor 與 Trend Plot 圖片設定視窗與樣式持久化機制 | Accepted | `0013-add-plot-settings-for-iv-monitor-and-trend-plot.md` |
| ADR-0014 | Make Line Resistance Readout Update Immediately by Relay Combination | Accepted | `0014-make-line-resistance-readout-update-immediately-by-relay-combination.md` |
| ADR-0015 | Add Reopen Button for IV Monitor and Trend Chart and Restore MainWindow Worker Thread Architecture | Accepted | `0015-add-reopen-button-for-iv-monitor-and-trend-chart-and-restore-mainwindow-worker-thread-architecture.md` |
| ADR-0016 | Fix Hardware Reconnect Flow to Only Reconnect Disconnected Devices | Accepted | `0016-fix-hardware-reconnect-flow-to-only-reconnect-disconnected-devices.md` |
| ADR-0017 | Fix Summary Blank Fields and Add Env Monitoring | Accepted | `0017-fix-summary-blank-fields-and-add-env-monitoring.md` |
| ADR-0018 | ADR-0018: 修正多通道 IV 掃描的 Relay 路徑殘留問題 | Accepted | `0018-fix-shared-electrode-relay-path-isolation.md` |
| ADR-0019 | ADR-0019: 強化日誌系統穩定性，並導入 Session / Part 分檔機制 | Accepted | `0019-harden-log-manager-and-session-rotation.md` |
| ADR-0020 | 20. 新增通知中心與 Telegram 整點摘要機制 | Accepted | `0020-add-notification-center-and-telegram-reporting.md` |
| ADR-0021 | 0021. 重構 Trend Monitor 的範圍選擇、群組圖例與環境子圖 | Accepted | `0021-refactor-trend-monitor-scope-legend-env-subplot.md` |
| ADR-0022 | 0022. 以立即停止旗標修正停止量測延遲，並新增開始 / 停止 Telegram 通知 | Accepted | `0022-immediate-stop-flag-and-telegram-stop-notify.md` |
| ADR-0023 | ADR-0023: Introduce Stage-1 Environment & ISOS Foundation | Accepted | `0023-environment-isos-stage1.md` |
| ADR-0023 | ADR-0023: Telegram 定時摘要與趨勢圖改為支援 active scope 分組寄送 | Accepted | `0023-grouped-telegram-trend-notifications.md` |
| ADR-0023 | ADR-0023: MeasureEngine Phase 1 解耦 | Accepted | `0023-measure-engine-phase1-decoupling.md` |
| ADR-0024 | ADR-0024: Add Measurement Recipe Library | Accepted | `0024-add-measurement-recipe-library.md` |
| ADR-0024 | ADR-0024: Environment Stage-2 Channel Dialog Integration | Accepted | `0024-environment-stage2-channel-dialog.md` |
| ADR-0024 | ADR-0024: Telegram Trend Notifications Use Active-Scope PDF Reports | Accepted | `0024-telegram-pdf-trend-reports.md` |
| ADR-0025 | ADR-0025: Environment package import cleanup for Stage 2.1 | Accepted | `0025-environment-stage2_1-import-fix.md` |
| ADR-0025 | ADR-0022：以 Channel Boundary Graceful Stop 取代立即中斷，並新增 Telegram 停止/完成通知 | Accepted | `0025-graceful-stop-at-channel-boundary.md` |
| ADR-0026 | ADR 0026: Environment mapping redesign to relay segments | Accepted | `0026-environment-stage2_2-relay-segment-redesign.md` |
| ADR-0027 | ADR 0027: Environment Stage 2.4 Compatibility and Climate Wrapper | Accepted | `0027-environment-stage2_4-compatibility-and-climate-wrapper.md` |
| ADR-0028 | ADR 0028: Stage 2.5 Widget Dialog and Environment Tab Restructure | Accepted | `0028-environment-stage2_5-widget-dialog-and-tab-restructure.md` |
| ADR-0029 | ADR 0029: Channel Setting Dialog Widget Extension Fix | Accepted | `0029-channel-setting-dialog-widget-extension-fix.md` |
| ADR-0031 | ADR 0031: Channel Dialog Environment Dropdown and Alignment | Accepted | `0031-channel-dialog-environment-dropdown-and-alignment.md` |
| ADR-0032 | ADR 0032: Climate Chamber Widget Decomposition | Accepted | `0032-climate-chamber-widget-decomposition.md` |
| ADR-0033 | ADR 0033: System Config Dialog Import Fix and Stable Environment Package | Accepted | `0033-system-config-dialog-import-fix-and-stable-environment-package.md` |
| ADR-0034 | ADR 0034: Climate Tab Scroll and Top Widget Extraction | Accepted | `0034-climate-tab-scroll-and-top-widget-extraction.md` |
| ADR-0035 | ADR 0035: Environment Skeleton Unification and Option A Freeze | Accepted | `0035-environment-skeleton-unification-and-option-a-freeze.md` |
| ADR-0036 | ADR 0036: Environment Recipe Editor Shared-Entry Skeleton | Accepted | `0036-environment-recipe-editor-shared-entry-skeleton.md` |
| ADR-0037 | 0037 - Environment Tab Authoritative Entry and Instance Save Chain | Accepted | `0037-environment-tab-authoritative-entry-and-instance-save-chain.md` |
| ADR-0038 | ADR 0038: Dynamic Logical Channel and Per-Channel Scheduler | Accepted | `0038-dynamic-logical-channel-and-per-channel-scheduler.md` |
| ADR-0039 | ADR 0039: Environment-grouped channel list and end-channel flow | Accepted | `0039-environment-grouped-channel-list-and-end-channel.md` |
| ADR-0040 | ADR 0040: Cycle Measurement Toggle Confirmation and Logical Label De-duplication | Accepted | `0040-cycle-measurement-toggle-confirmation-and-label-dedup.md` |
| ADR-0041 | ADR 0041: Use docs/OPEN_ITEMS.md as the canonical backlog and technical-debt tracker | Accepted | `0041-open-items-tracking-process.md` |
| ADR-0042 | ADR 0042: Drift-free scheduler conflict handling and logging | Accepted | `0042-drift-free-scheduler-conflict-logging.md` |
| ADR-0043 | ADR 0043: Security, Offset Correction, Diagnostics Queuing, and Scheduler Hardening | Accepted | `0043-security-offset-diagnostics-scheduler-hardening.md` |
| ADR-0044 | ADR 0044: ShutdownManager for Safe Process Shutdown and Emergency Exit | Accepted | `0044-shutdown-manager-safe-and-emergency-exit.md` |
| ADR-0045 | ADR 0045: Record deep data-integrity, thread-safety, and performance review items as detailed open items | Accepted | `0045-open-items-data-integrity-thread-safety-review.md` |
| ADR-0046 | ADR 0046: SMU read failures and startup hardening | Accepted | `0046-smu-read-failures-and-startup-hardening.md` |
| ADR-0047 | ADR 0047: Hardware reconnect safety, R-line traceability, overload visibility, and trend performance hardening | Accepted | `0047-hardware-safety-rline-trend-performance.md` |
| ADR-0048 | ADR 0048: Data Validity, Unit Schema, Scheduler Policy, Debounced Saves, and Release Cleanup | Accepted | `0048-data-validity-scheduler-policy-release-cleanup.md` |
| ADR-0049 | ADR 0049: Channel Identity, Cross-Restart Trend History, Relay Occupancy, and Active-Scope Telegram PDF Foundation | Accepted | `0049-channel-identity-history-relay-telegram-foundation.md` |
| ADR-0050 | ADR 0050: SystemConfigDialog Shell and Station Recipe Separation | Accepted | `0050-system-config-shell-and-station-recipes.md` |
| ADR-0051 | ADR 0051: Active-scope System Config Dashboard, Unified Environment/Station Recipes, and R-line Diagnostics | Accepted | `0051-active-scope-config-dashboard-and-rline-diagnostics.md` |
| ADR-0052 | ADR 0052: P0 Machine-Test Safety Gates for Relay All-Off and R-line Traceability | Accepted | `0052-p0-machine-test-safety-gates.md` |
| ADR-0053 | ADR 0053: Runtime Dependency Bootstrap Before Qt Startup | Accepted | `0053-runtime-dependency-bootstrap.md` |
| ADR-0054 | Chamber telemetry readiness and diagnostics | Accepted | `0054-chamber-telemetry-readiness-and-diagnostics.md` |
| ADR-0055 | Chamber XOR8 FCS and Signal 01 HEX Parser | Accepted | `0055-chamber-xor8-fcs-and-hex-parser.md` |
| ADR-0056 | Chamber Manual Setpoint Inputs Must Not Be Overwritten by Telemetry Polling | Accepted | `0056-chamber-manual-setpoint-input-stability.md` |
| ADR-0057 | Chamber manual spinbox edits must not compete with synchronous telemetry polling | Accepted | `0057-chamber-spinbox-polling-responsiveness.md` |
| ADR-0058 | Detailed Error Logging Standard for Hardware and Persistence Failures | Accepted | `0058-detailed-error-logging-standard.md` |
| ADR-0059 | Offline Scientific Regression and Hardware Safety Test Policy | Accepted | `0059-offline-regression-hardware-safety-policy.md` |
| ADR-0060 | Repository-Managed Atomic Pre-Push Source Backups | Accepted | `0060-repository-managed-pre-push-backup.md` |
| ADR-0061 | Explicit Channel Outcomes and Live Scheduler Controls | Accepted | `0061-channel-outcomes-and-live-scheduler-controls.md` |
| ADR-0062 | Qualified R-line and Mandatory Solar Polarity | Accepted | `0062-qualified-rline-and-mandatory-solar-polarity.md` |
| ADR-0063 | GSM Query Compatibility and Operator Diagnostics | Accepted | `0063-gsm-query-compatibility-and-operator-diagnostics.md` |

---

## 6. 最近更新的關鍵決策

本專案近期圍繞 `Environment` (環境) 基礎設施、ISOS 架構、`MeasureEngine` 解耦，以及 open item 追蹤有大量決策，詳見：
- **環境設定視窗 (Stage 2.4 - 2.5)**：ADR-0027 ~ ADR-0028 重構了 Channel 設定與 Climate Tab。
- **環境配方 (Recipe) 與 Skeleton**：ADR-0035, ADR-0036, ADR-0037 確立了統一的 Environment Instance 入口。
- **測量配方 (Measurement Recipe)**：ADR-0024 整合量測參數範本。
- **Open Items / 技術債追蹤**：ADR-0041 指定 `docs/OPEN_ITEMS.md` 為唯一正式 backlog。

---

## 7. 維護流程建議

當發生以下情況時，建議建立新的 ADR：
- 新增重大功能，且會改變資料流或模組責任
- 修改核心量測流程或拆分 `measure_engine.py`
- 調整 GUI 與 Core 的 Signal / Slot 關係
- 變更資料格式、輸出格式或命名規則
- 引入新的校正策略、掃描邏輯、錯誤保護機制
- 變更打包與部署方式
