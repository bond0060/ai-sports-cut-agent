"""Original detection helpers from avishah3/AI-Basketball-Shot-Detection-Tracker."""

from __future__ import annotations

import math

import numpy as np


def score(ball_pos: list, hoop_pos: list) -> bool:
    if len(ball_pos) < 1 or len(hoop_pos) < 1:
        return False

    x_vals: list[float] = []
    y_vals: list[float] = []
    rim_height = hoop_pos[-1][0][1] - 0.5 * hoop_pos[-1][3]

    for i in reversed(range(len(ball_pos))):
        if ball_pos[i][0][1] < rim_height:
            x_vals.append(ball_pos[i][0][0])
            y_vals.append(ball_pos[i][0][1])
            if i + 1 < len(ball_pos):
                x_vals.append(ball_pos[i + 1][0][0])
                y_vals.append(ball_pos[i + 1][0][1])
            break

    if len(x_vals) > 1:
        m, b = np.polyfit(x_vals, y_vals, 1)
        predicted_x = (hoop_pos[-1][0][1] - 0.5 * hoop_pos[-1][3] - b) / m
        rim_x1 = hoop_pos[-1][0][0] - 0.4 * hoop_pos[-1][2]
        rim_x2 = hoop_pos[-1][0][0] + 0.4 * hoop_pos[-1][2]
        rebound_zone = 10
        if rim_x1 < predicted_x < rim_x2:
            return True
        if rim_x1 - rebound_zone < predicted_x < rim_x2 + rebound_zone:
            return True

    return False


def detect_down(ball_pos: list, hoop_pos: list) -> bool:
    if len(ball_pos) < 1 or len(hoop_pos) < 1:
        return False
    y = hoop_pos[-1][0][1] + 0.5 * hoop_pos[-1][3]
    return ball_pos[-1][0][1] > y


def detect_up(ball_pos: list, hoop_pos: list) -> bool:
    if len(ball_pos) < 1 or len(hoop_pos) < 1:
        return False

    x1 = hoop_pos[-1][0][0] - 4 * hoop_pos[-1][2]
    x2 = hoop_pos[-1][0][0] + 4 * hoop_pos[-1][2]
    y1 = hoop_pos[-1][0][1] - 2 * hoop_pos[-1][3]
    y2 = hoop_pos[-1][0][1]
    point = ball_pos[-1][0]
    return x1 < point[0] < x2 and y1 < point[1] < y2 - 0.5 * hoop_pos[-1][3]


def in_hoop_region(center, hoop_pos: list) -> bool:
    if len(hoop_pos) < 1:
        return False

    x, y = center
    x1 = hoop_pos[-1][0][0] - 1 * hoop_pos[-1][2]
    x2 = hoop_pos[-1][0][0] + 1 * hoop_pos[-1][2]
    y1 = hoop_pos[-1][0][1] - 1 * hoop_pos[-1][3]
    y2 = hoop_pos[-1][0][1] + 0.5 * hoop_pos[-1][3]
    return x1 < x < x2 and y1 < y < y2


def clean_ball_pos(ball_pos: list, frame_count: int) -> list:
    if len(ball_pos) > 1:
        w1 = ball_pos[-2][2]
        h1 = ball_pos[-2][3]
        w2 = ball_pos[-1][2]
        h2 = ball_pos[-1][3]
        x1 = ball_pos[-2][0][0]
        y1 = ball_pos[-2][0][1]
        x2 = ball_pos[-1][0][0]
        y2 = ball_pos[-1][0][1]
        f_dif = ball_pos[-1][1] - ball_pos[-2][1]
        dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        max_dist = 4 * math.sqrt(w1 ** 2 + h1 ** 2)

        if dist > max_dist and f_dif < 5:
            ball_pos.pop()
        elif (w2 * 1.4 < h2) or (h2 * 1.4 < w2):
            ball_pos.pop()

    if len(ball_pos) > 0 and frame_count - ball_pos[0][1] > 30:
        ball_pos.pop(0)

    return ball_pos


def clean_hoop_pos(hoop_pos: list) -> list:
    if len(hoop_pos) > 1:
        x1 = hoop_pos[-2][0][0]
        y1 = hoop_pos[-2][0][1]
        x2 = hoop_pos[-1][0][0]
        y2 = hoop_pos[-1][0][1]
        w1 = hoop_pos[-2][2]
        h1 = hoop_pos[-2][3]
        w2 = hoop_pos[-1][2]
        h2 = hoop_pos[-1][3]
        f_dif = hoop_pos[-1][1] - hoop_pos[-2][1]
        dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        max_dist = 0.5 * math.sqrt(w1 ** 2 + h1 ** 2)

        if dist > max_dist and f_dif < 5:
            hoop_pos.pop()

        if (w2 * 1.3 < h2) or (h2 * 1.3 < w2):
            hoop_pos.pop()

    if len(hoop_pos) > 25:
        hoop_pos.pop(0)

    return hoop_pos
