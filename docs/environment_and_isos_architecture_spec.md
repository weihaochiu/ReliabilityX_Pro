# ReliabilityX Pro
## Environment & ISOS-Based Measurement Architecture Specification

## Stage 3.0.1 Bugfix Update

### Core Rule
- Channel setting **維持方案 A**
- `channel_setting_dialog` 由使用者先選 `Environment`，再限制可選 relay

### Environment Recipe Editor Entry Policy
- 正式主入口：`SystemConfigDialog` 的 `Environment Recipe` 分頁
- `SystemConfigDialog` 必須明確匯入
  `gui/config_tabs/environment_tab/environment_tab_main.py` 內的 `EnvironmentTab`
- 不再依賴已刪除或模糊的 `gui/config_tabs/environment_tab.py`

### Environment Parent Tab Policy
- `environment_tab_main.py` 是唯一 authoritative parent tab
- Parent tab 對上提供 `open_environment_recipe_requested(str)`
- Climate / Vacuum Glovebox / Indoor 子 tab 仍可提供 shortcut signal
  並由 parent tab 向上轉發

### Environment Instance Persistence
- `config/environment_profiles.json` 為 Environment Instance 的單一來源
- Relay assignment 與 `default_env_recipe` 的儲存必須走
  `core/environment_manager.py`
- 子 tab 不得自行直接寫 JSON；必須透過
  `EnvironmentManager.update_instance(instance_id, payload)`

### Current Scope
- Environment Recipe editor：JSON 載入 / 顯示 / 儲存
- Environment tab：instance / relay assignment / default recipe 的儲存
- 目前不做 glovebox / indoor 實際硬體控制
