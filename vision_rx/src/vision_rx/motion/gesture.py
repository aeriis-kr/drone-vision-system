"""Pose landmark gesture classification and debounce logic."""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, sqrt
from time import monotonic
from typing import Iterable, Literal, Sequence

from vision_rx.motion.types import Gesture, GestureDecision, Landmark

# BlazePose / MediaPipe pose landmark indices.
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HIP = 23
RIGHT_HIP = 24
_ARMS = (
    (LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST, "left"),
    (RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST, "right"),
)


@dataclass(frozen=True, slots=True)
class GestureConfig:
    """Tunable thresholds for the high-level vertical gesture mapper."""

    min_visibility: float = 0.60
    min_torso_height: float = 0.08
    min_wrist_elbow_delta_y_torso_ratio: float = 0.12
    min_up_elbow_angle_deg: float = 45.0
    max_up_elbow_angle_deg: float = 140.0
    min_down_elbow_angle_deg: float = 45.0
    max_down_elbow_angle_deg: float = 145.0
    max_hand_down_inward_wrist_dx_shoulder_ratio: float = 0.40
    max_elbow_shoulder_delta_y_torso_ratio: float = 0.45
    allow_partial_torso_reference: bool = False
    fallback_torso_height_shoulder_ratio: float = 1.5
    debounce_s: float = 1.0
    debounce_missing_grace_s: float = 0.35

    def arm_pose_options(self, torso_height: float, shoulder_span: float) -> "ArmPoseOptions":
        return ArmPoseOptions(
            min_keypoint_score=self.min_visibility,
            min_up_elbow_angle_deg=self.min_up_elbow_angle_deg,
            max_up_elbow_angle_deg=self.max_up_elbow_angle_deg,
            min_down_elbow_angle_deg=self.min_down_elbow_angle_deg,
            max_down_elbow_angle_deg=self.max_down_elbow_angle_deg,
            min_wrist_elbow_delta_y=self.min_wrist_elbow_delta_y_torso_ratio * torso_height,
            max_hand_down_inward_wrist_dx=self.max_hand_down_inward_wrist_dx_shoulder_ratio * shoulder_span,
            max_elbow_shoulder_delta_y=self.max_elbow_shoulder_delta_y_torso_ratio * torso_height,
        )


ArmPoseState = Literal["HAND_UP", "HAND_DOWN", "UNKNOWN"]


@dataclass(frozen=True, slots=True)
class ArmPoseOptions:
    """Per-arm pose thresholds in the same coordinate space as the input points."""

    min_keypoint_score: float = 0.50
    min_up_elbow_angle_deg: float = 45.0
    max_up_elbow_angle_deg: float = 140.0
    min_down_elbow_angle_deg: float = 45.0
    max_down_elbow_angle_deg: float = 145.0
    min_wrist_elbow_delta_y: float = 20.0
    max_hand_down_inward_wrist_dx: float = 80.0
    max_elbow_shoulder_delta_y: float = 110.0


@dataclass(frozen=True, slots=True)
class _ArmPoseEvaluation:
    state: ArmPoseState
    confidence: float
    angle_deg: float
    wrist_elbow_delta_y: float
    inward_wrist_dx: float
    elbow_shoulder_delta_y: float
    reason: str


@dataclass(frozen=True, slots=True)
class _ArmShape:
    gesture: Gesture
    confidence: float
    side: str
    reason: str


@dataclass(frozen=True, slots=True)
class _TorsoReference:
    height: float
    shoulder_span: float


