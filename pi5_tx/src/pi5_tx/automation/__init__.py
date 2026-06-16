"""Pi-side automation boundaries."""

from .config import AutomationConfig
from .events import AltitudeDirection, TriggerEvent
from .gesture_control import AltitudeControlResult, GestureAltitudeController

__all__ = [
    "AltitudeControlResult",
    "AltitudeDirection",
    "AutomationConfig",
    "GestureAltitudeController",
    "TriggerEvent",
]
