# ADR-0024: Environment Stage-2 Channel Dialog Integration

## Status
Accepted

## Context
Stage-1 已建立 environment profiles、recipes 與 EnvironmentManager，但尚未導入 Channel Setting Dialog，且 EnvironmentTab 初始化存在建構子參數錯配錯誤。

## Decision
1. 將 Environment 相關 tab 全部移入 `gui/config_tabs/environment/` 子資料夾。
2. `SystemConfigDialog` 改以 `EnvironmentTab(parent=self)` 建立頁面，避免位置參數誤用。
3. `ChannelSettingDialog` 導入：
   - Environment Instance
   - ISOS / Custom Test ID
   - Measurement Recipe
   - Environment Control Recipe
   - legal relay range 限制
   - runtime lock read-only 判斷

## Consequences
- Environment 設定與 Channel 設定建立起初步整合。
- 後續可在 Stage-3 進一步接入 main_window environment summary 與 measurement scheduler。