class GestureDebouncer:
    """Require the same gesture for a minimum time before accepting it.

    STOP is emitted immediately for safety. UP/DOWN require stability so a
    single noisy frame does not move the drone.
    """

    def __init__(self, hold_s: float, missing_grace_s: float = 0.35) -> None:
        self.hold_s = hold_s
        self.missing_grace_s = missing_grace_s
        self._candidate = Gesture.UNKNOWN
        self._candidate_since_s = 0.0
        self._candidate_last_seen_s = 0.0
        self._stable = Gesture.STOP

    @property
    def stable(self) -> Gesture:
        return self._stable

    def update(self, gesture: Gesture, now_s: float | None = None) -> Gesture:
        now_s = monotonic() if now_s is None else now_s

        if self.hold_s <= 0:
            self._candidate = gesture
            self._candidate_since_s = now_s
            self._candidate_last_seen_s = now_s
            self._stable = gesture if gesture in (Gesture.UP, Gesture.DOWN) else Gesture.STOP
            return self._stable

        if gesture in (Gesture.UP, Gesture.DOWN):
            candidate_expired = (
                self._candidate not in (Gesture.UP, Gesture.DOWN)
                or gesture != self._candidate
                or now_s - self._candidate_last_seen_s > self.missing_grace_s
            )
            if candidate_expired:
                self._candidate = gesture
                self._candidate_since_s = now_s
            self._candidate_last_seen_s = now_s
            if now_s - self._candidate_since_s >= self.hold_s:
                self._stable = gesture
            return self._stable

        if self._stable != Gesture.STOP:
            self._candidate = gesture
            self._candidate_since_s = now_s
            self._candidate_last_seen_s = now_s
            self._stable = Gesture.STOP
            return self._stable

        if (
            self._candidate in (Gesture.UP, Gesture.DOWN)
            and now_s - self._candidate_last_seen_s <= self.missing_grace_s
        ):
            return self._stable

        self._candidate = gesture
        self._candidate_since_s = now_s
        self._candidate_last_seen_s = now_s
        self._stable = Gesture.STOP
        return self._stable


def classify_vertical_gesture(
    landmarks: Sequence[Landmark] | Iterable[Landmark] | None,
    config: GestureConfig | None = None,
) -> GestureDecision:
    """Classify UP/DOWN/STOP from one pose's normalized landmarks.

    A command is only accepted when the forearm is clearly above the elbow for
    UP, or clearly below the elbow for DOWN without folding inward toward the torso.
    """

    config = config or GestureConfig()
    if landmarks is None:
        return GestureDecision(Gesture.STOP, 0.0, "no pose")

    points = list(landmarks)
    if len(points) < 33:
        return GestureDecision(Gesture.STOP, 0.0, "pose has fewer than 33 landmarks")

    torso = _resolve_torso_reference(points, config)
    if isinstance(torso, GestureDecision):
        return torso

    shapes = [
        _classify_arm_shape(points, shoulder_i, elbow_i, wrist_i, side, torso.height, torso.shoulder_span, config)
        for shoulder_i, elbow_i, wrist_i, side in _ARMS
    ]
    active = [shape for shape in shapes if shape.gesture in (Gesture.UP, Gesture.DOWN)]
    if not active:
        best_rejection = max(shapes, key=lambda shape: shape.confidence, default=None)
        if best_rejection is None:
            return GestureDecision(Gesture.STOP, 0.0, "no elbow-corner arm shape")
        return GestureDecision(
            Gesture.STOP,
            best_rejection.confidence,
            f"no elbow-corner arm shape: {best_rejection.reason}",
        )

    gestures = {shape.gesture for shape in active}
    if len(gestures) > 1:
        return GestureDecision(Gesture.STOP, min(shape.confidence for shape in active), "conflicting arm shapes")

    best = max(active, key=lambda shape: shape.confidence)
    return GestureDecision(best.gesture, best.confidence, best.reason)


def _classify_arm_shape(
    points: Sequence[Landmark],
    shoulder_i: int,
    elbow_i: int,
    wrist_i: int,
    side: str,
    torso_height: float,
    shoulder_span: float,
    config: GestureConfig,
) -> _ArmShape:
    shoulder = points[shoulder_i]
    elbow = points[elbow_i]
    wrist = points[wrist_i]
    evaluation = _evaluate_arm_pose(shoulder, elbow, wrist, config.arm_pose_options(torso_height, shoulder_span))
    return _arm_shape_from_evaluation(side, evaluation)


