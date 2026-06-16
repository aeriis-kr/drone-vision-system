"""Adapters from YOLO pose output to receiver motion landmarks."""

from __future__ import annotations

from typing import Any

from vision_rx.motion.types import Landmark

BLAZEPOSE_LANDMARK_COUNT = 33
COCO_TO_BLAZEPOSE = {5: 11, 6: 12, 7: 13, 8: 14, 9: 15, 10: 16, 11: 23, 12: 24}


def landmarks_from_yolo_pose_result(result: Any) -> tuple[tuple[Landmark, ...], ...]:
    """Convert Ultralytics COCO-17 pose keypoints into BlazePose-indexed landmarks."""

    keypoints = getattr(result, "keypoints", None)
    if keypoints is None:
        return ()

    xyn = getattr(keypoints, "xyn", None)
    if xyn is None:
        return ()

    xyn_people = _tolist(xyn)
    conf_value = getattr(keypoints, "conf", None)
    conf_people = _tolist(conf_value) if conf_value is not None else None

    poses: list[tuple[Landmark, ...]] = []
    for person_i, person_points in enumerate(xyn_people):
        if person_points is None:
            continue

        points = _tolist(person_points)
        landmarks = [Landmark(0.0, 0.0, 0.0) for _ in range(BLAZEPOSE_LANDMARK_COUNT)]
        person_conf = _person_confidence(conf_people, person_i)

        for coco_i, blaze_i in COCO_TO_BLAZEPOSE.items():
            if coco_i >= len(points):
                continue

            xy = _tolist(points[coco_i])
            if len(xy) < 2:
                continue

            visibility = 1.0
            if person_conf is not None and coco_i < len(person_conf):
                visibility = float(person_conf[coco_i])

            landmarks[blaze_i] = Landmark(x=float(xy[0]), y=float(xy[1]), visibility=visibility)

        poses.append(tuple(landmarks))

    return tuple(poses)


def _person_confidence(conf_people: list[Any] | None, person_i: int) -> list[Any] | None:
    if conf_people is None or person_i >= len(conf_people):
        return None
    person_conf = conf_people[person_i]
    if person_conf is None:
        return None
    return _tolist(person_conf)


def _tolist(value: Any) -> list[Any]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        result = value.tolist()
        return result if isinstance(result, list) else [result]
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]
