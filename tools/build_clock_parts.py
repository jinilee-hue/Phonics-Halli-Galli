"""HUD 시계 그림(assets/time_icon.png)을 조각내 바늘 2개가 따로 돌 수 있게 만듭니다.

결과 (가로세로 절반 크기 — 화면에선 10vh 남짓이라 충분)
  assets/clock_parts/body.png         바늘 · 바늘 그림자 · 가운데 단추를 지운 시계 (테두리 · 판 · 꼭지 그대로)
                                      시계 밖에 구워진 회백색 그림자도 지움 — 그림자는 upgrade.css의 drop-shadow로
  assets/clock_parts/hand_blue.png    파란 화살 바늘 — 주황 바늘 · 단추에 가렸던 뿌리 쪽은 깨끗한 단면을 이어 그림
  assets/clock_parts/hand_orange.png  주황 바늘 — 단추에 가렸던 뿌리 쪽은 깨끗한 단면을 이어 그림
  assets/clock_parts/cap.png          가운데 단추 (바늘 위에 얹힘)
  src/clock-parts.js                  window.CLOCK_PARTS — 크기 · 회전 중심(단추 중심) · 바늘 처음 각도 (src/clock.js가 씀)
바늘은 축이 단추 중심을 지나게 옮겨 두어, 단추 중심을 축으로 돌리면 제자리에서 돕니다.
바늘 가장자리는 원래 그림의 그림자 섞인 테두리를 버리고 안쪽 색 + 새 매끈한 테두리로 만듭니다 (돌려도 검은 테가 안 생김).
그림자는 CSS로 늘 같은 방향에 다시 그립니다. 원본의 투명 구멍(배경 지울 때 같이 지워진 반사광)은 저장된 색으로 되살립니다.

실행: /Users/jini/.hermes/bin/uv run --quiet --with pillow --with numpy --with scipy --with scikit-image python tools/build_clock_parts.py
"""
import json
import pathlib

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage.restoration import inpaint_biharmonic

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'assets' / 'time_icon.png'
OUT = ROOT / 'assets' / 'clock_parts'
JS = ROOT / 'src' / 'clock-parts.js'
DBG = pathlib.Path('/tmp/gl/hg')
SCALE = .5
LUMA = np.array([0.299, 0.587, 0.114])
rng = np.random.default_rng(3)

im = np.asarray(Image.open(SRC).convert('RGBA')).astype(np.float64) / 255
H, W = im.shape[:2]
rgb, a = im[..., :3].copy(), im[..., 3].copy()
yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
grow = lambda m, k: ndi.binary_dilation(m, iterations=k)
shrink = lambda m, k: ndi.binary_erosion(m, iterations=k)

# ── 0) 투명 구멍 되살리기
solid = shrink(ndi.binary_fill_holes(a > .97), 4)
holes = solid & (a < .999)
a[holes] = 1
lum = rgb @ LUMA
r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
mx, mn = rgb.max(-1), rgb.min(-1)
sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
hue = (np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) + 360) % 360
print(f'투명 구멍 되살림 {int(holes.sum())}px')


def biggest(m):
    lab, n = ndi.label(m)
    if n == 0:
        raise SystemExit('조각을 못 찾음')
    return ndi.binary_fill_holes(lab == np.argmax(ndi.sum(m, lab, range(1, n + 1))) + 1)


def unit(v):
    return v / np.linalg.norm(v)


def ang_of(d):                                     # 시계 방향 각도, 위 = 0°
    return float(np.degrees(np.arctan2(d[0], -d[1])) % 360)


# ── 1) 판 · 바늘
face = biggest((a > .9) & (mx > .85) & (sat < .25))
fy, fx = np.nonzero(face)
fcx, fcy, frad = fx.mean(), fy.mean(), np.sqrt(face.sum() / np.pi)
blue0 = biggest(face & (sat > .3) & (hue > 185) & (hue < 265))
orange0 = biggest(face & (sat > .58) & ((hue < 50) | (hue > 345)) & (r > .78))   # .35면 바늘 밑 갈색 그림자 가장자리까지 먹음
hands0 = blue0 | orange0
blue = ndi.binary_fill_holes(ndi.binary_closing(blue0, iterations=2) & ~orange0)   # 반사광 구멍 자리 작은 홈 메움
orange = ndi.binary_fill_holes(ndi.binary_closing(orange0, iterations=2))
print(f'판 중심 ({fcx:.0f}, {fcy:.0f}) 반지름 {frad:.0f} | 파랑 {int(blue.sum())}px · 주황 {int(orange.sum())}px')

