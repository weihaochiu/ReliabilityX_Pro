"""Inactive diagnostic scaffold; unsafe legacy R-line entry disabled (OI-054)."""

from typing import Callable, Dict, Optional


class DiagnosticsService:
    """Run hardware diagnostics without embedding them in MeasureEngine.

    Args:
        hardware_manager: HardwareManager instance.
        relay_path_service: RelayPathService instance.
        smu_driver: SMU driver instance.
        log_info: Logger callback for info-level messages.
        log_warning: Logger callback for warning-level messages.
        log_error: Logger callback for error-level messages.
    """

    def __init__(
        self,
        hardware_manager,
        relay_path_service,
        smu_driver=None,
        log_info: Callable[[str], None] = lambda msg: None,
        log_warning: Callable[[str], None] = lambda msg: None,
        log_error: Callable[[str], None] = lambda msg: None,
    ):
        self.hardware_manager = hardware_manager
        self.path_service = relay_path_service
        self.smu = smu_driver
        self._log_info = log_info
        self._log_warning = log_warning
        self._log_error = log_error

    def measure_line_resistance(
        self,
        pos_pin: int,
        neg_pin: int,
        sleep_fn: Callable[[float], None],
        read_vi_before_reset: Optional[Callable[[], object]] = None,
    ) -> float:
        """Reject the unintegrated legacy R-line path; use the queued engine route.

        Args:
            pos_pin: Physical positive relay pin.
            neg_pin: Physical negative relay pin.
            sleep_fn: Interruptible sleep function from the engine layer.
            read_vi_before_reset: Optional callback to capture final SMU readback.

        Raises:
            RuntimeError: This scaffold lacks v2 qualification and is disabled.
        """
        message = "Legacy DiagnosticsService R-line disabled; use MeasureEngine queued v2 diagnostics"
        self._log_error(message)
        raise RuntimeError(message)

    def perform_spot_check(
        self,
        ch_id: int,
        pos_pin: int,
        neg_pin: int,
        sleep_fn: Callable[[float], None],
    ) -> Dict[str, float]:
        """Perform a quick connection test on one channel.

        Args:
            ch_id: Logical channel ID.
            pos_pin: Physical positive relay pin.
            neg_pin: Physical negative relay pin.
            sleep_fn: Interruptible sleep function from the engine layer.

        Returns:
            Dict[str, float]: Measured voltage and current.

        Raises:
            RuntimeError: If measurement-ready hardware is unavailable.
            IOError: If relay path creation fails.
        """
        if not self.hardware_manager.is_measurement_ready():
            raise RuntimeError("硬體未就緒，無法執行連線測試。")

        try:
            self.path_service.prepare_measurement_path(
                ch_id=ch_id,
                relay_pos=pos_pin,
                relay_neg=neg_pin,
                sleep_fn=sleep_fn,
                settle_sec=0.3,
            )

            self.smu.configure_source(voltage=0.0, current_limit=0.1)
            self.smu.output_control(True)
            sleep_fn(0.1)

            v_msd, i_msd = self.smu.read_vi()
            self._log_info(f"CH{ch_id:02d} SpotCheck: V_msd={v_msd:.4f} V, I_msd={i_msd:.3e} A")
            return {"v_msd": v_msd, "i_msd": i_msd}
        finally:
            if self.smu and self.hardware_manager.probe_smu_connected():
                try:
                    self.smu.output_control("OFF")
                except Exception:
                    pass

            if self.hardware_manager.probe_relay_connected():
                try:
                    self.path_service.cleanup_measurement_path(sleep_fn=sleep_fn, settle_sec=0.05)
                except Exception as exc:
                    self._log_warning(f"CH{ch_id:02d} Spot Check 後 Relay 清空失敗: {exc}")
