15. 新增可喚回 IV Monitor 與 Trend Chart 視窗的系統管理按鈕，並恢復 MainWindow 的 signal + worker thread 架構
日期: 2026-03-26
狀態: 已接受並實施

背景 (Context)

在主畫面的系統管理區塊中，原本已有「系統全域設定」、「查看日誌」與「關閉程式」等操作按鈕，但缺少一個可在執行期間重新開啟 IV Monitor 與 Trend Chart 視窗的入口。

原本系統中，IV Monitor 與 Trend Chart 雖然可在量測開始時自動顯示，但若使用者在操作過程中手動關閉這兩個視窗，就可能在後續流程中無法方便地再次叫回，造成以下問題：

關閉 IV / Trend 視窗後缺少重新開啟入口
使用者若誤按右上角關閉鈕，主畫面中沒有明確按鈕可再度叫回這兩個視窗。
這會增加操作上的不便，也降低即時監看量測結果的可用性。

需要避免重複開啟多個 IV / Trend 視窗實例
本次需求不是建立新的 IV Monitor 與 Trend Chart 視窗，而是喚回既有視窗。
若按鈕實作為每次點擊都重新建立新視窗，可能導致多個重複視窗並存，造成狀態不一致與資源浪費。

開啟視窗的操作不應影響循環量測流程
本次需求僅是重新顯示監看視窗，不應中斷、重啟、停止或干涉正在進行中的循環量測程序。

MainWindow 的新版修改曾破壞原本的硬體初始化模型
在整合新按鈕時，曾將 MainWindow 的硬體初始化流程改為直接呼叫 engine.initialize_hardware() 並期待其回傳 dict。
但實際上既有系統的設計並非同步讀取回傳值，而是透過 signal 將初始化要求送入 engine 所在的 worker thread，再由 engine 以 signal 回傳硬體狀態。
因此，直接呼叫 initialize_hardware() 造成 NoneType 錯誤，顯示新版實作偏離了原有的架構設計。

既有 IV Monitor 與 Trend Chart 關閉行為其實是 hide 而非真正銷毀
IV Monitor 與 Trend Chart 的 closeEvent 已改為呼叫 hide() 並 ignore close event。
這代表只要 MainWindow 一直持有這兩個視窗的實例，就可以在使用者關閉後再次 show() 回來，而不需要重建。

因此，需要做出以下調整：

在 ControlPanel 的系統管理區塊中新增一個按鈕，供使用者隨時喚回 IV Monitor 與 Trend Chart。
在 MainWindow 中以單例方式持有這兩個視窗實例，避免重複建立。
恢復 MainWindow 舊版的 signal + worker thread 架構，使硬體初始化、量測啟停與設定重載流程回到既有且穩定的執行模型。
確保新按鈕僅影響視窗顯示，不影響量測流程本體。

決策 (Decision)

我們決定在系統管理區塊新增一個專用按鈕，用於同時開啟或喚回 IV Monitor 與 Trend Chart 視窗，並同步將 MainWindow 的硬體初始化與量測控制流程恢復為舊版的 signal + worker thread 架構。

1. 由 control_panel.py 新增「開啟 IV / TREND 視窗」按鈕與對應 signal
在 ControlPanel 中新增：
show_iv_trend_requested = pyqtSignal()

並在「系統全域設定」與「查看日誌」之間加入：
「🪟 開啟 IV / TREND 視窗」

按鈕本身只負責發送 signal，不直接建立或管理視窗。
這樣可保持 ControlPanel 僅作為操作面板，而不承擔視窗生命週期管理責任。

2. 由 main_window.py 持有 IV Monitor 與 Trend Chart 的單一實例
在 MainWindow 初始化時建立：

self.iv_monitor = IVMonitorWindow()
self.trend_chart = TrendChartWindow()

並由 MainWindow 持續保存這兩個實例。
按鈕觸發時不重新 new 視窗，而是對既有實例執行：
show()
raise_()
activateWindow()

這可確保：
不會重複開啟第二組視窗
已被使用者關閉的視窗可再次叫回
視窗內部狀態可被保留

