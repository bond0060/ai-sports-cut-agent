import math
import numpy as np
import torch

HOOP_ROI_X_SCALE = 3.0
HOOP_ROI_Y_SCALE = 3.0
HOOP_ROI_UP_EXTRA = 2.0


def get_device():
    if torch.cuda.is_available():
        device = 'cuda'
    elif torch.backends.mps.is_available():
        device = 'mps'
    else:
        device = 'cpu'
    return device


def normalize_roi(roi, frame_width=None, frame_height=None):
    """Validate and normalize ROI to (x1, y1, x2, y2) integers."""
    if roi is None:
        return None

    x1, y1, x2, y2 = [int(round(v)) for v in roi]
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1

    if frame_width is not None:
        x1 = max(0, min(x1, frame_width - 1))
        x2 = max(0, min(x2, frame_width - 1))
    if frame_height is not None:
        y1 = max(0, min(y1, frame_height - 1))
        y2 = max(0, min(y2, frame_height - 1))

    if x2 <= x1 and frame_width is not None:
        x2 = min(frame_width - 1, x1 + 20)
    if y2 <= y1 and frame_height is not None:
        y2 = min(frame_height - 1, y1 + 20)

    if x2 - x1 < 20 or y2 - y1 < 20:
        raise ValueError("ROI too small")

    return (x1, y1, x2, y2)


def get_hoop_roi(hoop_pos):
    if len(hoop_pos) < 1:
        return None

    cx, cy = hoop_pos[-1][0]
    w, h = hoop_pos[-1][2], hoop_pos[-1][3]
    half_w = HOOP_ROI_X_SCALE * w / 2
    half_h = HOOP_ROI_Y_SCALE * h / 2
    up_extra = HOOP_ROI_UP_EXTRA * h
    # Align auto ROI bottom with current net ROI bottom: rim_bottom + 0.20 * h.
    roi_bottom = cy + 0.7 * h

    return (
        int(cx - half_w),
        int(cy - half_h - up_extra),
        int(cx + half_w),
        int(roi_bottom),
    )


def get_active_roi(hoop_pos, custom_roi=None):
    if custom_roi is not None:
        return custom_roi
    return get_hoop_roi(hoop_pos)


def get_rim_bounds(hoop_pos):
    cx, cy = hoop_pos[-1][0]
    w, h = hoop_pos[-1][2], hoop_pos[-1][3]
    rim_y = cy - 0.5 * h
    rim_bottom = cy + 0.5 * h
    rim_x1 = cx - 0.4 * w
    rim_x2 = cx + 0.4 * w
    return rim_y, rim_x1, rim_x2, rim_bottom


def in_active_roi(point, hoop_pos=None, custom_roi=None):
    roi = get_active_roi(hoop_pos, custom_roi)
    if roi is None:
        return False

    x1, y1, x2, y2 = roi
    x, y = point
    return x1 <= x <= x2 and y1 <= y <= y2


