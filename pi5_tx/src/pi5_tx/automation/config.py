"""Configuration for inert Pi-side automation surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class AutomationConfig:
    """Runtime settings for future Pixhawk automation and takeover tests."""

    device: str = "/dev/serial0"
    baud: int = 57600
    altitude_step_m: float = 1.0
    min_current_altitude_m: float = 2.0
    min_target_altitude_m: float = 1.0
    cooldown_s: float = 5.0
    execute_timeout_s: float = 5.0
    setpoint_rate_hz: float = 5.0
    pilot_stick_deadband_pwm: int = 40
    automation_enable_channel: int | None = None
    dry_run: bool = True

    @classmethod
    def from_env(cls) -> "AutomationConfig":
        """Build a config from DVS_* or Makefile-friendly environment variables."""

        enable_channel = _env_optional_value(
            "DVS_AUTO_ENABLE_CHANNEL", "AUTO_ENABLE_CHANNEL"
        )
        return cls(
            device=_env_value("DVS_MAVLINK_DEVICE", "MAVLINK_DEVICE", "/dev/serial0"),
            baud=int(_env_value("DVS_MAVLINK_BAUD", "MAVLINK_BAUD", "57600")),
            dry_run=_truthy(_env_value("DVS_AUTO_DRY_RUN", "AUTO_DRY_RUN", "1")),
            automation_enable_channel=None
            if enable_channel in (None, "")
            else int(enable_channel),
            altitude_step_m=float(
                _env_value("DVS_ALTITUDE_STEP_M", "ALTITUDE_STEP_M", "1.0")
            ),
            min_current_altitude_m=float(
                _env_value(
                    "DVS_MIN_CURRENT_ALTITUDE_M", "MIN_CURRENT_ALTITUDE_M", "2.0"
                )
            ),
            min_target_altitude_m=float(
                _env_value("DVS_MIN_TARGET_ALTITUDE_M", "MIN_TARGET_ALTITUDE_M", "1.0")
            ),
            cooldown_s=float(_env_value("DVS_AUTO_COOLDOWN_S", "AUTO_COOLDOWN_S", "5.0")),
            execute_timeout_s=float(
                _env_value("DVS_AUTO_EXECUTE_TIMEOUT_S", "AUTO_EXECUTE_TIMEOUT_S", "5.0")
            ),
            setpoint_rate_hz=float(
                _env_value("DVS_AUTO_SETPOINT_RATE_HZ", "AUTO_SETPOINT_RATE_HZ", "5.0")
            ),
            pilot_stick_deadband_pwm=int(
                _env_value(
                    "DVS_PILOT_STICK_DEADBAND_PWM",
                    "PILOT_STICK_DEADBAND_PWM",
                    "40",
                )
            ),
        )


def _env_value(primary: str, secondary: str, default: str) -> str:
    return os.getenv(primary) or os.getenv(secondary) or default


def _env_optional_value(primary: str, secondary: str) -> str | None:
    value = os.getenv(primary)
    if value is not None:
        return value
    return os.getenv(secondary)


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "y", "on"}
