# ADR-0023: MeasureEngine Phase 1 解耦

- **日期**: 2026-04-01
- **狀態**: Accepted
- **決策者**: ReliabilityX Pro 開發團隊

## 背景

`MeasureEngine` 目前同時承擔：

- 硬體狀態探測與重連
- Relay 路徑切換與 reset
- 線阻量測與 spot-check 診斷
- 掃描生命週期協調
- 單通道正逆掃流程
- 分析與存檔協調

此外，`ChannelSettingDialog` 直接呼叫被 `moveToThread()` 的 `MeasureEngine` 診斷方法，而 `MainWindow.closeEvent()` 直接呼叫 `engine.shutdown_hardware()`，兩者都會模糊 UI thread 與 worker thread 的邊界。

## 決策

採用分階段解耦策略，**Phase 1 僅抽離最關鍵且最具 thread-boundary 風險的責任**，保留 `MeasureEngine` 作為外部穩定 façade。

### Phase 1 新模組

- `core/hardware/hardware_manager.py`
- `core/hardware/relay_path_service.py`
- `core/diagnostics/diagnostics_service.py`

### `MeasureEngine` 在 Phase 1 的定位

- 保留對外公開 API 與 signals
- 保留 scan lifecycle 狀態管理
- 將硬體生命週期、relay path 控制與 diagnostics 實作委派至新服務
- 暫時保留 `measure_single_channel()` 與 `scan_sequence()`，待 Phase 2 再抽出

### UI thread / worker thread 修正

- `ChannelSettingDialog` 改用 queued signal：
  - `request_rline_measurement` → `MeasureEngine.request_measure_line_resistance`
  - `request_spot_check` → `MeasureEngine.request_spot_check`
- `MainWindow` 新增 `request_shutdown_hardware`，以 `BlockingQueuedConnection` 送往 worker thread 執行關機

## 為什麼不一次拆更多

若在同一階段同時抽出 `ChannelMeasurementRunner`、`ResultPersistenceService`、`ScanScheduler`，會放大風險，並增加 UI / Notification / TrendChart 的回歸面積。

Phase 1 的目標是：

1. 先修 thread boundary
2. 先建立服務邊界
3. 保持外部 API 穩定

## 後續規劃

### Phase 2

- 抽出 `ChannelMeasurementRunner`
- 抽出 `ResultPersistenceService`
- 讓 `MeasureEngine` 更像純 orchestration façade

### Phase 3

- 抽出 `ScanScheduler`
- 正式支援 per-channel interval
- 加入 relay occupancy / active-channel due-time 排程

## 代價與影響

### 優點

- 降低 `MeasureEngine` 的責任集中度
- 修補最主要的 worker-thread 使用風險
- 建立可持續演進的重構路徑

### 缺點

- `MeasureEngine` 仍暫時偏大，尚未完成全部拆分
- 保留同步 wrapper 以兼容舊呼叫端，代表部分 legacy 路徑仍需後續清理

## 決策結果

接受本決策，並以 Phase 1 為後續重構基礎。