def get_ball_track_zone(
    hoop_pos,
    custom_roi=None,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> tuple[int, int, int, int] | None:
    """Wider zone for ball detection than strict ROI (covers side-angle shots)."""
    roi = get_active_roi(hoop_pos, custom_roi)
    if roi is None:
        return None

    x1, y1, x2, y2 = roi
    if len(hoop_pos) > 0:
        cx = hoop_pos[-1][0][0]
        w = hoop_pos[-1][2]
        x1 = min(x1, int(cx - 2.8 * w))
        x2 = max(x2, int(cx + 2.8 * w))
    else:
        pad_x = int(0.25 * (x2 - x1))
        x1 -= pad_x
        x2 += pad_x

    if frame_width is not None:
        x1 = max(0, x1)
        x2 = min(frame_width - 1, x2)
    if frame_height is not None:
        y1 = max(0, y1)
        y2 = min(frame_height - 1, y2)

    return (x1, y1, x2, y2)


def in_ball_track_zone(
    point,
    hoop_pos=None,
    custom_roi=None,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> bool:
    zone = get_ball_track_zone(hoop_pos, custom_roi, frame_width, frame_height)
    if zone is None:
        return False
    x1, y1, x2, y2 = zone
    x, y = point
    return x1 <= x <= x2 and y1 <= y <= y2


def in_hoop_roi(point, hoop_pos):
    return in_active_roi(point, hoop_pos=hoop_pos, custom_roi=None)


def in_hoop_region(center, hoop_pos):
    if len(hoop_pos) < 1:
        return False

    x, y = center
    x1 = hoop_pos[-1][0][0] - 1 * hoop_pos[-1][2]
    x2 = hoop_pos[-1][0][0] + 1 * hoop_pos[-1][2]
    y1 = hoop_pos[-1][0][1] - 1 * hoop_pos[-1][3]
    y2 = hoop_pos[-1][0][1] + 0.5 * hoop_pos[-1][3]

    return x1 < x < x2 and y1 < y < y2


def filter_ball_pos_by_roi(ball_pos, hoop_pos=None, custom_roi=None):
    if custom_roi is None and (hoop_pos is None or len(hoop_pos) < 1):
        return ball_pos
    return [
        point
        for point in ball_pos
        if in_active_roi(point[0], hoop_pos=hoop_pos, custom_roi=custom_roi)
    ]


def filter_ball_pos_for_tracking(
    ball_pos,
    hoop_pos=None,
    custom_roi=None,
    frame_width: int | None = None,
    frame_height: int | None = None,
):
    if custom_roi is None and (hoop_pos is None or len(hoop_pos) < 1):
        return ball_pos
    return [
        point
        for point in ball_pos
        if in_ball_track_zone(
            point[0],
            hoop_pos=hoop_pos,
            custom_roi=custom_roi,
            frame_width=frame_width,
            frame_height=frame_height,
        )
    ]


def get_up_frame_index(
    ball_pos,
    hoop_pos,
    custom_roi=None,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> int | None:
    """Frame index of the earliest point in the upper shot arc, if any."""
    if len(ball_pos) < 1:
        return None

    roi = get_active_roi(hoop_pos, custom_roi)
    if roi is None:
        return None

    x1, y1, x2, y2 = roi
    rim_y = None
    if len(hoop_pos) > 0:
        rim_y, _, _, _ = get_rim_bounds(hoop_pos)

    up_frame = None
    for point in ball_pos:
        x, y = point[0]
        if not in_ball_track_zone(
            (x, y),
            hoop_pos=hoop_pos,
            custom_roi=custom_roi,
            frame_width=frame_width,
            frame_height=frame_height,
        ):
            continue
        if rim_y is None:
            upper_bound = y1 + 0.5 * (y2 - y1)
            in_upper = y1 <= y <= upper_bound
        else:
            in_upper = y1 <= y <= rim_y
        if in_upper:
            up_frame = point[1] if up_frame is None else min(up_frame, point[1])

    return up_frame


def had_up_phase(
    ball_pos,
    hoop_pos,
    custom_roi=None,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> bool:
    return (
        get_up_frame_index(
            ball_pos, hoop_pos, custom_roi, frame_width, frame_height
        )
        is not None
    )


def score(ball_pos, hoop_pos, custom_roi=None):
    if len(ball_pos) < 1 or len(hoop_pos) < 1:
        return False

    rim_y, rim_x1, rim_x2, _ = get_rim_bounds(hoop_pos)
    roi_points = filter_ball_pos_by_roi(ball_pos, hoop_pos, custom_roi)
    if len(roi_points) < 1:
        return False

    for point in roi_points:
        x, y = point[0]
        if y >= rim_y and rim_x1 <= x <= rim_x2:
            return True

    x_vals = []
    y_vals = []
    for i in reversed(range(len(roi_points))):
        if roi_points[i][0][1] < rim_y:
            x_vals.append(roi_points[i][0][0])
            y_vals.append(roi_points[i][0][1])
            if i + 1 < len(roi_points):
                x_vals.append(roi_points[i + 1][0][0])
                y_vals.append(roi_points[i + 1][0][1])
            break

    if len(x_vals) > 1 and x_vals[0] != x_vals[1]:
        m, b = np.polyfit(x_vals, y_vals, 1)
        if m != 0:
            predicted_x = (rim_y - b) / m
            rebound_zone = 10
            if rim_x1 <= predicted_x <= rim_x2:
                return True
            if rim_x1 - rebound_zone <= predicted_x <= rim_x2 + rebound_zone:
                return True

    return False


def detect_down(
    ball_pos,
    hoop_pos,
    custom_roi=None,
    frame_width: int | None = None,
    frame_height: int | None = None,
):
    if len(ball_pos) < 1:
        return False

    point = ball_pos[-1][0]
    if not in_ball_track_zone(
        point,
        hoop_pos=hoop_pos,
        custom_roi=custom_roi,
        frame_width=frame_width,
        frame_height=frame_height,
    ):
        return False

    if len(hoop_pos) < 1:
        roi = get_active_roi(hoop_pos, custom_roi)
        if roi is None:
            return False
        _, y1, _, y2 = roi
        return point[1] > y1 + 0.65 * (y2 - y1)

    _, _, _, rim_bottom = get_rim_bounds(hoop_pos)
    return point[1] > rim_bottom


def detect_rim_rebound(ball_pos, hoop_pos, custom_roi=None, lookback: int = 8):
    """True when recent ball motion suggests a bounce off the rim plane."""
    if len(ball_pos) < 4 or len(hoop_pos) < 1:
        return False

    rim_y, rim_x1, rim_x2, _ = get_rim_bounds(hoop_pos)
    roi_points = filter_ball_pos_by_roi(ball_pos, hoop_pos, custom_roi)
    if len(roi_points) < 4:
        return False

    recent = roi_points[-lookback:]
    ys = [p[0][1] for p in recent]
    xs = [p[0][0] for p in recent]

    crossed_rim_band = any(
        rim_y - 15 <= y <= rim_y + 35 and rim_x1 - 20 <= x <= rim_x2 + 20
        for x, y in zip(xs, ys)
    )
    if not crossed_rim_band:
        return False

    # Upward jerk after being near rim: classic miss bounce.
    if len(ys) >= 3 and ys[-1] < ys[-2] < ys[-3]:
        return True

    # Horizontal deflection near rim with insufficient drop-through.
    if len(xs) >= 3 and len(ys) >= 3:
        x_span = max(xs[-3:]) - min(xs[-3:])
        y_drop = ys[-1] - min(ys[-3:])
        if x_span > 25 and y_drop < 20 and ys[-1] <= rim_y + 25:
            return True

    return False


def detect_up(
    ball_pos,
    hoop_pos,
    custom_roi=None,
    frame_width: int | None = None,
    frame_height: int | None = None,
):
    if len(ball_pos) < 1:
        return False

    point = ball_pos[-1][0]
    roi = get_active_roi(hoop_pos, custom_roi)
    if roi is None or not in_ball_track_zone(
        point,
        hoop_pos=hoop_pos,
        custom_roi=custom_roi,
        frame_width=frame_width,
        frame_height=frame_height,
    ):
        return False

    x1, y1, x2, y2 = roi
    if len(hoop_pos) < 1:
        upper_bound = y1 + 0.45 * (y2 - y1)
        return y1 <= point[1] <= upper_bound

    rim_y, _, _, _ = get_rim_bounds(hoop_pos)
    return y1 <= point[1] <= rim_y


def clean_ball_pos(
    ball_pos,
    frame_count,
    hoop_pos=None,
    custom_roi=None,
    frame_width: int | None = None,
    frame_height: int | None = None,
):
    if len(ball_pos) > 1:
        w1 = ball_pos[-2][2]
        h1 = ball_pos[-2][3]
        w2 = ball_pos[-1][2]
        h2 = ball_pos[-1][3]

        x1 = ball_pos[-2][0][0]
        y1 = ball_pos[-2][0][1]
        x2 = ball_pos[-1][0][0]
        y2 = ball_pos[-1][0][1]

        f1 = ball_pos[-2][1]
        f2 = ball_pos[-1][1]
        f_dif = f2 - f1

        dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        max_dist = 4 * math.sqrt((w1) ** 2 + (h1) ** 2)

        if (dist > max_dist) and (f_dif < 5):
            ball_pos.pop()
        elif (w2 * 1.4 < h2) or (h2 * 1.4 < w2):
            ball_pos.pop()

    if len(ball_pos) > 0 and frame_count - ball_pos[0][1] > 30:
        ball_pos.pop(0)

    return filter_ball_pos_for_tracking(
        ball_pos,
        hoop_pos,
        custom_roi,
        frame_width=frame_width,
        frame_height=frame_height,
    )


def clean_hoop_pos(hoop_pos, custom_roi=None):
    if custom_roi is not None:
        hoop_pos = [
            point
            for point in hoop_pos
            if in_active_roi(point[0], custom_roi=custom_roi)
        ]

    if len(hoop_pos) > 1:
        x1 = hoop_pos[-2][0][0]
        y1 = hoop_pos[-2][0][1]
        x2 = hoop_pos[-1][0][0]
        y2 = hoop_pos[-1][0][1]

        w1 = hoop_pos[-2][2]
        h1 = hoop_pos[-2][3]
        w2 = hoop_pos[-1][2]
        h2 = hoop_pos[-1][3]

        f1 = hoop_pos[-2][1]
        f2 = hoop_pos[-1][1]
        f_dif = f2 - f1

        dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        max_dist = 0.5 * math.sqrt(w1 ** 2 + h1 ** 2)

        if dist > max_dist and f_dif < 5:
            hoop_pos.pop()

        if (w2 * 1.3 < h2) or (h2 * 1.3 < w2):
            hoop_pos.pop()

    if len(hoop_pos) > 25:
        hoop_pos.pop(0)

    return hoop_pos
