# MeasureEngine Phase 1 實作藍圖

## 目標

Phase 1 的目標不是一次重寫整個 `MeasureEngine`，而是：

1. 修補 UI thread / worker thread 邊界
2. 將最容易膨脹的責任抽出
3. 保持外部 API 穩定

## 新增模組與責任

### `core/hardware/hardware_manager.py`

負責：

- `probe_smu_connected()`
- `probe_relay_connected()`
- `probe_chamber_connected()`
- `connect_*_if_needed()`
- `initialize_hardware()`
- `emit_status(...)`
- `is_measurement_ready()`
- `shutdown_hardware()`

### `core/hardware/relay_path_service.py`

負責：

- `reset_all(...)`
- `prepare_measurement_path(...)`
- `cleanup_measurement_path(...)`

### `core/diagnostics/diagnostics_service.py`

負責：

- `measure_line_resistance(...)`
- `perform_spot_check(...)`

## `MeasureEngine` 保留 / 移出清單

### 保留

- `initialize_hardware()`
- `start_scan_cycle(list)`
- `stop_scan_cycle()`
- `reload_config()`
- `shutdown_hardware()`
- `measure_single_channel(...)` *(Phase 2 才抽出)*
- `scan_sequence(...)` *(Phase 2 才抽出)*
- 既有對外 signals

### 新增

- `request_measure_line_resistance(int, int, int)`
- `request_spot_check(int, int, int)`
- `line_resistance_measured(dict)`
- `spot_check_completed(dict)`

### 移出

- 硬體 probe / reconnect / shutdown 細節
- relay path reset / prepare / cleanup 細節
- diagnostics 細節

## UI 調整

### `gui/channel_setting_dialog.py`

由：

- 直接呼叫 `engine.measure_line_resistance(...)`
- 直接呼叫 `engine.perform_spot_check(...)`

改為：

- `request_rline_measurement.emit(ch_id, pos_pin, neg_pin)`
- `request_spot_check.emit(ch_id, pos_pin, neg_pin)`
- 由 `on_line_resistance_measured(...)` / `on_spot_check_completed(...)` 接收結果

### `gui/main_window.py`

由：

- `closeEvent()` 直接呼叫 `engine.shutdown_hardware()`

改為：

- `request_shutdown_hardware` signal
- 透過 `BlockingQueuedConnection` 送至 worker thread

## 風險與注意事項

1. **legacy 呼叫端兼容**
   - 本階段保留 `MeasureEngine.measure_line_resistance(...)` 與 `perform_spot_check(...)` 同步 wrapper
   - 目的是避免未更新模組立刻中斷

2. **不要在 Widget 中直接驅動 driver**
   - Widget 只能發 signal，不應執行 relay / smu 實際操作

3. **暫不處理 per-channel interval**
   - 目前 `start_scan_cycle()` 仍保留舊式 round-based interval
   - 這是 Phase 3 的 `ScanScheduler` 議題

## 下一階段建議

### Phase 2

新增：

- `core/measurement/channel_measurement_runner.py`
- `core/services/result_persistence_service.py`

目標：

- 把 `measure_single_channel()` 與 `scan_sequence()` 自 `MeasureEngine` 拔出
- 讓 `MeasureEngine` 更專注在 orchestration

### Phase 3

新增：

- `core/measurement/scan_scheduler.py`

目標：

- 每個 channel 擁有自己的 `next_due_time`
- 支援 per-channel interval
- 為 recipe / occupancy / grouped notification 建立基礎
