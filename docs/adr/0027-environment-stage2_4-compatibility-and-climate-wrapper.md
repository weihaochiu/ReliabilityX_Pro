# ADR 0027: Environment Stage 2.4 Compatibility and Climate Wrapper

## Status
Accepted

## Context
先前 Environment 架構 patch 造成兩個直接回歸：
1. `EnvironmentTab` 不再相容於 `SystemConfigDialog.load_data_to_tabs()`
2. `ChannelSettingDialog` 不再相容於 `MainWindow.on_channel_detail_clicked()`

同時，Climate Chamber 的新子頁尚未真正承接舊 `chamber_tab.py` 的可用能力。

## Decision
1. 保留 `SystemConfigDialog` 與 `MainWindow` 既有介面契約。
2. 新增 `EnvironmentManager` 作為 core 層配置協調者。
3. `ClimateChamberTab` 以 wrapper 方式嵌入既有 `chamber_tab.py`。
4. `ChannelSettingDialog` 採用方案 A：先選 Environment，再限制 Relay 範圍。
5. Measurement Recipe 與 Environment / ISOS Recipe 分離。

## Consequences
- 優點：
  - 降低回歸風險
  - 保留既有 Climate 控制內容
  - 讓多場域功能可逐步整合
- 缺點：
  - `SystemConfigDialog` 仍保留 legacy `ChamberTab`
  - Climate 功能暫時存在「舊 tab + 新 wrapper」的過渡期重複