# ── 2) 가운데 단추: 바늘에 안 걸린 둘레에서 밝기 변화가 가장 큰 원
Lg = ndi.gaussian_filter(lum, 1.2)
gm = np.hypot(ndi.sobel(Lg, 1), ndi.sobel(Lg, 0))
near_h = grow(hands0, 4).astype(float)
th = np.radians(np.arange(0, 360, 2))


def circ_score(cx, cy, R):
    px, py = cx + R * np.sin(th), cy - R * np.cos(th)
    ok = ndi.map_coordinates(near_h, [py, px], order=0) < .5
    return ndi.map_coordinates(gm, [py, px], order=1)[ok].mean() if ok.sum() >= len(th) * .3 else -1


ys, xs = np.nonzero(hands0)
seed = np.array([np.percentile(xs, 3), np.percentile(ys, 97)])   # 두 바늘 뿌리 쪽 (왼쪽 아래)
best = (-1, 0, 0, 0)
for cy in np.arange(seed[1] - 70, seed[1] + 71, 2.0):
    for cx in np.arange(seed[0] - 30, seed[0] + 91, 2.0):
        for R in np.arange(30, 66, 1.0):
            v = circ_score(cx, cy, R)
            if v > best[0]:
                best = (v, cx, cy, R)
for _ in range(2):
    _, bx, by, bR = best
    for cy in np.arange(by - 2, by + 2.01, .5):
        for cx in np.arange(bx - 2, bx + 2.01, .5):
            for R in np.arange(bR - 1.5, bR + 1.51, .25):
                v = circ_score(cx, cy, R)
                if v > best[0]:
                    best = (v, cx, cy, R)
_, pcx, pcy, R = best
pivot = np.array([pcx, pcy])
dist_p = np.hypot(xx - pcx, yy - pcy)
print(f'단추: 중심 ({pcx:.1f}, {pcy:.1f}) 반지름 {R:.2f}')


# ── 3) 바늘 축 · 단면
def frame_of(d, p):
    n = np.array([-d[1], d[0]])
    o = p + np.dot(pivot - p, d) * d               # 단추 중심을 축에 내린 점 (s = 0)
    rel = np.stack([xx - o[0], yy - o[1]], -1)
    return d, n, o, rel @ d, rel @ n


def sections(m, s, u, s_from, s_to, step=3):
    out = []
    for k in np.arange(s_from, s_to, step):
        band = m & (s >= k) & (s < k + step)
        if band.sum() > 3:
            out.append((k + step / 2, u[band].min(), u[band].max(), band))
    return out


# 파랑: 주황에 안 가린 곧은 대의 가운데 선
d0 = unit(np.array(np.nonzero(blue0)[::-1], dtype=float).mean(1) - pivot)
_, n0, _, s0, u0 = frame_of(d0, pivot)
touch_o = grow(biggest(face & (sat > .35) & ((hue < 50) | (hue > 345)) & (r > .7)), 3)   # 주황 + 그 그림자에 닿은 단면은 빼고
sec = [(s, lo, hi) for s, lo, hi, bd in sections(blue0, s0, u0, R, 330) if not (bd & touch_o).any()]
w0 = sec[0][2] - sec[0][1]
shaft = []
for s, lo, hi in sec:
    if abs((hi - lo) - w0) > w0 * .08:
        break
    shaft.append((s, lo, hi))
