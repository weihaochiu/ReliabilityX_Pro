# ADR 0029: Channel Setting Dialog Widget Extension Fix

## Status
Accepted

## Context
`ChannelSettingDialog` 已切回舊版 widget-based 結構，但現行
`ChannelParamWidget` 與 `ChannelActionWidget` 尚未提供新 dialog 所需的
介面，導致 runtime error。

## Decision
1. 保留舊 widget 檔案作為基底，不重建替代版。
2. 直接在原 widget 上擴充必要 API：
   - `ChannelParamWidget.set_measurement_recipes()`
   - `ChannelActionWidget.set_environment_options()`
   - `ChannelActionWidget.set_environment_meta()`
3. `ChannelSettingDialog` 維持與 `main_window.py` 相容。

## Consequences
- 優點：
  - 最小修改
  - 不破壞既有 widget 的主要行為
  - 使用者熟悉的 UI 結構可以保留
- 缺點：
  - widget 介面變得比舊版稍大
