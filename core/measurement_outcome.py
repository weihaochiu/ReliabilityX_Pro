"""Explicit channel outcomes shared by measurement and scheduler (OI-050)."""

from dataclasses import asdict, dataclass
import math


def validate_channel_for_measurement(channel: dict, safety: dict, total_relays: int) -> str:
    """Check a channel before it can operate a relay path or enable SMU output.

    Args:
        channel: Saved logical channel settings.
        safety: Global voltage/current compliance bounds.
        total_relays: Physical board channel count.

    Returns:
        Diagnostic error, or an empty string for valid settings.
    """
    try:
        if not all(str(channel.get(key) or "").strip() for key in ("user", "project", "device_name")):
            return "使用者、專案或設備名稱未設定"
        pos, neg = int(channel["relay_pos"]), int(channel["relay_neg"])
        if pos == neg or not (1 <= pos <= total_relays and 1 <= neg <= total_relays):
            return "Relay pair 超出範圍或正負端使用相同 Relay"
        keys = ("v_start", "v_stop", "v_step", "i_limit", "area", "delay_time", "interval_min")
        values = {key: float(channel[key]) for key in keys}
        if not all(math.isfinite(value) for value in values.values()):
            return "量測參數包含非有限數值"
        if values["v_step"] <= 0 or values["v_stop"] <= values["v_start"]:
            return "V step 必須大於零，V stop 必須大於 V start"
        if values["v_step"] > values["v_stop"] - values["v_start"]:
            return "V step 超過掃描電壓範圍"
        if values["area"] <= 0 or min(values["delay_time"], values["interval_min"]) < 0:
            return "面積必須大於零，延遲與量測間隔不可為負"
        if not 0 < values["i_limit"] <= float(safety["I_MAX"]):
            return "電流 compliance 超過全域限制或不大於零"
        if max(abs(values["v_start"]), abs(values["v_stop"])) > float(safety["V_MAX"]):
            return "掃描電壓超過全域限制"
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return f"量測參數不完整或格式錯誤: {exc}"
    return ""


@dataclass(frozen=True)
class ChannelOutcome:
    """Describe a channel attempt without confusing failure with completion.

    Attributes:
        ch_id: Logical channel identifier.
        status: Completed or classified failure code.
        error: Diagnostic reason, empty on success.
        cleanup_errors: Unconfirmed cleanup operations, if any.
    """

    ch_id: int
    status: str
    error: str = ""
    cleanup_errors: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        """Return whether measurement, persistence and cleanup succeeded."""
        return self.status == "completed" and not self.cleanup_errors

    def to_dict(self) -> dict:
        """Return JSON-compatible diagnostics for scan signals and state."""
        return asdict(self)
