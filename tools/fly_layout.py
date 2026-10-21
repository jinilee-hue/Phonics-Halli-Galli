"""시작 화면 카드 6장을 더 크게 놓을 자리 찾기 (vh 단위, x는 화면 가운데 기준).

카드: 3:4, 기울기 ±r(떠다니며 반대로 기울어짐 → |r| 기준), 위로 4vh 떠오름.
피할 것: 로고 · 종 · START · 단계 고르기(+여백), 화면 가장자리, 카드끼리.
화면이 좁은 4:3(반폭 66.67vh)과 넓은 화면(1180×820, 반폭 71.95vh) 두 가지로 따로 풂.
"""
import json
import math

import numpy as np

UI = {  # [x0, y0, x1, y1] — 브라우저에서 잰 값 (여러 화면 크기의 합집합)
    'logo': [-20.7, 4.75, 20.7, 22.25],
    'bell': [-22.6, 32.3, 22.6, 70.2],
    'start': [-15.0, 79.7, 15.0, 94.0],
    'level': [27.3, 86.8, 76.2, 95.5],
}
PAD_UI, PAD_CARD, EDGE, FLOAT = 1.6, 1.4, 1.2, 4.0
# 이름, 쪽(-1 왼쪽, +1 오른쪽), 기준 크기(지금 vh), 기울기, 위/가운데/아래 순서
CARDS = [('bug', -1, 13.0, -14, 0), ('cats', -1, 15.5, 10, 1), ('pig', -1, 17.5, -8, 2),
         ('egg', 1, 12.5, 12, 0), ('pets', 1, 16.0, -14, 1), ('dogs', 1, 17.0, 12, 2)]


def bbox(cx, cy, w, r):
    h = w * 4 / 3
    t = math.radians(abs(r))
    bw = w * math.cos(t) + h * math.sin(t)
    bh = w * math.sin(t) + h * math.cos(t)
    return [cx - bw / 2, cy - bh / 2 - FLOAT, cx + bw / 2, cy + bh / 2]


def ov(a, b, pad):
    return max(0, min(a[2], b[2]) + pad - max(a[0], b[0])) * max(0, min(a[3], b[3]) + pad - max(a[1], b[1]))


def penalty(P, s, half):
    boxes = [bbox(x, y, c[2] * s, c[3]) for (x, y), c in zip(P, CARDS)]
    pen = 0
    for b in boxes:
        pen += max(0, -half + EDGE - b[0]) * 50 + max(0, b[2] - half + EDGE) * 50
        pen += max(0, EDGE - b[1]) * 50 + max(0, b[3] - 100 + EDGE) * 50
        for u in UI.values():
            pen += ov(b, u, PAD_UI)
    for i in range(6):
        for j in range(i + 1, 6):
            pen += ov(boxes[i], boxes[j], PAD_CARD)
    # 위/가운데/아래 순서 유지 (같은 쪽끼리 중심 y) + 보기 좋은 높이(위 18 · 가운데 48 · 아래 80vh) 쪽으로 살짝 당김
    for side in (-1, 1):
        ys = [P[k][1] for k, c in enumerate(CARDS) if c[1] == side]
        pen += max(0, ys[0] - ys[1] + 8) * 5 + max(0, ys[1] - ys[2] + 8) * 5
    soft = sum(0.004 * (P[k][1] - [18, 48, 80][c[4]]) ** 2 for k, c in enumerate(CARDS))
    return pen + (soft if pen > 0 else 0), boxes


def solve(s, half, iters=6000, seed=0):
    rng = np.random.default_rng(seed)
    best = None
    for restart in range(14):
        P = []
        for c in CARDS:
            ylev = [18, 50, 80][c[4]]
            P.append([c[1] * rng.uniform(30, half - 12), ylev + rng.uniform(-6, 6)])
        P = np.array(P, float)
        cur, _ = penalty(P, s, half)
        T = 8.0
        for it in range(iters):
            k = rng.integers(6)
            Q = P.copy()
            Q[k] += rng.normal(0, 2.2, 2)
            Q[k][0] = CARDS[k][1] * abs(Q[k][0])
            p, _ = penalty(Q, s, half)
            if p < cur or rng.random() < math.exp(-(p - cur) / max(T, 1e-6)):
                P, cur = Q, p
            T *= 0.9993
            if cur == 0:
                break
        if best is None or cur < best[0]:
            best = (cur, P.copy())
        if cur == 0:
            break
    return best


def spread_score(P, s, half):
    """여유 공간: 카드와 다른 것 사이 최소 간격(클수록 시원함)"""
    _, boxes = penalty(P, s, half)
    gaps = []
    others = boxes + list(UI.values())
    for i, b in enumerate(boxes):
        for j, o in enumerate(others):
            if j == i:
                continue
            dx = max(o[0] - b[2], b[0] - o[2], 0)
            dy = max(o[1] - b[3], b[1] - o[3], 0)
            gaps.append(math.hypot(dx, dy) if dx > 0 and dy > 0 else max(dx, dy))
    return min(gaps)


def comp_score(P, s, half):
    """보기 좋은 배치 점수: 간격이 넓고, 위/가운데/아래 높이가 목표에 가까울수록 좋음"""
    dev = sum(abs(P[k][1] - [18, 48, 80][c[4]]) for k, c in enumerate(CARDS)) / 6
    return spread_score(P, s, half) - 0.25 * dev


out = {}
for name, half, margin in (('narrow', 66.67, 0.03), ('wide', 71.0, 0.05), ('xwide', 79.0, 0.06)):
    lo, hi, found = 1.0, 1.9, None
    for _ in range(9):                      # 이분 탐색: 들어가는 가장 큰 배율
        mid = (lo + hi) / 2
        pen, P = solve(mid, half)
        if pen == 0:
            lo, found = mid, (mid, P)
        else:
            hi = mid
    s, P = found
    s_use = math.floor((s - margin) * 100) / 100      # 여유를 조금 남김
    cands = []
    for seed in range(16):
        pen, Q = solve(s_use, half, seed=seed)
        if pen == 0:
            cands.append((comp_score(Q, s_use, half), Q))
    sc, Q = max(cands, key=lambda t: t[0])
    print(f'{name}: 반폭 {half}vh → 최대 배율 {s:.3f}, 사용 {s_use} (최소 간격 {spread_score(Q, s_use, half):.1f}vh)')
    res = []
    for (x, y), c in zip(Q, CARDS):
        w = round(c[2] * s_use, 1)
        res.append({'n': c[0], 'x': round(float(x), 1), 'y': round(float(y), 1), 'w': w, 'r': c[3]})
        print(f'   {c[0]:5s} 가운데 x {x:6.1f}vh  y {y:5.1f}vh  폭 {w:5.1f}vh (지금 {c[2]})')
    out[name] = {'scale': s_use, 'cards': res}
json.dump(out, open('/tmp/gl/hg/fly_layout.json', 'w'), indent=1)
