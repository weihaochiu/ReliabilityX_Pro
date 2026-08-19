# 13. 新增 IV Monitor 與 Trend Plot 圖片設定視窗與樣式持久化機制

- **日期**: 2026-03-26
- **狀態**: 已接受並實施

## 背景 (Context)

使用者提出希望為 `IVMonitorWindow` 與 `TrendChartWindow` 新增一套可視化的圖片/圖表設定功能，使使用者可以直接透過對話框調整圖表外觀，而不需要修改程式碼。需求重點包括：

1. **IV Monitor 圖表外觀需要可調整**
   - 使用者希望能調整圖表標題、背景顏色、字型大小、座標軸範圍、格線顯示、圖例位置、曲線名稱/顏色/線寬/線型等。
   - 使用者另要求 IV curve 支援：
     - Y 軸顯示模式切換：`Current (mA)`、`Current Density (mA/cm²)`、`Power (mW)`
     - 第四象限鎖定選項，且僅對 `Current` / `Current Density` 生效，`Power` 模式沿用原始量測符號，不強制第四象限。

2. **Trend Plot 圖表外觀也需要可調整**
   - 使用者希望以與 IV Monitor 相同的概念，為趨勢圖建立設定視窗。
   - 設定內容需涵蓋主圖、雙 Y 軸、格線、圖例、設備趨勢曲線、環境曲線（Temp / Hum）、tooltip、匯出選項等。

3. **設定需要可持久化**
   - 使用者要求設定可儲存並於下次啟動時保留。
   - 因此不能只做一次性的暫時套用，而需要將設定寫入 `config` 目錄下的 JSON 檔案。

4. **需要從主視窗直接呼叫**
   - 使用者希望在 `IVMonitorWindow` 與 `TrendChartWindow` 中直接新增「圖表設定...」按鈕，以開啟對應設定視窗並立即套用設定。

## 決策 (Decision)

我們決定為 IV 與 Trend 兩套圖表系統，分別新增一套獨立的圖表設定對話框與 JSON 設定檔機制，並將其整合進主視窗按鈕流程中。

### 1. 為 IV Monitor 新增專用圖表設定視窗

- 新增 `iv_plot_settings_dialog.py`，作為 IV 曲線圖設定對話框。
- 對話框採用分頁式設計，包含：
  - 一般
  - 字型
  - 座標軸
  - 格線
  - 圖例
  - 曲線
  - 匯出
- 使用者可調整：
  - 圖表標題與背景顏色
  - 標題/座標軸/刻度/圖例字型大小
  - 座標軸自動縮放與手動範圍
  - 第四象限鎖定
  - Y 軸模式切換（Current / Current Density / Power）
  - 格線顯示、透明度、線型
  - 圖例顯示與位置
  - 四條 IV 曲線的顯示、名稱、顏色、線寬、線型
  - 匯出格式與解析度

### 2. 為 Trend Plot 新增專用圖表設定視窗

- 新增 `trend_plot_settings_dialog.py`，作為趨勢圖設定對話框。
- 對話框採用分頁式設計，包含：
  - 一般
  - 字型
  - 座標軸
  - 格線
  - 圖例
  - 曲線
  - 匯出
- 使用者可調整：
  - 圖表標題、背景色、tooltip 顯示與顏色
  - 標題/座標軸/刻度/圖例/tooltip 字型大小
  - X / 左 Y / 右 Y 軸標題與範圍
  - 是否顯示右側環境軸
  - 格線顯示、透明度、線型
  - 圖例顯示、位置、是否包含環境曲線、是否使用完整設備名稱
  - 設備趨勢曲線預設樣式
  - Temp / Hum 環境曲線的顯示、名稱、顏色、線寬、線型
  - 匯出格式、解析度、檔名樣式

### 3. 導入 JSON 持久化設定

- 為兩套設定視窗新增 JSON 讀寫邏輯。
- IV 設定檔位置：
  - `config/iv_plot_settings.json`
- Trend 設定檔位置：
  - `config/trend_plot_settings.json`
- 若設定檔不存在：
  - 自動建立預設檔案