3. 利用既有 closeEvent -> hide() 設計達成可重複喚回
IV Monitor 與 Trend Chart 的關閉行為已改為：
self.hide()
event.ignore()

因此關閉視窗不會真正銷毀物件，只會隱藏。
本次 MainWindow 的新按鈕即建立在此設計基礎上，透過 show / raise / activateWindow 將隱藏視窗重新帶回前景。

4. 恢復 MainWindow 舊版的 signal + worker thread 架構
在 MainWindow 中恢復以下模式：

建立 QThread
將 engine moveToThread(thread)
以 pyqtSignal 作為 UI -> engine 的請求入口
使用 QueuedConnection 將請求送入 engine thread 執行

包括：
request_init_hardware
request_start_scan
request_stop_scan
request_reload_config

其中，on_hardware_init_clicked() 不再直接呼叫：
self.engine.initialize_hardware()

而改回：
self.request_init_hardware.emit()

這樣可避免 UI thread 直接操作 engine，並維持與既有架構相容。

5. 硬體狀態更新維持由 engine signal 回傳
硬體初始化後的狀態更新，仍沿用既有模式：
engine.hardware_status_updated -> control_panel.set_hardware_status

也就是說，本次修改不假設 initialize_hardware() 必須回傳 dict，而是維持原本由 engine 主動 emit 狀態給 UI 的做法。
這可避免再次發生 NoneType.get() 類型錯誤。

6. 新按鈕不介入量測流程
「開啟 IV / TREND 視窗」按鈕僅呼叫視窗顯示相關方法，不會呼叫：
start_scan_cycle()
stop_scan_cycle()
initialize_hardware()
reload_config()

因此本次變更僅處理視窗可見性與使用者操作便利性，不改變循環量測的核心行為。

7. 保留量測開始時自動顯示 IV / Trend 視窗的既有行為
除新增手動喚回按鈕外，也保留量測開始時自動顯示 IV / Trend 視窗的舊版邏輯。
也就是說：
scan_started 時會自動 bring-to-front
平常若使用者手動關閉，也可透過新按鈕再次叫回

這讓系統同時具備自動顯示與手動恢復能力。

影響 (Consequences)

正面影響

使用者可明確重新開啟 IV / Trend 視窗
即使使用者誤關 IV Monitor 或 Trend Chart，也可透過主畫面按鈕立即叫回，不必重啟程式或等待量測重新開始。

不會重複建立多個視窗
由於 MainWindow 只持有單一實例，按鈕只會喚回既有視窗，避免多重視窗造成資料不同步與狀態混亂。

不影響正在進行中的循環量測
按鈕的功能僅限於視窗顯示，不會中斷或改變 engine 的量測執行流程。

恢復既有穩定的執行模型
MainWindow 回到 signal + worker thread 架構後，硬體初始化與量測控制再次符合原本設計，降低 UI thread 與 engine thread 混用帶來的風險。

避免 initialize_hardware() 回傳值假設錯誤
不再依賴 initialize_hardware() 的同步回傳值，可避免 NoneType.get() 造成的啟動錯誤。

程式責任分工更清楚
control_panel.py 負責發出使用者意圖
main_window.py 負責視窗生命週期與流程控制
engine 負責背景執行與狀態回傳

整體架構比直接在 UI 中同步呼叫 engine 方法更清楚、也更接近既有系統設計。

負面影響

MainWindow 結構較為複雜
為了恢復 worker thread 與 queued signal 架構，MainWindow 需要管理額外的 request signal、thread 啟停與跨 thread 連線，程式碼複雜度略有增加。

需要維護視窗實例生命週期
由於 IV Monitor 與 Trend Chart 需由 MainWindow 長期持有，後續修改時必須注意關閉程式時的清理順序與資源釋放。

不同 engine 版本的 signal 命名可能需額外相容處理
若未來 engine 的 signal 名稱或參數 signature 發生調整，MainWindow 中與 IV / Trend 視窗的連線可能需要進一步補強或做版本相容判斷。