14. 線路阻抗讀取改為依 Relay 組合即時查詢並相容新舊格式
日期: 2026-03-26
狀態: 已接受並實施
背景 (Context)

在通道設定視窗中，使用者可以手動調整 Relay Pos 與 Relay Neg 的接線代號，以指定實際量測通道所對應的正負極繼電器腳位。

原本系統中，線路阻抗（R-line）的顯示邏輯存在以下問題：

切換 relay 組合後不會即時更新既有的線路阻抗值
畫面上的 R-line 通常只會在載入資料時更新一次。
若使用者在視窗中手動改變 Relay Pos 或 Relay Neg，即使 calibration_settings.json 中已經存在對應組合的阻抗資料，畫面也不會立刻顯示。
R-line 的讀取時機過於被動
原本邏輯偏向在 set_data() 或量測完成後才更新顯示。
這使得使用者在調整接線代號時，無法立即得知目前組合是否已有校正資料可沿用。
calibration_settings.json 中的資料格式已經混用新舊兩種結構
舊格式直接以數值儲存，例如：
"7_60": 21.578
新格式則儲存為包含數值與時間的物件，例如：
"10_55": {"value": 1.9455, "time": "2026-03-05 15:34:23"}
若讀取邏輯只支援單一格式，則會造成部分既有資料無法正確顯示。
需要保留既有量測與儲存流程
系統原本已具備量測線路阻抗後寫入 calibration_settings.json 的能力。
本次修改不應破壞原有的量測、儲存、通道設定保存與硬體映射更新流程。

因此，需要將 R-line 顯示機制改為：
當使用者改變正負極 relay 組合時，立即依目前組合查詢既有校正資料並更新畫面，同時兼容新舊資料格式。

決策 (Decision)

我們決定調整通道設定視窗與 relay 動作元件的責任分工，讓 R-line 的顯示改為依目前所選 relay 組合即時查詢 calibration_settings.json 中的 line_resistance_map，並統一支援新舊資料格式。

1. 由 channel_setting_dialog.py 負責 relay 組合變更時的即時查詢
在 ChannelSettingDialog 中，新增對以下控制項的 signal 連接：
combo_relay_pos.currentTextChanged
combo_relay_neg.currentTextChanged
當任一 relay 選項改變時，立即呼叫更新函式，重新查詢目前組合的 R-line。
查詢來源為：
config.CALIBRATION_SETTINGS_FILE
其中的 line_resistance_map

這讓 R-line 顯示不再只依賴初始化時的 set_data()，而是能隨使用者操作即時刷新。

2. 由 channel_action_widget.py 封裝 R-line 顯示邏輯
在 ChannelActionWidget 中，新增專責方法處理：
依 relay_pos / relay_neg 組成 key，例如 10_55
從 line_resistance_map 中查找對應資料
將結果格式化後顯示到 label_rline
同時新增錯誤顯示方法，以便在讀檔失敗或格式異常時，畫面能維持明確狀態，而不是靜默失敗。

這樣可將「畫面顯示」與「資料讀取觸發時機」拆開，使結構更清楚。

3. 相容舊格式與新格式的線路阻抗資料
讀取邏輯同時支援：
舊格式：float / int
新格式：{"value": ..., "time": ...}
若讀到的是：
數值型別：直接顯示阻抗值
物件型別：顯示阻抗值，若有時間欄位則一併顯示時間
若格式不符預期，則顯示預設文字或錯誤提示，而不讓 UI 崩潰。

此決策可避免因校正檔歷史資料格式不一致而造成相容性問題。

4. 新量測結果統一寫入新格式
當使用者執行「量測線路阻抗」後：
仍透過既有 engine 流程取得量測值
寫回 line_resistance_map
但寫入格式統一為：
{"value": round(resistance, 4), "time": "YYYY-MM-DD HH:MM:SS"}
量測完成後立即重新刷新目前畫面上的 R-line 顯示。

此作法可讓後續新增的資料逐步收斂到一致格式，同時不破壞舊資料的可讀性。

5. 保留原有通道設定與硬體映射流程
本次修改不變更以下既有功能：
通道啟用狀態與基本資訊儲存
IV 量測參數儲存
relay_pos / relay_neg 儲存到 channel settings
HARDWARE_MAP 更新機制
即時連線測試（spot check）流程

也就是說，本次變更僅聚焦於：

R-line 讀取時機
R-line 顯示邏輯
新舊資料格式相容性

而不改動量測系統的核心行為。

影響 (Consequences)
正面影響
使用者操作更直覺
當使用者調整 Relay Pos / Relay Neg 時，若系統已存在該組合的 R-line 校正值，畫面會立即顯示，不再需要重新開視窗或再次量測。
減少重複量測
已有的線路阻抗資料可以被即時辨識並沿用，降低不必要的重測次數。
提升資料相容性
系統現在可同時讀取舊格式數值與新格式物件，不會因歷史資料格式混用而顯示失敗。
資料可追溯性提升
新量測資料統一包含時間欄位，後續更容易判斷某組 R-line 的取得時間與新鮮度。
程式責任分工更清楚
channel_setting_dialog.py 負責觸發更新與流程控制，channel_action_widget.py 負責 UI 顯示與格式解析，維護性較佳。
負面影響
程式碼結構略為增加
為了支援即時查詢與格式相容，新增了 R-line 更新方法、格式解析方法與額外的 signal connection。
讀檔頻率增加
每次變更 relay 組合時，都會重新讀取一次 calibration_settings.json。在目前資料量小的情況下影響可忽略，但若未來校正資料規模明顯增加，可能需要考慮快取機制。
舊資料不會自動轉檔
雖然系統已能讀取舊格式，但目前不會在背景自動將舊資料批次轉換為新格式；因此校正檔在一段時間內仍可能維持混合格式狀態。