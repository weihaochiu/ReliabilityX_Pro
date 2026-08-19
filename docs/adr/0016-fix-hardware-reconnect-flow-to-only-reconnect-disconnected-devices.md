16. 修正硬體重新偵測流程，僅重連未連線設備
日期: 2026-03-26
狀態: 已接受並實施
背景 (Context)

在目前主視窗與量測引擎的架構中，「重新偵測硬體連線」按鈕會透過 main_window.py 的 queued signal，呼叫 MeasureEngine.initialize_hardware()，再由 hardware_status_updated signal 將結果更新到 ControlPanel 的硬體狀態區塊。ControlPanel 本身已具備顯示 SMU、Relay、Chamber 三項硬體連線狀態的 UI 與更新方法，因此此次問題的核心不在 UI 顯示，而在量測引擎的重偵測策略。

在舊版 measure_engine.py 中，initialize_hardware() 每次被呼叫時，都會無條件執行：

self.smu.connect()
self.relay.auto_scan()
若 Relay 掃描成功，再執行 self.relay.reset_all()

也就是說，即使 SMU 與 Relay 已經處於已連線狀態，只要再次按下「重新偵測硬體連線」，程式仍會嘗試重新開啟或重新掃描這些裝置。

進一步檢查底層 driver 後發現：

SMUDriver.connect() 並未先判斷是否已連線，也未先釋放既有 VISA session
它會直接 open_resource(...)，並在成功後設定 self.is_connected = True。這表示若外層重複呼叫 connect()，是否安全將取決於 VISA 資源本身與設備狀態，不能假設一定可以重入。
RelayDriver.auto_scan() 也不是無條件安全的重複初始化流程
它只有在 temp_config 存在且 self.is_connected 為真時才會先 close()；在一般情況下，會直接重新掃描所有 COM port，找到符合條件的裝置後建立新的 serial.Serial(...) 連線，並將 self.ser 指向新的串口實例。這種行為同樣不適合在已連線狀態下反覆執行。

因此，舊版設計存在以下風險：

已連線設備被重複初始化
VISA / COM port 資源可能被重複占用
使用者按下「重新偵測硬體連線」時，可能造成不必要的連線錯誤
重偵測行為不符合直覺，因為理想行為應是「只補救未連線的設備」
決策 (Decision)

我們決定調整 MeasureEngine.initialize_hardware() 的設計，將原本「每次重偵測都全部重連」的模式，改為「只檢查並重連未連線設備」。此修改以 measure_engine.py 為核心，保留 main_window.py 與 control_panel.py 既有的 signal / slot 架構與 UI 介面不變。

本次決策內容如下：

加入硬體狀態探測邏輯
為 SMU、Relay、Chamber 各自建立狀態探測方法。
SMU 連線狀態除了檢查 is_connected 外，還額外以 get_idn() 作為輕量健康檢查，避免僅憑布林旗標誤判。
Relay 連線狀態除了檢查 is_connected 外，還會確認 ser 物件存在且 ser.is_open 為真。
Chamber 則維持相容性設計，若沒有 driver 則回報未連線；若有 driver，優先讀取其 is_connected 屬性。
僅對未連線設備執行重連
若 SMU 已連線，則略過 connect()。
若 Relay 已連線，則略過 auto_scan()。
若 Chamber 已連線，則略過 connect()。
只有當探測結果判定該設備未連線時，才會進行對應的重連流程。
保留重連成功後的必要初始化
Relay 只有在這次確實完成重連後，才執行 reset_all()，確保板卡進入安全初始狀態。
已連線且健康檢查通過的設備，不再執行重複初始化。
量測進行中禁止硬體重偵測
若 is_running 為真，代表系統正在掃描或量測中，則忽略此次重偵測要求。
此時僅回報目前狀態，不對硬體進行重連或重設，以避免量測中途干擾。
統一由 hardware_status_updated 回報最新狀態
不論是略過、重連成功、重連失敗或量測中拒絕執行，都會在流程尾端回報最新的 SMU / Relay / Chamber 狀態。
ControlPanel 仍透過既有的 set_hardware_status(...) 更新顯示，不需改動 UI 介面。
影響 (Consequences)
正面影響
避免重複占用硬體資源
舊版每次重偵測都會無條件重新執行 SMU.connect() 與 Relay.auto_scan()，新設計改為僅對未連線設備補救，可明顯降低 VISA session 或串口資源被重複開啟的風險。
重新偵測行為更符合使用者直覺
使用者按下「重新偵測硬體連線」時，系統現在會優先檢查目前狀態，只補救真正掉線的設備，而不是對所有設備重新初始化。
提升系統穩定性
在量測進行中忽略重偵測要求，可避免量測途中重設 Relay 或重連 SMU，降低流程中斷風險。
保留既有 UI 與主視窗架構
main_window.py 仍使用 queued signal 將重偵測請求送入 engine thread；ControlPanel 仍透過 set_hardware_status(...) 顯示狀態，因此修改集中在 measure_engine.py，不需大幅調整主視窗與控制面板。
硬體狀態判斷更可靠
不再只依賴單純的 is_connected 布林值，而是加入 SMU.get_idn() 與 Relay.ser.is_open 的健康檢查，提高狀態判斷可信度。
負面影響
程式碼複雜度略為增加
為了支援「只重連未連線設備」與健康檢查，measure_engine.py 需要增加多個內部輔助方法，使初始化邏輯比舊版稍微複雜。
仍依賴 driver 狀態旗標的正確性
雖然已加入輕量健康檢查，但若未來某些 driver 的 is_connected 與實際設備狀態不同步，仍可能造成誤判，因此後續 driver 設計仍需維持一致性。
Chamber 仍為相容性保留設計
若目前專案尚未完整實作 chamber driver 的連線與健康檢查能力，則 Chamber 狀態仍可能只反映有限資訊，需待後續硬體整合時再進一步完善。