- 對話框操作邏輯：
  - **套用**：立即發送設定至圖表，不關閉視窗
  - **儲存**：將目前設定寫入 JSON，不關閉視窗
  - **確定**：先套用，再儲存，最後關閉視窗
  - **取消**：關閉視窗，不套用也不儲存
  - **還原預設**：回復程式內建預設值

### 4. 修改 IV 與 Trend Plot Widget，使其支援動態套用設定

- 修改 `iv_plot_widget.py`：
  - 支援讀取 `iv_plot_settings.json`
  - 將原本固定寫死的樣式改為可由 `apply_plot_settings(settings)` 動態套用
  - 支援重新整理標題、背景、字型、格線、圖例、曲線樣式、Y 軸模式
  - 將資料儲存為原始值，以支援切換 `Current / Current Density / Power` 時重算圖形
  - 第四象限邏輯僅在 `Current` / `Current Density` 模式下生效

- 修改 `trend_plot_widget.py`：
  - 支援讀取 `trend_plot_settings.json`
  - 支援主圖與右側環境雙 Y 軸樣式動態更新
  - 支援 tooltip 樣式、圖例樣式、環境曲線樣式、設備曲線預設樣式與範圍設定
  - 保留原本的資料邏輯（如 normalize、T80、環境資料顯示），僅擴充圖表外觀控制

### 5. 在主視窗加入「圖表設定...」入口

- 修改 `iv_monitor_window.py`
  - 新增 `圖表設定...` 按鈕
  - 按下後呼叫 `IVPlotSettingsDialog`
  - 將 `settings_applied` 連接至 `IVPlotWidget.apply_plot_settings`

- 修改 `trend_chart_window.py`
  - 新增 `圖表設定...` 按鈕
  - 按下後呼叫 `TrendPlotSettingsDialog`
  - 將 `settings_applied` 連接至 `TrendPlotWidget.apply_plot_settings`

### 6. 調整數值輸入方式以提升穩定性

- 在 IV 設定視窗中，針對易受主題樣式影響的數值欄位進行調整：
  - 離散型參數（如字型大小、線寬、透明度、DPI）改用 `QComboBox`
  - 連續範圍型參數（如 X/Y 最小值、最大值）保留 `QDoubleSpinBox`，但隱藏上下按鈕
- 這樣可保留滑鼠滾輪與鍵盤輸入功能，同時避免因樣式表造成上下箭頭按鈕失效。

## 影響 (Consequences)

### 正面影響

- **可用性提升**  
  使用者現在可以透過圖形介面直接調整 IV 與 Trend 圖表外觀，無需再修改程式碼。

- **專業性提升**  
  圖表標題、格線、圖例、曲線樣式、Y 軸模式等都可根據用途調整，更適合報告、論文、簡報與內部分析。

- **持久化設定提升便利性**  
  使用者不需要每次重新開啟程式後重新設定圖表外觀，設定可長期保留。

- **IV 曲線分析彈性提升**  
  IV Monitor 可直接切換 `Current`、`Current Density`、`Power` 顯示模式，並支援第四象限鎖定，更符合太陽能元件分析需求。

- **Trend Monitor 外觀一致性提升**  
  趨勢圖主圖與環境雙 Y 軸的樣式可以統一管理，並支援 tooltip、圖例與環境曲線的客製化。

- **主視窗操作流程更完整**  
  使用者可直接從 `IVMonitorWindow` 與 `TrendChartWindow` 點選「圖表設定...」進入設定，不需額外入口。

### 負面影響

- **程式結構複雜度略微增加**  
  為了支援外觀設定與 JSON 持久化，新增了兩套對話框、兩份設定檔以及圖表 widget 的套用邏輯。

- **部分 pyqtgraph 格線樣式仍有限制**  
  目前穩定支援的是格線顯示與透明度；格線顏色與線型雖已納入設定模型，但若要完全反映到畫面，可能仍需要進一步客製 pyqtgraph 的格線繪製方式。

- **匯出設定尚未完全整合至所有匯圖流程**  
  雖然設定視窗已包含匯出格式與 DPI，但主視窗的儲存圖表流程仍可在後續再進一步整合，讓匯出完全遵循 JSON 設定。