from typing import Callable


class RelayPathService:
    """Prepare and clean relay paths for measurement and diagnostics.

    Args:
        relay_driver: Relay driver instance.
        relay_probe_fn: Function that returns whether the relay is connected.
        log_info: Logger callback for info-level messages.
        log_warning: Logger callback for warning-level messages.
        log_error: Logger callback for error-level messages.
    """

    def __init__(
        self,
        relay_driver=None,
        relay_probe_fn: Callable[[], bool] = lambda: False,
        log_info: Callable[[str], None] = lambda msg: None,
        log_warning: Callable[[str], None] = lambda msg: None,
        log_error: Callable[[str], None] = lambda msg: None,
    ):
        self.relay = relay_driver
        self._relay_probe_fn = relay_probe_fn
        self._log_info = log_info
        self._log_warning = log_warning
        self._log_error = log_error

    def reset_all(self, sleep_fn: Callable[[float], None], settle_sec: float = 0.1) -> None:
        """Reset all relay channels and wait for mechanical settling.

        Args:
            sleep_fn: Interruptible sleep function from the engine layer.
            settle_sec: Relay settling time in seconds.

        Raises:
            IOError: If relay is unavailable or reset fails.
        """
        if not self.relay or not self._relay_probe_fn():
            raise IOError("Relay 未連線，無法執行 reset_all。")
        if not self.relay.reset_all():
            raise IOError("Relay reset_all() 失敗。")
        if settle_sec > 0:
            sleep_fn(settle_sec)

    def prepare_measurement_path(
        self,
        ch_id: int,
        relay_pos: int,
        relay_neg: int,
        sleep_fn: Callable[[float], None],
        settle_sec: float = 0.3,
    ) -> None:
        """Prepare a dedicated relay path for one channel.

        Args:
            ch_id: Logical channel ID.
            relay_pos: Physical positive relay pin.
            relay_neg: Physical negative relay pin.
            sleep_fn: Interruptible sleep function from the engine layer.
            settle_sec: Settling time after switching.

        Raises:
            IOError: If switching the relay pair fails.
        """
        self.reset_all(sleep_fn=sleep_fn, settle_sec=0.1)

        res1 = self.relay.switch_on(relay_pos)
        res2 = self.relay.switch_on(relay_neg)
        if not (res1 and res2):
            raise IOError(
                f"Relay 切換失敗，無法建立 CH{ch_id:02d} 的獨立量測路徑 "
                f"(pins {relay_pos}, {relay_neg})"
            )

        if settle_sec > 0:
            sleep_fn(settle_sec)

    def cleanup_measurement_path(
        self,
        sleep_fn: Callable[[float], None],
        settle_sec: float = 0.05,
    ) -> None:
        """Reset relay path after a measurement or diagnostic action."""
        self.reset_all(sleep_fn=sleep_fn, settle_sec=settle_sec)
