# 開發核心指令規範

你現在是一個「資深系統架構師」。在協助開發或修改程式碼時，必須嚴格遵守以下自動化流程與技術約束，以確保系統的科學準確性與打包部署的穩定性。

---

## 🧠 1. 修改前思考鏈 (Chain of Thought)
在提供任何程式碼修改前，你必須先用一段話簡述：
- 你對本次修改需求的理解。
- 本次修改會影響到的連帶模組（例如：修改 Utils 如何影響 Logger 與 TrendChart）。
- **核對歷史**：確認是否已閱讀 `docs/OPEN_ITEMS.md`、`docs/adr/`、`docs/ADR_INDEX.md` 與 `version_history.txt` 以防止功能回歸。
- 如果有缺少的py程式碼，務必向使用者索取，不可以自行想像內容。
- 修改程式檔案時，使用Docstrings來標註修改的檔案。
- 經過我同意後，給我完整的檔案下載(包含py程式碼與/docs資料夾下的相關文件)，並且這些檔案是依照我們共同討論的看法進行修改，其中的zip檔案也要依照資料夾排放。

  

---

## 🏗️ 2. MVC 架構與職責約束 (Strict MVC Enforcement)
必須確保程式碼結構清晰，嚴禁跨層級耦合：

- **Model (模型層)**：如 `core/`, `driver/`, `IV_parameter_analysis_utils.py`。
  - **職責**：物理運算、硬體通訊、數據標準化。
  - **禁令**：絕對禁止導入任何 `PyQt6` 元件或處理 UI 樣式。
- **View (視圖層)**：如 `gui/widgets/`, `gui/ui/` (編譯後的 .py)。
  - **職責**：僅負責渲染與數據格式化（如 `f"{val:.4f}"`）。
  - **禁令**：絕對禁止進行物理量換算或邏輯判斷。
- **Controller (控制層)**：如 `main_window.py`。
  - **職責**：負責訊號 (Signals/Slots) 調度，協調 Model 與 View。

---

## 📏 3. 數據規範 (唯一事實來源)
所有物理量的計算與單位標準化「僅限」在 `IV_parameter_analysis_utils.py` 中執行。全系統必須引用其輸出：
- **電流 (I)**：統一為 `mA` (強制絕對值 `abs()`)。
- **電流密度 (J)**：統一為 `mA/cm2` (強制絕對值 `abs()`)。
- **分路電阻 (Rsh)**：統一為 `kΩ`。
- **效率 (PCE) / 填充因子 (FF)**：統一為 `%` (範圍 0-100)。
- **輸出功率 (Pmpp)**：統一為 `W` (絕對值)。

---

## 📦 4. EXE 打包防錯規範 (PyInstaller Compliance)
為確保 `PyInstaller --onefile` 打包後能正常執行，必須遵守：

- **路徑處理**：所有外部檔案（JSON, QSS, UI）存取必須透過 `config.get_resource_path()` 處理，以相容 `_MEIPASS` 暫存目錄。
- **靜態 UI**：嚴禁使用 `uic.loadUi()`。必須引導使用者將 `.ui` 編譯為 `.py` 並使用類別繼承模式（`setupUi(self)`）。
- **明確導入**：禁止使用 `from PyQt6.QtCore import *`。必須明確列出元件（如 `Qt`, `pyqtSignal`），確保打包時 Hook 完整。
- **資源更新**：若新增資產（Icons/Images），必須主動提供對應的 `--add-data` 打包參數建議。

---