def classify_arm_pose(
    shoulder: Landmark,
    elbow: Landmark,
    wrist: Landmark,
    options: ArmPoseOptions | None = None,
) -> ArmPoseState:
    """Classify one arm as HAND_UP, HAND_DOWN, or UNKNOWN."""

    return _evaluate_arm_pose(shoulder, elbow, wrist, options or ArmPoseOptions()).state


# Compatibility with the reference implementation's public name.
classifyArmPose = classify_arm_pose


def _evaluate_arm_pose(
    shoulder: Landmark,
    elbow: Landmark,
    wrist: Landmark,
    options: ArmPoseOptions,
) -> _ArmPoseEvaluation:
    confidence = _min_visibility([shoulder, elbow, wrist])
    angle_deg = calculate_elbow_angle_degrees(shoulder, elbow, wrist)
    wrist_elbow_delta_y = wrist.y - elbow.y
    inward_wrist_dx = _calculate_inward_wrist_dx(shoulder, elbow, wrist)
    elbow_shoulder_delta_y = abs(elbow.y - shoulder.y)

    if confidence < options.min_keypoint_score:
        return _arm_pose_result(
            "UNKNOWN",
            confidence,
            angle_deg,
            wrist_elbow_delta_y,
            inward_wrist_dx,
            elbow_shoulder_delta_y,
            "arm landmarks not visible",
        )

    if elbow_shoulder_delta_y > options.max_elbow_shoulder_delta_y:
        return _arm_pose_result(
            "UNKNOWN",
            confidence,
            angle_deg,
            wrist_elbow_delta_y,
            inward_wrist_dx,
            elbow_shoulder_delta_y,
            "elbow too far from shoulder height",
        )

    if abs(wrist_elbow_delta_y) < options.min_wrist_elbow_delta_y:
        return _arm_pose_result(
            "UNKNOWN",
            confidence,
            angle_deg,
            wrist_elbow_delta_y,
            inward_wrist_dx,
            elbow_shoulder_delta_y,
            "wrist too level with elbow",
        )

    if wrist_elbow_delta_y < 0:
        if not (options.min_up_elbow_angle_deg <= angle_deg <= options.max_up_elbow_angle_deg):
            return _arm_pose_result(
                "UNKNOWN",
                confidence,
                angle_deg,
                wrist_elbow_delta_y,
                inward_wrist_dx,
                elbow_shoulder_delta_y,
                "hand-up elbow angle out of range",
            )
        return _arm_pose_result(
            "HAND_UP",
            confidence,
            angle_deg,
            wrist_elbow_delta_y,
            inward_wrist_dx,
            elbow_shoulder_delta_y,
            "hand-up",
        )

    if not (options.min_down_elbow_angle_deg <= angle_deg <= options.max_down_elbow_angle_deg):
        return _arm_pose_result(
            "UNKNOWN",
            confidence,
            angle_deg,
            wrist_elbow_delta_y,
            inward_wrist_dx,
            elbow_shoulder_delta_y,
            "hand-down elbow angle out of range",
        )

    if inward_wrist_dx > options.max_hand_down_inward_wrist_dx:
        return _arm_pose_result(
            "UNKNOWN",
            confidence,
            angle_deg,
            wrist_elbow_delta_y,
            inward_wrist_dx,
            elbow_shoulder_delta_y,
            "hand-down wrist folded inward",
        )

    return _arm_pose_result(
        "HAND_DOWN",
        confidence,
        angle_deg,
        wrist_elbow_delta_y,
        inward_wrist_dx,
        elbow_shoulder_delta_y,
        "hand-down",
    )