assert len(shaft) >= 4, f'파랑 곧은 대 단면이 너무 적음: {len(shaft)}'
S = np.array([q[0] for q in shaft])
C = np.array([(q[1] + q[2]) / 2 for q in shaft])
c1, c0 = np.polyfit(S, C, 1)
dB = unit(d0 + c1 * n0)
pB = pivot + S.mean() * d0 + (c0 + c1 * S.mean()) * n0
dB, nB, oB, sB, uB = frame_of(dB, pB)
s_refB = np.dot(pivot + S.min() * d0 - oB, dB) + 3
print(f'파랑: 방향 {ang_of(dB):.1f}° · 곧은 대 폭 {w0:.0f}px · 깨끗한 단면 s={s_refB:.0f} · 축과 단추 중심 거리 {np.dot(pivot - pB, nB):+.1f}px')

# 주황: 단추 밖 부분의 주성분 축
ys, xs = np.nonzero(orange0 & (dist_p > R + 6))
pts = np.stack([xs, ys], 1).astype(float)
pO = pts.mean(0)
w, v = np.linalg.eigh(np.cov((pts - pO).T))
dO = v[:, np.argmax(w)]
dO = dO if np.dot(dO, pO - pivot) > 0 else -dO
dO, nO, oO, sO, uO = frame_of(dO, pO)
s_refO = R + 14
print(f'주황: 방향 {ang_of(dO):.1f}° · 깨끗한 단면 s={s_refO:.0f} · 축과 단추 중심 거리 {np.dot(pivot - pO, nO):+.1f}px')

# ── 4) 몸통: 바늘 · 바늘 그림자 · 단추 자리를 판 색으로 (매끈한 판 모델 + 둘레에서 이어 받은 차이)
d_hands = ndi.distance_transform_edt(~hands0)
d_rim = ndi.distance_transform_edt(face)
X, Y = (xx - fcx) / frad, (yy - fcy) / frad


def basis(x, y, dr):
    """판 색 모델: 매끈한 3차 면 + 테두리 안쪽 그늘(테두리에서 멀어질수록 옅어짐, 위아래 · 좌우로 세기가 다름)"""
    poly = [np.ones_like(x), x, y, x * x, x * y, y * y, x ** 3, x * x * y, x * y * y, y ** 3]
    rim = []
    for k in (5., 12., 28.):
        e = np.exp(-dr / k)
        rim += [e, e * x, e * y]
    return np.stack(poly + rim, -1)


fitm = face & (d_hands > 45) & (dist_p > R + 18) & (d_rim > 1.5) & ~grow(holes, 8)
coef = np.linalg.lstsq(basis(X[fitm], Y[fitm], d_rim[fitm]), rgb[fitm], rcond=None)[0]
model = basis(X, Y, d_rim) @ coef
shadow = face & (d_hands < 60) & ((model @ LUMA) - lum > .008)
# 바늘 둘레에 비친 색(파랑 · 분홍 반사)도 지움 — 남기면 메울 때 번져 얼룩이 됨
tint = face & (d_hands < 90) & (np.abs(rgb - model).max(-1) > .018) & (d_rim > 6)
hole = grow(hands0, 4) | shadow | tint | (dist_p < R + 4)
hole = ndi.binary_fill_holes(ndi.binary_closing(grow(hole, 2), iterations=3)) & face & (d_rim > 1.5)
# 메우기: 판 색 모델 + 둘레(지우지 않은 판)와의 작은 차이만 가장자리에서 10px 안쪽으로 옅게 이어 받음
known = face & ~hole & (d_rim > 1.5)
dk, (ky, kx) = ndi.distance_transform_edt(~known, return_indices=True)
resid = rgb - model
body = rgb.copy()
body[hole] = np.clip(model + resid[ky, kx] * np.exp(-dk / 10)[..., None], 0, 1)[hole]
hp = lum - ndi.gaussian_filter(lum, 1.5)
grain = 1.4826 * np.median(np.abs(hp[fitm] - np.median(hp[fitm])))
noise = rng.standard_normal((H, W))
noise -= ndi.gaussian_filter(noise, 1.5)
body = np.clip(body + (noise * grain / noise.std() * np.clip(ndi.distance_transform_edt(hole) / 4, 0, 1))[..., None], 0, 1)
edge = grow(hole, 2) & known
print(f'판 모델 오차 {(np.abs(model[fitm] - rgb[fitm]).mean(0) * 255).round(2)}/255 · 메운 자리 둘레 차이 {np.abs(resid[edge]).mean() * 255:.2f}/255 · 바늘 그림자 {int(shadow.sum())}px · 메운 자리 {int(hole.sum())}px')