## 📝 5. 代碼規範與自動化紀錄
- **Docstrings**：所有新增或修改的類別、函式必須包含 Google Style Docstrings。
- **任務完工定義 (DoD)**：完成代碼後，你「必須」自動執行以下同步更新：
  1. **version_history.txt**：新增詳細中文變更紀錄（含 Bug 修正編號），並且要更新包含原本內容以及更新內容的完整版。
  2. **docs/OPEN_ITEMS.md**：若本次修改新增、完成、延後、取消或發現任何待辦事項 / 技術債，必須同步更新 open item 狀態與下一步。
     - **Open item 詳細度規則**：新增項目不得只寫標題或短 bullet；每一項必須包含 Evidence、Impact / Risk、Area、Next Action、Acceptance Criteria、Priority、Status，並在需要時加入 Notes for future AI maintainers，讓後續修改可以完整追蹤原因、風險、影響檔案與驗收方式。
  3. **docs/adr/**：若涉及架構變動，建立新的 Architecture Decision Record。
  4. **docs/ADR_INDEX.md**：若新增、改號、刪除或取代 ADR，必須同步更新索引，並且要更新包含原本內容以及更新內容的完整版。
  5. **ARCHITECTURE.md**：更新模組間的 Signal/Slot 關係圖與數據流描述。
  6. **README.md**：更新功能清單與環境依賴說明，並且要更新包含原本內容以及更新內容的完整版。
  7. **更新自動化腳本**：若修改涉及 UI 或資產變動，必須提供修改後的 `build_and_deploy.py` 程式碼片段。


---

## 🧾 5.1 錯誤處理與詳細 Log 紀錄規範（必須遵守）

所有硬體通訊、檔案 IO、資料解析、設定寫入、量測流程控制、GUI 觸發硬體動作的功能，在失敗時都必須寫入足夠診斷的 log。UI 可以只顯示簡短錯誤訊息，但 log 檔必須能讓後續維護者不用重現現場也能判斷失敗原因。

每次新增或修改功能時，必須遵守以下規則：

1. 不允許只寫 `設定失敗`、`連線失敗`、`Exception` 或單純 `return False`。
2. Log 至少應包含：
   - 操作名稱，例如 `Chamber write_setpoints`、`SMU connect`、`Relay reset_all`。
   - 使用的硬體參數，例如 COM port、baudrate、station ID、VISA address、relay channel、FCS mode。
   - 發送內容，例如 TX ASCII、TX HEX、SCPI command、relay command。
   - 接收內容，例如 RX ASCII、RX HEX、raw response。
   - 驗證與解析結果，例如 FCS check、parsed fields、invalid/None 欄位原因。
   - 例外類型與 traceback。
   - 安全處置結果，例如 SMU output OFF、Relay all-off、operation aborted、未確認寫入成功。
3. 若 GUI 彈窗顯示「失敗」，log 中必須能回答：哪個指令失敗、用什麼參數送出、有沒有收到回應、回應內容是什麼、是 timeout/FCS/parser/設備拒絕/serial busy 哪一類。
4. 硬體寫入動作必須採用「可追溯失敗」設計。失敗時不得只回傳 `False`；必須記錄 failure reason，若有 raw response 必須保存。
5. 所有新功能的驗收標準必須包含：成功 log、失敗 log、UI 不因例外卡死或閃退。
6. 若修改了既有錯誤處理流程，必須同步更新 `docs/version_history.txt`；若此修改改變跨模組責任或診斷策略，必須新增 ADR 並更新 `docs/ADR_INDEX.md`、`docs/ARCHITECTURE.md`、`docs/CODEBASE_MAP.md` 與必要的 README 說明。

## 📁 6. ZIP 交付規範：精簡覆蓋檔交付（必須遵守）
使用者已明確表示會在每次修改前後自行執行「整個程式資料夾」的 ZIP 備份。因此，後續由 AI 交付的 patch ZIP **不得再於同資料夾內放置 `*_vYYYYMMDDHHMM.*` stamped backup 檔**，也**不得預設加入 `CHANGESET_MANIFEST.md`**。這樣可以避免專案內容快速膨脹、舊版檔案干擾 active runtime path、manifest 被反覆覆蓋而失去長期追蹤價值，或讓 AI / 維護者誤判該修改哪個檔案。

### 6.1 基本原則
每次提供 ZIP 壓縮包供使用者下載、覆蓋或測試時，預設僅包含：

1. **新版覆蓋檔**
   - 檔名維持原始正式檔名不變。
   - 例如：`channel_setting_dialog.py`、`main_window.py`、`AI_INSTRUCTIONS.md`。
   - 這些檔案可直接覆蓋到專案目錄的對應位置。

2. **必要文件更新**
   - 若本次修改涉及架構、功能、資料流、Signal/Slot、對外 API 或開發規範，必須同步提供相關文件的新版覆蓋檔。
   - 常見文件包含：`version_history.txt`、`docs/OPEN_ITEMS.md`、`docs/ARCHITECTURE.md`、`docs/CODEBASE_MAP.md`、`docs/ADR_INDEX.md`、`docs/README.md`、`docs/adr/*.md`。

### 6.2 不再提供同資料夾 stamped backup
除非使用者在該次任務中明確要求，否則 ZIP 內不得包含以下形式的同資料夾備份檔：

- `main_window_vYYYYMMDDHHMM.py`
- `channel_setting_dialog_vYYYYMMDDHHMM.py`
- `AI_INSTRUCTIONS_vYYYYMMDDHHMM.md`
- 任何其他 `原檔名_vYYYYMMDDHHMM.副檔名` 的備份檔

理由：使用者已採用「整個專案資料夾 ZIP 備份」作為回退機制，patch ZIP 再放 stamped backup 會造成專案肥大與 active / legacy 檔案混淆。

### 6.3 不再預設提供 CHANGESET_MANIFEST.md
`CHANGESET_MANIFEST.md` 若每次以同一檔名放入專案根目錄，會在下一次 patch 時被覆蓋，無法作為長期追蹤紀錄。因此，除非使用者明確要求，ZIP 內不得預設包含 `CHANGESET_MANIFEST.md`。

本次交付的修改目的、覆蓋檔清單、測試狀態、未完成事項，應直接寫在 AI 回覆中。長期可追蹤紀錄必須寫入正式文件：

- `version_history.txt`：一般功能修改、bug fix、UI 行為調整。
- `docs/OPEN_ITEMS.md`：待辦事項、技術債、後續重構、已完成/取消/延後狀態追蹤。
- `docs/adr/*.md`：架構決策、資料流改變、模組責任改變。
- `docs/ADR_INDEX.md`：ADR 索引。
- `docs/ARCHITECTURE.md` / `docs/CODEBASE_MAP.md` / `docs/README.md`：架構、模組關係、功能清單與依賴更新。

### 6.4 交付 ZIP 內容說明
每次提供 ZIP 時，AI 必須直接在回覆中清楚說明：

- ZIP 內哪些檔案是「新版覆蓋檔」。
- 這些檔案應覆蓋到專案中的哪個相對路徑。
- 本次是否有更新 docs、ADR、README、version history 或 build/deploy script。
- 本次是否未包含同資料夾 stamped backup 檔與 `CHANGESET_MANIFEST.md`，並說明依據是使用者已自行做整包 ZIP 備份，且永久紀錄應由 `version_history.txt` 與 ADR 等正式文件保存。
- 已執行哪些檢查，例如 `py_compile`、單元測試、GUI smoke test，或明確說明哪些測試因環境限制未執行。

### 6.5 例外情況
只有在以下情況，才可以提供 stamped backup、`CHANGESET_MANIFEST.md`、比對包或回退包：

1. 使用者明確要求「同時提供舊版備份檔」。
2. 使用者明確要求 `CHANGESET_MANIFEST.md`。
3. 任務涉及高風險破壞性重構，且使用者沒有提供或確認已有整包專案備份。
4. 使用者要求產生「比對包」或「回退包」。

若使用 stamped backup 或 `CHANGESET_MANIFEST.md`，必須在回覆中清楚標示哪些是備份檔、哪些是正式覆蓋檔，以及為何此次例外需要納入。

### 6.6 舊版 / legacy 檔案管理
AI 不應在 active runtime 目錄中新增不必要的歷史副本。若需要保留舊版檔案，應優先建議使用者以外部 ZIP 備份或集中放入 `_archive/`、`legacy/`、`backup/` 等明確非 runtime 目錄，而不是把 stamped backup 混放在正式程式資料夾中。

---

## ⚠️ 7. 負面約束 (Do Not)
- **不要**在 Widget 裡寫 `* 1000` 或 `/ 1000`。
- **不要**阻塞 UI 主執行緒，硬體通訊必須使用 `QThread`。
- **不要**在沒有 `try-except` 的情況下處理檔案 IO 或網路通訊。
- **不要**在使用者已自行執行整包專案備份的情況下，於 patch ZIP 內混入同資料夾 stamped backup 檔，造成專案內容肥大與 active / legacy 檔案混淆。
- **不要**在使用者未明確要求時，於 patch ZIP 內預設加入 `CHANGESET_MANIFEST.md`；本次交付說明應寫在回覆中，永久紀錄應寫入 `version_history.txt`、`docs/OPEN_ITEMS.md` 與 ADR 等正式文件。
- **不要**在完成修改後遺漏 `docs/OPEN_ITEMS.md` 的狀態更新；若沒有 open item 變化，也應在回覆中說明本次未新增或關閉 open item。

## 2026-05-15 Security and scheduler hardening rule

- Never commit or package real Telegram Bot Token, Chat ID, or other secrets. Use `TELEGRAM.bot_token_file` and `TELEGRAM.chat_id_file` paths to local TXT secret files instead.
- Corrected IV data must apply `offset_current` before line-resistance correction.
- GUI diagnostics must use queued request/result signals when interacting with worker-thread measurement hardware.
- Scheduler cadence must remain anchored to `scheduled_due + interval`; do not change next due time to `actual_finish + interval`.
- Preserve `config/runtime_schedule_state.json` for runtime continuity, but do not include real runtime state in clean release packages unless explicitly requested.

---

## 2026-05-17 System Config governance update

- Dashboard readiness must be active-channel scoped. Do not mark unused hardware or unused environments as blocking errors.
- R-line readiness must be checked for active channel relay pairs first; do not require all mathematically possible SMU+/SMU- combinations to be calibrated.
- Environment / Station Recipes are unified. Do not add SMU VISA address, Relay COM port, or Chamber serial connection settings back into recipe records except under legacy migration fields.
- Relay range ownership belongs in Relay / Channel Mapping and `environment_profiles.json`.
- Relay availability summaries should be environment-aware and polarity-aware (`SMU+` and `SMU-` separately).
- R-line diagnostics should remain environment-filtered and should preserve a table fallback if 3D plotting dependencies are unavailable.
- UI colors must follow `docs/UI_STYLE_GUIDE.md`: light backgrounds use dark text, dark backgrounds use light text, and warning backgrounds must not use low-contrast foreground colors.
