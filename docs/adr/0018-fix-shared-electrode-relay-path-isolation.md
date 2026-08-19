# ADR-0018: 修正多通道 IV 掃描的 Relay 路徑殘留問題

- **日期**: 2026-03-27
- **狀態**: 已接受並實施

## 背景 (Context)

在多通道 IV 掃描中，發現第一個 channel 的短路電流 (`Isc`) 量測值正常，但後續 channel 的 `Isc` 明顯偏高，且越後面的通道偏差越大。

進一步比對即時量測（spot check）與正式 IV scan 的結果後，確認這不是元件效率突然上升，也不是線阻校正所造成的誤差，而是量測路徑切換流程存在問題。

此次案例中，多顆電池共用同一個電極，因此只要前一顆 channel 的 relay 路徑沒有被正確清除，後一顆 channel 在量測時，就可能把前面已接上的元件一併掛到 SMU 量測路徑上，造成電流被疊加。

## 根本原因分析 (Root Cause Analysis)

原本的 `measure_engine.py` 在每輪掃描開始時，只呼叫一次 `relay.prepare_for_measurement()`，也就是只在整輪最前面做一次 relay 清空。

但在後續每個 channel 的 `measure_single_channel()` 中，程式僅執行：
- 打開當前 channel 的 `relay_pos`
- 打開當前 channel 的 `relay_neg`
- 直接開始掃描

流程中並沒有在「每個 channel 開始前」再次執行 `reset_all()`，也沒有在「每個 channel 結束後」清除上一個 channel 的 relay 狀態。

另一方面，`relay_driver.py` 的 `switch_on()` 是直接送出 `relay on XX` 指令，屬於累加開啟行為；真正會將所有 relay 關閉的只有 `reset_all()`。

因此，在多顆元件共用同一個電極的配置下，量測流程會變成：
1. 第一顆 channel 在乾淨路徑下量測，因此結果正常。
2. 第二顆 channel 開始時，前一顆 channel 的 relay 仍可能保持導通，造成兩顆元件同時掛在線路上。
3. 第三顆 channel 再往後量時，又可能把前兩顆一起納入，導致量測電流進一步放大。

這就是造成「第一個 channel 正常、後面的 channel 電流偏高」的主因。

## 決策 (Decision)

為了解決這個問題，我們決定將 IV 掃描流程改為「每個 channel 完全獨立建立與清除 relay 路徑」，避免任何前一通道的殘留連線影響後一通道的結果。

具體決策如下：
1. **修改 `measure_engine.py`**：新增 channel 級別的 relay 路徑準備與清除流程。
2. **新增 `_relay_reset_all()` 輔助函式**：集中處理 relay 全清空與必要的穩定等待。
3. **新增 `_prepare_channel_path()` 輔助函式**：在每個 channel 量測前，固定執行：
   - `relay.reset_all()`
   - 只打開當前 channel 的 `relay_pos`
   - 只打開當前 channel 的 `relay_neg`
   - 等待路徑穩定後再開始掃描
4. **新增 `_cleanup_channel_path()` 輔助函式**：在每個 channel 量測結束後，再次執行 `relay.reset_all()`，避免殘留路徑影響下一顆元件。
5. **保留既有掃描與分析邏輯**：本次修改僅針對 relay 路徑隔離，不改動 IV 掃描點位、線阻修正公式與參數分析流程。
6. **補強 spot check 診斷資訊**：將 spot check 的 log 改為輸出實際量到的 `V_msd` 與 `I_msd`，便於後續判斷量測時是否真的在 0 V 條件下讀值。

## 影響 (Consequences)

### 正面影響
- **修正多通道電流疊加問題**：每個 channel 都在獨立的 relay 路徑下量測，可避免共用電極配置下的前一通道殘留影響。
- **恢復 IV 結果可信度**：後續 channel 的 `Isc` 不再因為路徑殘留而被放大，量測結果會更接近元件實際表現。
- **提升診斷能力**：spot check 顯示實測電壓與電流後，未來更容易分辨是路徑問題、SMU source 狀態問題，還是元件本身異常。
- **修改範圍集中**：本次修正聚焦於 relay 路徑切換與隔離，不影響既有 IV 分析演算法與檔案輸出格式。

### 負面影響
- **每個 channel 會多一次 relay reset 與等待時間**：因此整體掃描時間會略微增加。
- **對 relay 穩定性要求提高**：若 relay 板本身反應不穩或 reset 指令失敗，將更直接影響單通道掃描啟動與結束流程。
