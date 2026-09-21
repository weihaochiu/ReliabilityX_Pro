# README

## Offline regression and Git backup setup

The first formal pytest baseline is entirely offline and mock-only. Run it with:

```powershell
python -m pytest -q
```

`tests/conftest.py` blocks real VISA, serial, socket, production SMU-output, and physical relay entrypoints. Unit and integration tests use `tmp_path` for data/config/backup output and injected `MockSMU`, `MockRelay`, and `MockEnvironment` objects.

After a fresh clone, enable the tracked pre-push hook once:

```powershell
python tools/install_git_hooks.py
```

The hook invokes `tools/create_git_backup.py --trigger pre-push` for the commit supplied by Git. A validated atomic ZIP is written under local ignored `BACKUP/`; only the latest 10 matching archives are retained. The ZIP is derived from `git archive`, includes `BACKUP_MANIFEST.json`, and excludes the working tree, `.git`, runtime data/logs, live ignored config, `_local_only`, credentials, and previous backups. Any creation, validation, or retention failure exits non-zero and blocks the push. Manual validation remains available through `python tools/create_git_backup.py`.

## Public repository baseline

Public Git tracking excludes scientific measurement output, logs, caches, historical stamped snapshots, third-party manuals, credentials, personal paths, runtime channel/archive data, calibration results, personnel profiles, and hardware-specific connection settings. Safe schemas are provided as `config/*.example.json`; bundled measurement/environment/station recipes remain tracked as required defaults. Local live JSON files must never contain secrets intended for commit.

## Runtime dependency bootstrap

從 2026-06-02 版本起，source-code 模式執行 `main.py` 時，程式會先執行 `dependency_bootstrap.ensure_runtime_dependencies()`。若新電腦只安裝 Python、尚未安裝 ReliabilityX Pro 所需套件，系統會在載入 PyQt6 前自動檢查並嘗試安裝：PyQt6、pyqtgraph、numpy、scipy、matplotlib、pyserial、pyvisa、pyvisa-py、reportlab、pandas。

手動安裝可使用：

```bat
python -m pip install -r requirements_runtime.txt
```

若自動安裝失敗，請查看：

```text
logs/dependency_bootstrap.log
```

注意：此功能只安裝 Python 套件；NI-VISA、USB-to-Serial、SMU/Relay/Chamber 廠商驅動仍需另外安裝。


## Stage 3.0
This skeleton adds a shared Environment Recipe editor page:
- formal main entry from SystemConfigDialog
- shortcut buttons from each environment tab
- three recipe field-model editors
- JSON-backed load/save only

## Dynamic Logical Channel Mode

The main window now shows only configured logical channels instead of a fixed CH01-CH32 grid. Users can add channels as needed. The displayed channel label is generated from the selected environment:

- `CH_C##` for climate chamber instances
- `CH_I##` for indoor instances
- `CH_V##` for vacuum / glovebox instances

Relay selection remains simple: users directly select SMU+ and SMU− relays. After an environment is selected, relay dropdowns are limited to that environment's configured relay ranges. The dialog shows whether each relay is independent or shared with another device using the same polarity. Same-polarity sharing is allowed after confirmation; opposite-polarity reuse is blocked.

Measurement scheduling is now per channel. Each active logical channel uses its own `interval_min` and next due time instead of the first channel's interval controlling the whole scan round. The relay safety behavior remains conservative: before each channel measurement, all relays are reset and only the target channel's two relays are opened.


## Environment-grouped channel display and end-channel action

The main dynamic channel list is grouped by environment family / instance so `CH_V##`, `CH_I##`, and `CH_C##` channels are not mixed in a single row. The detail dialog uses the same environment inference logic as the card display, including fallback from legacy `channel_label` prefixes and relay ranges.