# ── 5) 바늘 조각: 안쪽 색(테두리 2px 안쪽에서 가져옴) + 새 매끈한 테두리, 뿌리는 깨끗한 단면을 이어 그림
def hand(core0, d, n, o, s, u, s_ref):
    sec_m = core0 & (np.abs(s - s_ref) < 1.5)
    lo, hi = u[sec_m].min(), u[sec_m].max()
    root = (s >= 0) & (s < s_ref) & (u >= lo) & (u <= hi)
    core = (core0 & ~((s < s_ref) & (s > -R))) | root            # 뿌리 쪽(단추 ~ 단면)은 단면 모양으로 새로
    inner = shrink(core0, 2)
    _, (jy, jx) = ndi.distance_transform_edt(~inner, return_indices=True)
    col = rgb[jy, jx]
    m = root
    sx = o[0] + s_ref * d[0] + u[m] * n[0]
    sy = o[1] + s_ref * d[1] + u[m] * n[1]
    for ch in range(3):
        col[..., ch][m] = ndi.map_coordinates(col[..., ch], [sy, sx], order=1)
    din = ndi.distance_transform_edt(core)
    dout = ndi.distance_transform_edt(~core)
    al = np.clip(ndi.gaussian_filter(din - dout, 1.0) + .5, 0, 1)   # 매끈한 테두리 (계단 없이)
    return col, al, (lo, hi)


colB, alB, wB = hand(blue, dB, nB, oB, sB, uB, s_refB)
colO, alO, wO = hand(orange, dO, nO, oO, sO, uO, s_refO)
print(f'뿌리 단면 폭: 파랑 {wB[1] - wB[0]:.0f}px · 주황 {wO[1] - wO[0]:.0f}px (단추 지름 {2 * R:.0f}px)')


def shift(col, al, v):                                          # 축이 단추 중심을 지나게 옮김
    sh = (v[1], v[0])
    return np.stack([ndi.shift(col[..., ch], sh, order=1, mode='nearest') for ch in range(3)], -1), ndi.shift(al, sh, order=1)


offB = np.dot(pivot - oB, nB) * nB
offO = np.dot(pivot - oO, nO) * nO
colB, alB = shift(colB, alB, offB)
colO, alO = shift(colO, alO, offO)

# ── 6) 가운데 단추 (가장자리 색은 조금 안쪽에서 — 바늘 색이 안 섞이게)
Rc = R + .5
angm = np.arctan2(yy - pcy, xx - pcx)
rin = np.minimum(dist_p, Rc - 3.5)
colC = np.stack([ndi.map_coordinates(rgb[..., ch], [pcy + rin * np.sin(angm), pcx + rin * np.cos(angm)], order=1) for ch in range(3)], -1)
alC = np.clip((Rc - dist_p) / 1.6 + .5, 0, 1)


def over(dst, col, al):
    return al[..., None] * col + (1 - al[..., None]) * dst


def rot(col, al, deg):                                          # 단추 중심을 축으로 시계 방향 deg
    t = np.radians(deg)
    c, s_ = np.cos(t), np.sin(t)
    dx, dy = xx - pcx, yy - pcy
    sx, sy = pcx + c * dx + s_ * dy, pcy - s_ * dx + c * dy
    return np.stack([ndi.map_coordinates(col[..., ch], [sy, sx], order=1) for ch in range(3)], -1), ndi.map_coordinates(al, [sy, sx], order=1)


def compose(db=0, do=0):
    cb, ab = rot(colB, alB, db)
    co, ao = rot(colO, alO, do)
    return over(over(over(body, cb, ab), co, ao), colC, alC)


