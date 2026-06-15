"""Pi-side automation boundaries."""

from .config import AutomationConfig
from .events import AltitudeDirection, TriggerEvent
from .gesture_control import AltitudeControlResult, SitlGestureAltitudeController

__all__ = [
    "AltitudeControlResult",
    "AltitudeDirection",
    "AutomationConfig",
    "SitlGestureAltitudeController",
    "TriggerEvent",
]
