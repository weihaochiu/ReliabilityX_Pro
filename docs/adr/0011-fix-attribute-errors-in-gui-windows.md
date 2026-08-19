# 11. 修正 GUI 視窗中的屬性錯誤 (AttributeError)

- **日期**: 2026-03-16
- **狀態**: 已接受並實施

## 背景 (Context)

在先前實作了「儲存圖表」和「修復 Tooltip」等功能後，實際運行時發現了兩類不同的 `AttributeError`，導致功能失效或崩潰。

1.  **`IVMonitorWindow` 的存檔錯誤**:
    -   **問題**: 點擊「儲存圖表 (JPG)」按鈕時，日誌顯示 `AttributeError: 'IVMetaWidget' object has no attribute 'get_info'`。
    -   **根本原因**: 程式碼試圖呼叫一個不存在的 `get_info` 方法來獲取中繼資料，而非從 `IVMetaWidget` 的 UI 元件（`QLabel`）中讀取。

2.  **`TrendChartWindow` 的 Tooltip 顯示錯誤**:
    -   **問題**: 在趨勢圖上移動滑鼠時，程式拋出 `AttributeError: 'TrendPlotWidget' object has no attribute 'get_plot_item'`。
    -   **根本原因**: 負責顯示 Tooltip 的 `_on_mouse_moved` 方法試圖自行建立和管理一個 `pg.TextItem`，並呼叫一個不存在的 `get_plot_item` 方法將其添加到圖表中。事實上，`TrendPlotWidget` 內部已經封裝了完整的 Tooltip 管理邏輯。

3.  **潛在的存檔錯誤**:
    -   **問題**: 在審查 `TrendChartWindow` 的 `_on_save_plot_clicked` 方法時，發現了與 Tooltip 錯誤類似的 latent bug。它也試圖呼叫不存在的 `get_plot_item()`。
    -   **根本原因**: 對 `pyqtgraph` 物件結構的錯誤假設，應直接存取其 `PlotItem` 物件。

## 決策 (Decision)

我們決定一次性修復這些屬性錯誤，並藉此機會重構部分程式碼，使其與子元件的互動更清晰、更健壯。

1.  **修復 `TrendChartWindow` (Tooltip 和存檔)**:
    -   在 `_on_mouse_moved` 方法中，**完全移除**手動建立和管理 `self.tooltip` 的邏輯。
    -   改為直接呼叫 `self.plot_widget` 內部已經存在的 `update_tooltip()` 和 `hide_tooltip()` 方法。這將控制權交還給了 `TrendPlotWidget`，使其職責單一。
    -   在 `_on_save_plot_clicked` 方法中，將 `ImageExporter(self.plot_widget.get_plot_item())` 的錯誤呼叫修正為 `ImageExporter(self.plot_widget.p1)`，直接存取 `TrendPlotWidget` 內部正確的 `PlotItem` 物件。

2.  **修復 `IVMonitorWindow` (存檔)**:
    -   為了讓 `IVMonitorWindow` 能乾淨地獲取繪圖物件，首先在 `IVPlotWidget` 中新增一個 `get_plot_item(self)` 的輔助方法，該方法回傳其內部的 `PlotItem`。
    -   接著，在 `_on_save_plot_clicked` 方法中：
        a. 將 `self.meta_widget.get_info(...)` 的錯誤呼叫，改為從 `self.meta_widget.meta_labels["Channel"].text()` 和 `self.meta_widget.meta_labels["Device"].text()` 讀取 UI 文字。
        b. 增加一個 `try-except` 區塊，以安全地將從 UI 讀取的頻道 ID 字串轉換為整數。
        c. 使用新建立的 `self.plot_widget.get_plot_item()` 方法來獲取 `PlotItem` 並傳遞給 `ImageExporter`。

## 影響 (Consequences)

### 正面影響
- **錯誤修正**: 徹底解決了上述三類 `AttributeError`，讓 Tooltip 功能和兩個視窗的存檔功能都能正常運作。
- **程式碼品質提升**:
    -   `TrendChartWindow` 的程式碼被簡化，移除了冗餘的 Tooltip 管理邏輯，使其與子元件的互動更加清晰。
    -   `IVPlotWidget` 的封裝性得到增強，透過 `get_plot_item` 方法提供了一個更穩定、更明確的公共介面。
- **健壯性**: 為 `IVMonitorWindow` 中的字串到整數轉換增加了錯誤處理，使程式在面對非預期 UI 狀態時不會崩潰。

### 負面影響
- 無。本次修改均為錯誤修正與良性重構，未引入任何新風險。
