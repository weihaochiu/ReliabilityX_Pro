# ADR-0024: Add Measurement Recipe Library

- **日期**: 2026-04-02
- **狀態**: Accepted
- **決策者**: ReliabilityX Pro 開發團隊

## 背景

目前單一 channel 的量測參數需要在 `ChannelSettingDialog` 中逐筆手動輸入，容易因 sample 類型不同而造成：

- 電壓範圍設定錯誤
- 電流限制設定錯誤
- 面積設定錯誤
- 延遲與量測間隔設定不一致

使用者要求在 `SystemConfigDialog` 中建立可集中維護的 measurement recipe library，並在 `ChannelSettingDialog` 直接以下拉選單套用。

## 決策

新增一層**純 UI / 設定輔助用途**的 Measurement Recipe Library。

### 新增元件

- `config/measurement_recipes.json`
- `gui/config_tabs/recipe_tab.py`
- `config.load_measurement_recipes()` / `config.save_measurement_recipes()`
- `ChannelSettingDialog` recipe 下拉選單與套用按鈕

### Recipe 僅允許保存的欄位

- `name`
- `v_start`
- `v_stop`
- `v_step`
- `delay_time_ms`
- `measurement_interval_min`
- `current_limit_a`
- `area_cm2`

### 明確不放入 recipe 的內容

- `relay_pos` / `relay_neg`
- battery type / WBG / NBG
- recipe version
- runtime metadata

## 為什麼這樣設計

1. `relay_pos / relay_neg` 是單一通道的硬體接線資訊，不應被模板覆蓋。
2. runtime 量測時若回查 recipe，會讓既有 channel 因 recipe 內容後續變更而被動改變，破壞 `channel_settings.json` 作為唯一事實來源的角色。
3. recipe 的目的只是降低重複輸入風險，不是引入新的 runtime 組態層。

## 影響

### 正面

- 減少人工輸入錯誤。
- 讓常用 sample 條件可以集中維護。
- 不破壞既有量測流程與 `MeasureEngine` runtime 讀取邏輯。

### 負面 / 代價

- 增加一個新的 JSON 設定檔與 UI tab。
- `ChannelSettingDialog` 需要多一個 recipe 套用流程。
- 使用者需要理解：**套用 recipe 不等於自動綁定 recipe**，最終仍是把值寫入當前 channel。

## 決策結果

接受此設計，並維持以下不變式：

- runtime 量測只讀 `channel_settings.json`
- recipe 不保存 relay pin
- recipe 只負責快速填值
