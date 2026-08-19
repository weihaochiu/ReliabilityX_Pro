# ADR 0028: Stage 2.5 Widget Dialog and Environment Tab Restructure

## Status
Accepted

## Context
使用者指出：
1. `channel_setting_dialog` 應以 2026-03-25 舊版為主體，再加入多場域邏輯。
2. `climate_chamber_tab.py` 應重新排版，不應直接硬嵌 `chamber_tab.py` 導致下方 layout 炸裂。
3. `climate_chamber_tab`、`indoor_environment_tab`、`vacuum_glovebox_tab` 應放在 `gui/config_tabs/environment/tabs/`。

## Decision
1. `channel_setting_dialog.py` 回到 widget-based 主體。
2. Measurement Recipe 與 Environment Recipe 明確分離。
3. concrete environment tabs 移到 `environment/tabs/`。
4. Climate Chamber 先用 scroll host 承接既有 `chamber_tab.py`，作為過渡方案。

## Consequences
- 優點：
  - 與舊版使用習慣更接近
  - 多場域邏輯能加在既有成熟流程上
  - tabs 結構更清楚
- 缺點：
  - Climate legacy UI 尚未完全拆成可重用子元件
  - 仍保留過渡性 host widget