Each channel card includes `結束實驗 / 移除`. This removes the logical channel from the active configuration and frees the relay path for future channel creation. Existing measurement data, summaries, and logs are preserved. The final channel settings are archived to `config/archived_channel_settings.json`. Channel removal is disabled while a measurement is running; stop the scan first and wait for the current channel to finish safely.


## Dynamic Channel Toggle Notes

- The checkbox in each channel card controls whether that logical channel is included in cyclic measurement.
- Checked cards show `開始循環量測`; unchecked cards show `暫停循環量測`. Changing this state requires confirmation to prevent accidental experiment start/pause.
- `結束實驗 / 移除` is separate from pause: it archives/removes the active logical channel configuration and releases the relay path, while existing measurement data remains untouched.
- Empty legacy channel records without a complete relay path are not shown in the active dynamic channel list.


## Global cyclic measurement controls

The left-side system control buttons now operate the global scheduler, while each channel card checkbox only controls whether that individual logical channel is included in cyclic measurement.

- `▶ 啟動全部循環量測`: starts the global scheduler after confirmation and only includes cards currently marked `開始循環量測`.
- `⏸ 停止全部循環量測`: requests a graceful global stop after confirmation. The current channel completes its forward/reverse scan before the scheduler stops at a safe relay boundary.
- The global status label shows stopped, scheduler-running, current-channel measuring, safe-stopping, or error-stopped states.
- Stopping the scheduler does not delete channel settings, release relay assignments, or remove scientific data. Use `結束實驗 / 移除` on a channel card for that workflow.

## Open Items and Technical-Debt Tracking

`docs/OPEN_ITEMS.md` is the canonical backlog for ReliabilityX Pro. It lists current open items, priority, status, evidence, affected modules, next actions, and acceptance criteria.

Before modifying code, maintainers and AI assistants should review:

1. `docs/OPEN_ITEMS.md`
2. `docs/ADR_INDEX.md`
3. relevant `docs/adr/*.md`
4. `docs/version_history.txt`
5. `docs/ARCHITECTURE.md` and `docs/CODEBASE_MAP.md`

Root-level `ToDo list.txt` is no longer authoritative and only points to `docs/OPEN_ITEMS.md`. Patch ZIPs should not include `CHANGESET_MANIFEST.md` unless explicitly requested; delivery summaries belong in the response, while durable records belong in the docs files listed above.


### Drift-free scheduler conflict handling

When two or more devices become due at the same time, ReliabilityX Pro queues them because one SMU/relay resource can only measure one channel at a time. Queue delay is recorded in logs, IV CSV metadata, and Summary_report scheduler columns. Future due times do not drift: `next_due` is advanced from the original scheduled due time plus `interval_min`, not from the delayed actual finish time.

### Telegram secret handling

For release-safe Telegram notification setup, do not place the real Bot Token or Chat ID directly in `config/notification_settings.json`. Instead, create local TXT files outside the project package and set `bot_token_file` and `chat_id_file` to those paths. Each TXT file should contain exactly one value on the first line. The ZIP package includes only examples and blank defaults.


## Safe Shutdown / Emergency Exit

主畫面提供「🛑 安全關閉程式」。按下後可選擇 `安全流程關閉` 或 `緊急停止並關閉`。安全流程會等待目前 channel 到安全停止邊界後再關閉 SMU output、reset all relay、儲存 runtime state 並離開；緊急流程會立即強制硬體安全狀態，但目前量測點可能不完整。相關設計見 ADR-0044。

## System Config Shell and Station Recipes

The global configuration dialog now uses a left-navigation shell with a right-side content area instead of exposing all configuration pages as crowded same-level tabs.  The first page is a dashboard that summarizes SMU, Relay, Chamber, calibration, notification, and Station Recipe state.  Advanced settings are collapsed by default.

Recipe responsibilities are separated:

- **Measurement Recipe**: IV scan conditions such as voltage range, step, delay, interval, compliance current, and area.
- **Station Recipe / Hardware Recipe**: hardware/environment station configuration such as SMU, Relay, Chamber, environment profile, calibration profile, and notification profile.