views = [rgb, compose(), body] + [compose(p, q) for p, q in ((90, 150), (200, 40), (300, 260))]
bgc = np.array([1, 1, 1.0])
tiles = [Image.fromarray(((v * a[..., None] + bgc * (1 - a[..., None])) * 255 + .5).astype(np.uint8)).resize((W // 3, H // 3), Image.LANCZOS) for v in views]
sheet = Image.new('RGB', (W // 3 * len(tiles) + 6 * (len(tiles) - 1), H // 3), 'black')
for i, tl in enumerate(tiles):
    sheet.paste(tl, (i * (W // 3 + 6), 0))
sheet.save(DBG / 'ck_sheet.png')
Image.fromarray(((compose(120, 210) * a[..., None] + bgc * (1 - a[..., None])) * 255 + .5).astype(np.uint8)).crop((100, 150, 720, 760)).save(DBG / 'ck_zoom.png')
Image.fromarray(((body * a[..., None] + bgc * (1 - a[..., None])) * 255 + .5).astype(np.uint8)).crop((100, 150, 720, 760)).save(DBG / 'ck_body.png')

# ── 6.5) 바깥의 뿌연 회백색 그림자 걷어 내기
#   원본 그림은 흰 바탕에 맞춘 그림자가 '반투명 회백색'으로 구워져 있어서, 분홍 · 하늘색 배경 위에서는
#   시계 아래 · 오른쪽에 흰 박스처럼 떠 보임 → 시계 몸 밖은 투명하게, 그림자는 CSS drop-shadow로 새로 그림
#   시계 몸 = 빨간 테두리 + 노란 꼭지(채도 높음)를 메운 모양. 회백색 그림자는 채도가 낮아 여기서 빠짐
#   (0단계에서 그림자 일부가 '구멍'으로 잡혀 불투명해졌으므로, 알파가 아니라 색으로 몸을 정함)
rimk = (im[..., 3] > .5) & (sat > .3) & (r > .55)
rimk = ndi.binary_closing(rimk, iterations=3)
lab, n = ndi.label(rimk)
sizes_ = ndi.sum(rimk, lab, range(1, n + 1))
keep = [i + 1 for i, s_ in enumerate(sizes_) if s_ > 2000]          # 테두리 고리 + 꼭지 (작은 부스러기는 버림)
sil = ndi.binary_fill_holes(np.isin(lab, keep))
d_out = ndi.distance_transform_edt(~sil)
halo = ~sil & (im[..., 3] > .02)
a_body = np.where(sil, a, im[..., 3] * np.clip(1.0 - d_out, 0, 1))  # 테두리 밖 1px만 원래 가장자리 알파
print(f'바깥 회백색 기운 {int(halo.sum())}px 지움 (색 중앙값 {(np.median(rgb[halo], 0) * 255).round().tolist()}, '
      f'원래 알파 중앙값 {np.median(im[..., 3][halo]):.2f}) · 시계 몸 {int(sil.sum())}px · 테두리 조각 {len(keep)}개')

# ── 7) 저장 (절반 크기 · 미리 곱한 알파로 줄여 테두리가 어두워지지 않게)
OUT.mkdir(exist_ok=True)
for f in OUT.glob('*.png'):
    f.unlink()
w2, h2 = round(W * SCALE), round(H * SCALE)


def save(name, col, al):
    img = Image.fromarray((np.dstack([col, al]) * 255 + .5).astype(np.uint8), 'RGBA')
    img.convert('RGBa').resize((w2, h2), Image.LANCZOS).convert('RGBA').save(OUT / f'{name}.png', optimize=True)
    return (OUT / f'{name}.png').stat().st_size


sizes = {'body': save('body', body, a_body), 'hand_blue': save('hand_blue', colB, alB),
         'hand_orange': save('hand_orange', colO, alO), 'cap': save('cap', colC, alC)}
meta = {'W': w2, 'H': h2, 'pivot': [round(pcx * SCALE, 2), round(pcy * SCALE, 2)], 'capR': round(Rc * SCALE, 2),
        'base': {'blue': round(ang_of(dB), 1), 'orange': round(ang_of(dO), 1)}}
JS.write_text('// tools/build_clock_parts.py 가 만든 파일입니다 — HUD 시계 조각 크기 · 회전 중심 · 바늘 처음 각도(시계 방향, 위 = 0°).\n'
              f'window.CLOCK_PARTS = {json.dumps(meta)};\n', encoding='utf-8')
print('저장:', {k: f'{v // 1024}KB' for k, v in sizes.items()}, json.dumps(meta))