def _resolve_torso_reference(
    points: Sequence[Landmark],
    config: GestureConfig,
) -> _TorsoReference | GestureDecision:
    left_shoulder = points[LEFT_SHOULDER]
    right_shoulder = points[RIGHT_SHOULDER]
    shoulder_points = [left_shoulder, right_shoulder]
    if any(point.visibility < config.min_visibility for point in shoulder_points):
        return GestureDecision(Gesture.STOP, _min_visibility(shoulder_points), "shoulder landmarks not visible")

    shoulder_y = (left_shoulder.y + right_shoulder.y) / 2.0
    shoulder_span = abs(right_shoulder.x - left_shoulder.x)
    visible_hips = [points[i] for i in (LEFT_HIP, RIGHT_HIP) if points[i].visibility >= config.min_visibility]
    if len(visible_hips) == 2:
        hip_y = (visible_hips[0].y + visible_hips[1].y) / 2.0
        torso_height = hip_y - shoulder_y
    elif config.allow_partial_torso_reference:
        torso_height = shoulder_span * config.fallback_torso_height_shoulder_ratio
    else:
        return GestureDecision(
            Gesture.STOP,
            _min_visibility([*shoulder_points, points[LEFT_HIP], points[RIGHT_HIP]]),
            "torso landmarks not visible",
        )

    if torso_height < config.min_torso_height:
        return GestureDecision(
            Gesture.STOP,
            _min_visibility([*shoulder_points, *visible_hips]),
            "torso too small or inverted",
        )

    return _TorsoReference(torso_height, shoulder_span)


def _arm_shape_from_evaluation(side: str, evaluation: _ArmPoseEvaluation) -> _ArmShape:
    if evaluation.state == "HAND_UP":
        return _ArmShape(
            Gesture.UP,
            evaluation.confidence,
            side,
            f"{side} elbow-corner hand-up shape angle={evaluation.angle_deg:.0f} dy={evaluation.wrist_elbow_delta_y:+.2f}",
        )

    if evaluation.state == "HAND_DOWN":
        return _ArmShape(
            Gesture.DOWN,
            evaluation.confidence,
            side,
            f"{side} elbow-corner hand-down shape angle={evaluation.angle_deg:.0f} dy={evaluation.wrist_elbow_delta_y:+.2f}",
        )

    return _ArmShape(Gesture.STOP, evaluation.confidence, side, f"{side} {evaluation.reason}")


def _arm_pose_result(
    state: ArmPoseState,
    confidence: float,
    angle_deg: float,
    wrist_elbow_delta_y: float,
    inward_wrist_dx: float,
    elbow_shoulder_delta_y: float,
    reason: str,
) -> _ArmPoseEvaluation:
    return _ArmPoseEvaluation(
        state,
        confidence,
        angle_deg,
        wrist_elbow_delta_y,
        inward_wrist_dx,
        elbow_shoulder_delta_y,
        reason,
    )


def _calculate_inward_wrist_dx(shoulder: Landmark, elbow: Landmark, wrist: Landmark) -> float:
    upper_arm_dx = elbow.x - shoulder.x
    forearm_dx = wrist.x - elbow.x
    if upper_arm_dx > 0:
        return max(0.0, -forearm_dx)
    if upper_arm_dx < 0:
        return max(0.0, forearm_dx)
    return 0.0


def calculate_elbow_angle_degrees(a: Landmark, b: Landmark, c: Landmark) -> float:
    ab_x = a.x - b.x
    ab_y = a.y - b.y
    cb_x = c.x - b.x
    cb_y = c.y - b.y
    ab_len = sqrt(ab_x * ab_x + ab_y * ab_y)
    cb_len = sqrt(cb_x * cb_x + cb_y * cb_y)
    if ab_len == 0 or cb_len == 0:
        return 180.0
    cosine = (ab_x * cb_x + ab_y * cb_y) / (ab_len * cb_len)
    cosine = max(-1.0, min(1.0, cosine))
    return degrees(acos(cosine))


def _min_visibility(points: Sequence[Landmark]) -> float:
    return min((p.visibility for p in points), default=0.0)