Station recipes are stored in `config/station_recipes.json`.  They are editable in the global settings dialog but are not yet automatically applied to runtime hardware initialization.

## 2026-05-17 System Config UX update

The System Config window now uses active-channel-scoped readiness:

- Dashboard checks only enabled channel cards and their required environments, relay pairs, R-line records, and hardware dependencies.
- Unused environments or unused hardware are not blocking errors.
- Measurement Recipes include built-in PSC templates for Normal Bandgap, WBG, NBG, and Perovskite-Si Tandem cells, with edit and duplicate workflows.
- Station Recipe and Environment Recipe are unified as Environment / Station Recipes.
- Relay / Channel Mapping owns environment relay ranges and shows a 3x2 environment-by-polarity relay availability summary.
- Calibration & R-line Diagnostics includes an active-pair readiness table and environment-filtered 3D R-line map.

A new `docs/UI_STYLE_GUIDE.md` file documents contrast rules for relay matrices and other status-heavy GUI components.


### Chamber setup diagnostics

For the climate chamber, select the COM port that matches the USB-RS485 converter name shown in Windows Device Manager, for example `CMS/ITRI USB to RS485 (COM8)`. The connection test now requires Signal `01` PV/SV readback. If COM opens but PV remains `ERR`, use the manual debug terminal to copy the TX/RX ASCII and HEX report and verify station ID, RS485 A/B wiring, remote communication enablement, and the vendor FCS algorithm.

### SMU and Relay connection diagnostics

SMU connection logs identify the selected VISA backend, enumerated resources, requested resource, timeout, `*IDN?` response, and the exact failing stage. An empty `*IDN?` reply is a failure rather than a connected state. The System Configuration SMU page restores the saved IP/VISA address after applying the interface hint; when that value is absent, it may display the active driver's last successful connection setting.

Relay connection logs enumerate every visible COM device with description/HWID/VID:PID where available. Each attempted port records baudrate, `ver\r` TX/RX ASCII and HEX, and classifies no-port, serial-open exception, no-response timeout, or identifier mismatch. The final error includes the attempted ports and directs the operator to the relevant driver/cable/port/baud/identifier checks.


#### Chamber FCS and Signal 01 decoding

For the CMS/ITRI USB-RS485 chamber path, field diagnostics on 2026-06-02 showed that the chamber responds to `xor8_include_at` FCS. The production driver therefore sends Signal `01` using XOR8 over the frame including the leading `@`. Signal `01` analog data is decoded as 4-character HEX words scaled by `/100`; unused values such as `7FFF`, `FFFF`, or `----` are shown as unavailable rather than as numeric telemetry.

#### Failure log diagnostics

ReliabilityX Pro now treats detailed persistent error logging as a required runtime behavior. If a GUI dialog says a hardware command failed, the corresponding log should include enough detail to diagnose the failure without guessing: command name, hardware settings, TX/RX ASCII, TX/RX HEX, checksum/FCS result, parser result, exception traceback when present, and safety action. SMU, Relay, and Chamber connection paths follow this rule; future file IO, parser, and scheduler failures should follow the same pattern.

## 2026-09-20 多通道上機版本

請依 [MACHINE_TEST_GUIDE.md](MACHINE_TEST_GUIDE.md) 準備測試機並完成短程驗收。全域按一次啟動後自動量測各通道；運行中 checkbox 可個別啟動／暫停，當前通道完成正逆掃與清理後生效。全部暫停時保持等待，恢復不補測暫停時段。故障即停止全域排程，禁止誤算成功。

開發驗證：Python 3.12、Windows、pytest mock-only/offscreen。`setup_and_check.bat` 會安裝 pytest 與 runtime；未建立任何實體儀器連線。測試機本身仍應重跑並驗證廠商驅動、校正、接線與資料儲存。
