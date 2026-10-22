"""Coco 그림(assets/coco.png)에서 얼굴 조각을 떼어 내 표정 애니메이션용으로 만듭니다 (가운데 종 tools/build_bell_parts.py와 같은 생각).

결과 (원본의 1/2 크기로 저장 — 화면에서 Coco는 20vh 안팎이라 충분)
  assets/coco_parts/still.webp      원본 그대로(가장자리 흰 테만 정리) — 조각을 다 불러오기 전에 보이는 그림
  assets/coco_parts/body.webp       눈 · 입 · 볼터치를 지운 몸통 — 얼굴 창을 둘레 면 색에 맞춘 매끈한 면으로 메움
  assets/coco_parts/eye_l|r.png     눈 흰자 + 둘레 그림자 (눈동자 자리는 흰자로 메움 → 눈동자를 움직여도 비지 않음)
  assets/coco_parts/iris_l|r.png    눈동자
  assets/coco_parts/mouth.png       입
  assets/coco_parts/blush_l|r.png   볼터치 (눈 그림자에 가려진 곳은 타원 모양대로 이어 그림 — 눈을 감으면 보이므로)
  assets/coco_parts/parts.json      조각 위치(원본 픽셀) · 눈 · 입 크기 · 선 색
  src/coco-parts.js                 window.COCO_PARTS (src/coco-face.js가 씀)
몸통 위에 조각을 모두 제자리에 겹치면 원본과 같습니다 ('복원 오차'로 확인). Coco 그림을 바꾸면 다시 돌리세요.

얼굴 창 메우기: 남은 얼굴 면(눈 · 입 · 볼 둘레 밖)에 매끈한 면(3차 다항식 + 창 테두리 쪽 그늘)을 맞추고,
지운 자리 경계에서는 원래 그림과 딱 맞게 차이만 라플라스로 이어 줌 (전에 쓴 바이하모닉은 그림자 · 볼 색을 끌고 들어와 얼룩이 남았음)

실행: /Users/jini/.hermes/bin/uv run --quiet --with pillow --with numpy --with scipy --with scikit-image python tools/build_coco_parts.py
"""
import json
import pathlib
import time

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu
from skimage.measure import find_contours
from skimage.morphology import convex_hull_image, disk

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'assets' / 'coco.png'
OUT = ROOT / 'assets' / 'coco_parts'
JS = ROOT / 'src' / 'coco-parts.js'
DBG = pathlib.Path('/tmp/gl/hg')
SCALE = .5         # 저장 크기 (원본 대비)
SHADOW = 20        # 눈 흰자 바깥으로 그림자까지 지우는 폭 (원본 px)
MOUTH_M = 12       # 입 둘레 (원본 px) — 입 그림자까지
BLUSH_RHO = 2.2    # 볼터치: 반값 타원의 몇 배까지 지울지 (그 밖은 3% 미만)
LUMA = np.array([.299, .587, .114])
t0 = time.time()

src = np.asarray(Image.open(SRC).convert('RGBA')).astype(np.float64) / 255
H0, W0 = src.shape[:2]
H, W = -(-H0 // 4) * 4, -(-W0 // 4) * 4            # 1/2로 줄여도 조각 자리가 딱 맞게 4의 배수로
im = np.zeros((H, W, 4))
im[:H0, :W0] = src
rgb, alpha0 = im[..., :3].copy(), im[..., 3].copy()
op = alpha0 > .99
yy, xx = np.mgrid[0:H, 0:W]
print(f'그림 {W0}×{H0} → 작업 {W}×{H}')


def disc(cx, cy, r):
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r


def fit_circle(px, py):
    A = np.c_[px, py, np.ones_like(px)]
    D, E, F = np.linalg.lstsq(A, -(px ** 2 + py ** 2), rcond=None)[0]
    cx, cy = -D / 2, -E / 2
    return float(cx), float(cy), float(np.sqrt(cx * cx + cy * cy - F))


def harmonic_fill(img, mask):
    """mask 안을 둘레 값에서 가장 매끈하게(라플라스) 이어 메움. img: H×W×C (mask 밖 값은 그대로)"""
    ys, xs = np.nonzero(mask)
    n = len(ys)
    idx = -np.ones(mask.shape, np.int64)
    idx[ys, xs] = np.arange(n)
    rows, cols, vals = [np.arange(n)], [np.arange(n)], []
    diag = np.zeros(n)
    b = np.zeros((n, img.shape[2]))
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        ny, nx = ys + dy, xs + dx
        ok = (ny >= 0) & (ny < mask.shape[0]) & (nx >= 0) & (nx < mask.shape[1])
        nb = np.full(n, -1)
        nb[ok] = idx[ny[ok], nx[ok]]
        diag += ok
        inn, out = ok & (nb >= 0), ok & (nb < 0)
        rows.append(np.nonzero(inn)[0])
        cols.append(nb[inn])
        vals.append(-np.ones(int(inn.sum())))
        b[out] += img[ny[out], nx[out]]
    A = coo_matrix((np.concatenate([diag] + vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tocsc()
    lu = splu(A)
    res = img.copy()
    for c in range(img.shape[2]):
        res[ys, xs, c] = lu.solve(b[:, c])
    return res


def fit_ellipse(x, y):
    D1 = np.vstack([x * x, x * y, y * y]).T
    D2 = np.vstack([x, y, np.ones_like(x)]).T
    S1, S2, S3 = D1.T @ D1, D1.T @ D2, D2.T @ D2
    T = -np.linalg.inv(S3) @ S2.T
    M = np.linalg.inv(np.array([[0, 0, 2], [0, -1, 0], [2, 0, 0]], float)) @ (S1 + S2 @ T)
    _, v = np.linalg.eig(M)
    v = v.real
    a1 = v[:, np.nonzero(4 * v[0] * v[2] - v[1] ** 2 > 0)[0][0]]
    c = np.concatenate([a1, T @ a1])
    return c if c[0] > 0 else -c


def ellipse_rho(c):
    A, B, C, D, E, F = c
    x0, y0 = np.linalg.solve([[2 * A, B], [B, 2 * C]], [-D, -E])
    q0 = A * x0 * x0 + B * x0 * y0 + C * y0 * y0 + D * x0 + E * y0 + F
    dx, dy = xx - x0, yy - y0
    return np.sqrt(np.maximum(A * dx * dx + B * dx * dy + C * dy * dy, 0) / -q0), (float(x0), float(y0))


def decompose(target, base, core, reg):
    """target = α·조각색 + (1-α)·base 가 되게 조각(색, α)을 뗌. core 안은 α=1, reg 밖은 α=0"""
    D = target - base
    inner = ndi.binary_erosion(core, iterations=1)
    _, (jy, jx) = ndi.distance_transform_edt(~inner, return_indices=True)
    V = target[jy, jx] - base
    a = np.clip((D * V).sum(-1) / np.maximum((V * V).sum(-1), 1e-6), 0, 1)
    lo = np.where(D > 0, D / np.maximum(1 - base, 1e-6), np.where(D < 0, -D / np.maximum(base, 1e-6), 0)).max(-1)
    a = np.clip(np.maximum(a, lo), 0, 1)
    a[inner] = 1
    a[~reg] = 0
    col = np.clip(np.where(a[..., None] > 0, base + D / np.maximum(a[..., None], 1e-6), 0), 0, 1)
    return col, a


def over(base, col, a):
    return a[..., None] * col + (1 - a[..., None]) * base


# ── 0) 가장자리 흰 테: 반투명 가장자리 색이 원래 배경(흰색)에 물들어 있음 → 가장 가까운 안쪽 색으로
edge = (alpha0 > 0) & ~op
_, (iy, ix) = ndi.distance_transform_edt(~op, return_indices=True)
l0 = rgb @ LUMA
print(f'가장자리 {int(edge.sum())}px: 안쪽보다 {float((l0[edge] - l0[iy, ix][edge]).mean()):+.3f} 밝음 → 안쪽 색으로 정리')
rgb[edge] = rgb[iy[edge], ix[edge]]
still = rgb.copy()
lum = rgb @ LUMA
mx_, mn_ = rgb.max(-1), rgb.min(-1)
sat = (mx_ - mn_) / np.maximum(mx_, 1e-6)
bg = rgb[..., 2] / np.maximum(rgb[..., 1], 1e-6)          # 얼굴 면 1.02~1.08 · 몸통 · 테두리 1.13 이상

# ── 1) 얼굴 창: 파랑/초록이 낮은 밝은 면 중 가운데 덩어리 → 볼록 껍질 (둥근 네모라 볼록)
facec = op & (bg < 1.10) & (lum > .45)
lab, n = ndi.label(facec)
sz = ndi.sum(facec, lab, np.arange(1, n + 1))
cands = []
for i in np.argsort(sz)[::-1][:6]:
    m = lab == i + 1
    ys, xs = np.nonzero(m)
    cands.append((float(np.hypot(xs.mean() - .5 * W0, ys.mean() - .56 * H0)), m))
cands.sort(key=lambda c: c[0])
pale_main = ndi.binary_fill_holes(ndi.binary_opening(cands[0][1], structure=disk(2)))


def set_window(extra=None):
    """얼굴 창 = 밝은 얼굴 면(+ 볼터치 타원)의 볼록 껍질.
    오른쪽 볼은 그늘져 '밝은 면'에서 빠지고 창 테두리에 붙어 있어 구멍 메우기로도 안 채워짐 → 볼을 찾은 뒤 넣어서 다시 만듦"""
    global win, interior, wd, cxw, cyw, sw, sh, UU, VV
    win = convex_hull_image(pale_main if extra is None else pale_main | extra)
    interior = ndi.binary_erosion(win, iterations=2)
    wd = ndi.distance_transform_edt(win)
    ys, xs = np.nonzero(win)
    cxw, cyw, sw, sh = xs.mean(), ys.mean(), np.ptp(xs) / 2, np.ptp(ys) / 2
    UU, VV = (xx - cxw) / sw, (yy - cyw) / sh
    print(f'얼굴 창: x {xs.min()}–{xs.max()} · y {ys.min()}–{ys.max()} ({int(win.sum())}px)')


set_window()

# ── 2) 눈동자: 얼굴 창 안의 진한 갈색 덩어리 2개
dark = op & win & (lum < .42) & (rgb[..., 0] < .5)
lab, n = ndi.label(dark)
sz = ndi.sum(dark, lab, np.arange(1, n + 1))
big = [i + 1 for i in np.argsort(sz)[::-1][:2] if sz[i] > 1500]
assert len(big) == 2, f'눈동자를 2개 못 찾음: {sorted(sz)[-4:]}'
irises = sorted((ndi.binary_fill_holes(lab == i) for i in big), key=lambda m: np.nonzero(m)[1].mean())

# ── 3) 눈 흰자: 눈동자 중심에서 바깥으로 가며 '흰 정도(밝기 − 채도)'가 가장 가파르게 떨어지는 곳 = 흰자 바깥 테 → 원 맞춤
wv = ndi.gaussian_filter(lum - 1.6 * sat, 1.0)
eyes = []
for m in irises:
    ys, xs = np.nonzero(m)
    icx, icy = float(xs.mean()), float(ys.mean())
    ir = float(np.sqrt(m.sum() / np.pi))
    rs = np.arange(ir + 3, ir + 34, .5)
    pts = []
    for ang in np.deg2rad(np.arange(0, 360, 3)):
        px_, py_ = icx + rs * np.cos(ang), icy + rs * np.sin(ang)
        d = np.gradient(ndi.map_coordinates(wv, [py_, px_], order=1), rs)
        k = int(np.argmin(d))
        if d[k] < -.012:
            pts.append((px_[k], py_[k]))
    pts = np.array(pts)
    keep = np.ones(len(pts), bool)
    for _ in range(6):
        cx, cy, R = fit_circle(pts[keep, 0], pts[keep, 1])
        res = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - R
        keep = np.abs(res) < max(2.0, 2.2 * float(res[keep].std()))
    eyes.append(dict(cx=cx, cy=cy, r=R, icx=icx, icy=icy, ir=ir, iris=m))
    print(f'눈: 흰자 중심 ({cx:.1f}, {cy:.1f}) 반지름 {R:.1f} (맞춘 점 {keep.sum()}/{len(pts)}, 어긋남 {res[keep].std():.1f}px) · '
          f'눈동자 ({icx:.1f}, {icy:.1f}) 반지름 {ir:.1f}')

# ── 4) 입: 두 눈 사이 아래의 진한 덩어리
box = (xx > .44 * W0) & (xx < .57 * W0) & (yy > .555 * H0) & (yy < .63 * H0)
mm = op & box & (lum < .5)
lab, n = ndi.label(mm)
assert n, '입을 못 찾음'
sz = ndi.sum(mm, lab, np.arange(1, n + 1))
mouth = ndi.binary_fill_holes(lab == int(np.argmax(sz)) + 1)
mys, mxs = np.nonzero(mouth)
assert eyes[0]['cx'] < mxs.mean() < eyes[1]['cx'] and mys.mean() > eyes[0]['cy'], '입이 두 눈 사이 아래에 있지 않음'
colsum = mouth.sum(0)
stroke = float(np.median(colsum[colsum > 0]))
print(f'입: 중심 ({mxs.mean():.0f}, {mys.mean():.0f}) 폭 {np.ptp(mxs) + 1} · 선 굵기 {stroke:.0f}px')
def set_regions():
    global mouth_reg, eye_reg, eye_any
    mouth_reg = ndi.binary_dilation(mouth, iterations=MOUTH_M) & interior
    eye_reg = [disc(e['cx'], e['cy'], e['r'] + SHADOW) & interior & ~mouth_reg for e in eyes]
    eye_any = eye_reg[0] | eye_reg[1]


set_regions()

# ── 5) 얼굴 면 모형: 3차 다항식 + 창 테두리에서의 거리에 따른 그늘 (테두리 쪽이 어둡고 붉어지는 것)


def design(mask):
    u, v, d = UU[mask], VV[mask], wd[mask]
    cols = [u ** i * v ** j for i in range(4) for j in range(4 - i)]
    for t in (3., 8., 20.):
        e = np.exp(-d / t)
        cols += [e, e * u, e * v]
    return np.stack(cols, 1)


def fit_face(K):
    X, Y = design(K), rgb[K]
    keep = np.ones(len(X), bool)
    for _ in range(3):
        coef = np.linalg.lstsq(X[keep], Y[keep], rcond=None)[0]
        res = Y - X @ coef
        s = np.sqrt((res[keep] ** 2).mean(0))
        keep = (np.abs(res) < 3 * s).all(1)
    M = np.zeros_like(rgb)
    M[win] = design(win) @ coef
    return M, s * 255, keep.mean()


def find_blush(e, side, M, init=None):
    """얼굴 면보다 붉은(r−g) 정도에 '타원 + 부드러운 가장자리' 모양을 맞춤 (눈 그림자 · 입 둘레 · 창 테두리 쪽은 빼고).
    가장자리 반값(진하기 절반)이 rho=1. 볼 일부가 눈 그림자에 가려져도 보이는 부분만으로 모양을 맞춤.
    init: 처음 값 [cx, cy, log a, log b, θ, 세기, log 가장자리] — 오른쪽 볼은 왼쪽 볼을 좌우로 뒤집은 모양에서 시작
    (오른쪽은 얼굴이 그늘져 볼과 둘레 색 차이가 작아서, 혼자 찾으면 엉뚱한 곳을 잡음)"""
    from scipy.optimize import least_squares
    red_ex = np.where(interior, (rgb[..., 0] - rgb[..., 1]) - (M[..., 0] - M[..., 1]), 0)
    zone = interior & ~mouth_reg & (yy > e['cy'] + 10) & ((xx < e['cx'] + 30) if side < 0 else (xx > e['cx'] - 30))
    vis = zone & ~eye_any & (wd > 4)
    if init is None:
        sm_ = ndi.gaussian_filter(red_ex, 1.0)
        pk = float(np.percentile(sm_[vis], 99.5))
        assert pk > .02, f'볼터치가 둘레보다 붉지 않음 (세기 {pk:.3f})'
        top = vis & (sm_ > pk * .5)
        lb, nb = ndi.label(top)
        top = lb == int(np.argmax(ndi.sum(top, lb, np.arange(1, nb + 1)))) + 1
        ys, xs = np.nonzero(top)
        r0 = max(12., float(np.sqrt(top.sum() / np.pi)))
        p0 = [xs.mean(), ys.mean(), np.log(r0), np.log(r0), 0., pk, np.log(6.)]
    else:
        p0 = list(init)
        r0 = float(np.exp(max(p0[2], p0[3])))
    box_ = vis & (np.abs(xx - p0[0]) < r0 * 3.2) & (np.abs(yy - p0[1]) < r0 * 3.2)
    py, px = np.nonzero(box_)
    val = red_ex[py, px]

    def model(p, x, y):
        cx, cy, la, lb_, th, A, lk = p
        c, s = np.cos(th), np.sin(th)
        u, v = ((x - cx) * c + (y - cy) * s) / np.exp(la), (-(x - cx) * s + (y - cy) * c) / np.exp(lb_)
        return A / (1 + np.exp(np.exp(lk) * (np.sqrt(u * u + v * v) - 1)))

    fit = least_squares(lambda p: model(p, px, py) - val, p0, loss='soft_l1', f_scale=.02)
    p = fit.x
    if init is not None:                           # 왼쪽 볼과 너무 달라지면 → 모양은 왼쪽 그대로, 자리 · 세기만 맞춤
        bad = (abs(p[0] - p0[0]) > 25 or abs(p[1] - p0[1]) > 25 or not (.6 < np.exp(p[2] - p0[2]) < 1.6)
               or not (.6 < np.exp(p[3] - p0[3]) < 1.6) or p[5] < .02)
        if bad:
            f2 = least_squares(lambda q: model([q[0], q[1], p0[2], p0[3], p0[4], q[2], p0[6]], px, py) - val,
                               [p0[0], p0[1], p0[5]], loss='soft_l1', f_scale=.02)
            p = [f2.x[0], f2.x[1], p0[2], p0[3], p0[4], f2.x[2], p0[6]]
            fit = f2
            print('  (오른쪽 볼: 혼자 맞춘 모양이 왼쪽과 많이 달라서, 왼쪽 볼 모양을 뒤집어 씀)')
    cx, cy, la, lb_, th, A, lk = p
    c, s = np.cos(th), np.sin(th)
    u, v = ((xx - cx) * c + (yy - cy) * s) / np.exp(la), (-(xx - cx) * s + (yy - cy) * c) / np.exp(lb_)
    rho = np.sqrt(u * u + v * v)
    hid = float(((rho <= 1) & ~vis).sum() / max((rho <= 1).sum(), 1))
    k_ = float(np.exp(lk))
    # 지울 범위: 모형 값이 1/300 아래로 떨어지는 곳 + 5px (볼터치 가장자리 번짐까지)
    rmax = max(1.3, 1 + np.log(max(float(A), .01) / .003) / k_ + 5 / min(np.exp(la), np.exp(lb_)))
    return dict(rho=rho, cx=float(cx), cy=float(cy), peak=float(A), a=float(np.exp(la)), b=float(np.exp(lb_)), k=k_, rmax=float(rmax),
                th=float(th), la=float(la), lb=float(lb_), lk=float(lk), hid=hid, rmse=float(np.sqrt((fit.fun ** 2).mean())))


MID = (eyes[0]['cx'] + eyes[1]['cx']) / 2              # 얼굴 가운데 세로선 (오른쪽 볼 = 왼쪽 볼을 여기서 뒤집은 자리)


def mirror(b):
    return [2 * MID - b['cx'], b['cy'], b['la'], b['lb'], -b['th'], b['peak'], b['lk']]


K0 = interior & ~eye_any & ~mouth_reg
M0, s0, k0 = fit_face(K0)
print(f'얼굴 면 맞춤 1차: 남는 차이 RGB {np.round(s0, 2)} /255 (쓴 점 {k0:.0%})')
bl = find_blush(eyes[0], -1, M0)
blushes = [bl, find_blush(eyes[1], 1, M0, init=mirror(bl))]
# 얼굴 창 다시: 볼터치 타원(눈에 보이는 가장자리 rho 1.15까지)을 넣어 볼록 껍질 → 그늘진 오른쪽 볼도 얼굴 창 안으로
set_window((blushes[0]['rho'] <= 1.15) | (blushes[1]['rho'] <= 1.15))
set_regions()
K0 = interior & ~eye_any & ~mouth_reg
M1, s1, k1 = fit_face(K0 & ~(blushes[0]['rho'] <= blushes[0]['rmax'] + .3) & ~(blushes[1]['rho'] <= blushes[1]['rmax'] + .3))
print(f'얼굴 면 맞춤 2차 (두 볼 자리 뺌): 남는 차이 RGB {np.round(s1, 2)} /255 (쓴 점 {k1:.0%})')
bl = find_blush(eyes[0], -1, M1)
blushes = [bl, find_blush(eyes[1], 1, M1, init=mirror(bl))]
blush_sup = [(b['rho'] <= b['rmax']) & interior for b in blushes]
for nm, b in zip(('blush_l', 'blush_r'), blushes):
    print(f'{nm}: 중심 ({b["cx"]:.0f}, {b["cy"]:.0f}) · 반지름 {b["a"]:.0f}×{b["b"]:.0f} · 가장자리 {b["k"]:.1f} · 세기 {b["peak"]:.3f} · '
          f'가려진 몫 {b["hid"]:.0%} · 지울 범위 {b["rmax"]:.2f}배 · 맞춤 오차 {b["rmse"]:.3f}')
    assert 15 < b['a'] < 80 and 15 < b['b'] < 80 and abs(b['cx'] - MID) < 260, f'{nm} 모양이 이상함'

# ── 6) 몸통: 지울 자리 = 눈(그림자까지) · 입 · 볼터치. 면 모형 + 경계에서 원래 그림과 딱 맞게 차이만 라플라스로 이음
U = (eye_any | mouth_reg | blush_sup[0] | blush_sup[1]) & interior
ring = ndi.binary_dilation(U, iterations=2) & ~U & interior
resL = ((rgb - M1) @ LUMA)[ring] * 255
print(f'지울 자리 {int(U.sum())}px · 그 둘레에서 면 모형과 차이(밝기): 1%={np.percentile(resL, 1):.1f} 99%={np.percentile(resL, 99):.1f} /255')
ys, xs = np.nonzero(U)
y0, y1, x0, x1 = ys.min() - 4, ys.max() + 5, xs.min() - 4, xs.max() + 5
Uc = U[y0:y1, x0:x1]
Rf = harmonic_fill((rgb - M1)[y0:y1, x0:x1], Uc)
body = rgb.copy()
sub = body[y0:y1, x0:x1]
sub[Uc] = np.clip(M1[y0:y1, x0:x1][Uc] + Rf[Uc], 0, 1)
print(f'몸통 메움 끝 {time.time() - t0:.0f}s')
# 메운 자리가 둘레 얼굴 면만큼 매끈한지 (자잘한 얼룩 = 높은 주파수 성분)
hpL = (body - ndi.gaussian_filter(body, (4, 4, 0))) @ LUMA * 255
refm = K0 & ~ndi.binary_dilation(U, iterations=6) & (wd > 12)
print(f'메운 자리 결: 99%={np.percentile(np.abs(hpL[U & (wd > 12)]), 99):.2f} · 둘레 얼굴 면 99%={np.percentile(np.abs(hpL[refm]), 99):.2f} /255')

# ── 7) 조각: 아래부터 볼터치 → 눈 → 입. 바로 아래 층을 바탕으로 떼어 냄
layers = {}
base = body.copy()
for nm, b, sup in zip(('blush_l', 'blush_r'), blushes, blush_sup):
    vis = sup & ~eye_any & ~mouth_reg
    col, a = decompose(rgb, body, vis & (b['rho'] <= .45), vis)
    hid = sup & ~vis
    # 눈 그림자에 가려진 곳: 보이는 곳의 '타원 거리 → 진하기'를 그대로 이어 쓰고, 색은 보이는 볼터치 색을 부드럽게 이어 붙임
    eg = np.linspace(0, b['rmax'], 23)
    mid = (eg[1:] + eg[:-1]) / 2
    prof = []
    for lo_, hi_ in zip(eg[:-1], eg[1:]):
        sel = vis & (b['rho'] >= lo_) & (b['rho'] < hi_)
        prof.append(np.median(a[sel]) if sel.sum() > 20 else np.nan)
    prof = np.array(prof)
    good = ~np.isnan(prof)
    prof = np.minimum.accumulate(np.clip(np.interp(mid, mid[good], prof[good]), 0, 1))
    a[hid] = np.interp(b['rho'][hid], mid, prof, right=0)
    w = (vis & (a > .25)).astype(float)
    num = np.stack([ndi.gaussian_filter(col[..., c] * w, 8) for c in range(3)], -1)
    den = ndi.gaussian_filter(w, 8)[..., None]
    fillc = np.where(den > 1e-3, num / np.maximum(den, 1e-6), np.median(col[w > 0], 0))
    col[hid] = fillc[hid]
    col[a <= 0] = 0
    layers[nm] = (col, a)
    base = over(base, col, a)
    print(f'{nm}: 눈 그림자 · 입 둘레에 가려진 {int(hid.sum())}px를 타원 모양대로 이어 그림')
for k, e in enumerate(eyes):
    nm = ('eye_l', 'eye_r')[k]
    core = disc(e['cx'], e['cy'], e['r'] - 1.5) & eye_reg[k]
    col, a = decompose(rgb, base, core, eye_reg[k])
    base = over(base, col, a)
    # 눈동자 테두리: 눈동자 중심에서 바깥으로 가며 '어두움 → 흰자'로 가장 가파르게 밝아지는 바깥쪽 자리 → 원 맞춤
    # (눈동자 안 반짝임 · 위쪽의 밝은 테 때문에 어둠 기준 덩어리는 위가 패여 있어, 그대로 쓰면 눈동자를 옮길 때 흰자에 자국이 남음)
    rs = np.arange(e['ir'] * .75, e['ir'] * 1.45, .5)
    pts = []
    for ang in np.deg2rad(np.arange(0, 360, 3)):
        px_, py_ = e['icx'] + rs * np.cos(ang), e['icy'] + rs * np.sin(ang)
        d = np.gradient(ndi.map_coordinates(wv, [py_, px_], order=1), rs)
        strong = np.nonzero(d > d.max() * .5)[0]
        if len(strong) and d.max() > .02:
            j = strong[-1]
            while j + 1 < len(d) and d[j + 1] > d[j]:
                j += 1
            pts.append((px_[j], py_[j]))
    pts = np.array(pts)
    keep = np.ones(len(pts), bool)
    for _ in range(6):
        icx, icy, irf = fit_circle(pts[keep, 0], pts[keep, 1])
        res = np.hypot(pts[:, 0] - icx, pts[:, 1] - icy) - irf
        keep = np.abs(res) < max(1.5, 2.2 * float(res[keep].std()))
    e.update(icx=icx, icy=icy, ir=irf)
    ireg = disc(icx, icy, irf + 3.5) & core
    wcol = harmonic_fill(col, ireg)                       # 눈동자 자리 = 둘레 흰자에서 매끈하게
    icol, ia = decompose(col, wcol, disc(icx, icy, irf - 1.2) & core, ireg)
    layers[nm] = (wcol, a)
    layers[nm.replace('eye', 'iris')] = (icol, ia)
    print(f'{nm}: 눈동자 원 ({icx:.1f}, {icy:.1f}) 반지름 {irf:.1f} (맞춘 점 {keep.sum()}/{len(pts)}, 어긋남 {res[keep].std():.1f}px) — '
          f'흰자+눈동자 = 원래 눈, 오차 최대 {np.abs(over(wcol, icol, ia) - col)[core].max() * 255:.2f}/255')
col, a = decompose(rgb, base, mouth, mouth_reg)
layers['mouth'] = (col, a)
base = over(base, col, a)
print(f'복원 오차(몸통 + 조각 = 원본): 최대 {np.abs(base - rgb).max(-1)[op].max() * 255:.2f}/255')

# ── 8) 저장 (1/2 크기 · 곱한 알파로 줄여 가장자리 색 번짐 없이)
OUT.mkdir(exist_ok=True)
for f in list(OUT.glob('*.png')) + list(OUT.glob('*.webp')):
    f.unlink()


def save(name, col, a, bx=None, fmt='png'):
    if bx is None:
        ys, xs = np.nonzero(a > 1 / 255)
        bx = (int(xs.min()) // 4 * 4, int(ys.min()) // 4 * 4, -(-(int(xs.max()) + 1) // 4) * 4, -(-(int(ys.max()) + 1) // 4) * 4)
    X0, Y0, X1, Y1 = (int(v) for v in bx)
    rgba = np.dstack([np.where(a[..., None] > 0, col, 0), a])[Y0:Y1, X0:X1]
    img = Image.fromarray((np.clip(rgba, 0, 1) * 255 + .5).astype(np.uint8), 'RGBA')
    img = img.convert('RGBa').resize((round((X1 - X0) * SCALE), round((Y1 - Y0) * SCALE)), Image.LANCZOS).convert('RGBA')
    fname = f'{name}.{fmt}'
    if fmt == 'webp':
        img.save(OUT / fname, 'WEBP', quality=92, method=6, alpha_quality=100)
    else:
        img.save(OUT / fname, optimize=True)
    return dict(file=fname, x=X0, y=Y0, w=X1 - X0, h=Y1 - Y0)


feat = rgb[mouth & (lum < .3)]
ink = '#%02x%02x%02x' % tuple((np.median(feat, 0) * 255).round().astype(int))
meta = {'W': W, 'H': H, 'scale': SCALE, 'stroke': round(stroke, 1), 'ink': ink}
meta['still'] = save('still', still, alpha0, (0, 0, W, H), 'webp')
meta['body'] = save('body', body, alpha0, (0, 0, W, H), 'webp')
for k, e in enumerate(eyes):
    s = 'lr'[k]
    meta[f'eye_{s}'] = {**save(f'eye_{s}', *layers[f'eye_{s}']), 'cx': round(e['cx'], 1), 'cy': round(e['cy'], 1), 'r': round(e['r'], 1)}
    meta[f'iris_{s}'] = {**save(f'iris_{s}', *layers[f'iris_{s}']), 'cx': round(e['icx'], 1), 'cy': round(e['icy'], 1),
                         'r': round(e['ir'], 1)}
for k, b in enumerate(blushes):
    s = 'lr'[k]
    meta[f'blush_{s}'] = {**save(f'blush_{s}', *layers[f'blush_{s}']), 'cx': round(b['cx'], 1), 'cy': round(b['cy'], 1)}
meta['mouth'] = {**save('mouth', *layers['mouth']), 'cx': round(float(mxs.mean()), 1), 'cy': round(float(mys.mean()), 1),
                 'core': [int(mxs.min()), int(mys.min()), int(mxs.max()), int(mys.max())]}
(OUT / 'parts.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
JS.write_text('// tools/build_coco_parts.py 가 만든 파일입니다 — Coco 얼굴 조각 위치(원본 픽셀)와 눈 · 입 크기 · 선 색.\n'
              f'window.COCO_PARTS = {json.dumps(meta)};\n', encoding='utf-8')
print('파일:', ', '.join(f'{f.name} {f.stat().st_size // 1024}KB' for f in sorted(OUT.iterdir()) if f.suffix != '.json'))

# ── 확인용 (3×2): 원본 | 몸통(얼굴 지움) | 눈 감을 때 바탕(몸통+볼+입) / 오른쪽 아래를 봄(눈동자 이동) | 경계선 | 몸통 결 확대(×8)
DBG.mkdir(parents=True, exist_ok=True)
bgc = np.array([90, 175, 190]) / 255
fy0, fy1, fx0, fx1 = 470, 800, 270, 800


def comp(names, shift=(0, 0)):
    out = body.copy()
    for nm in names:
        c, a = layers[nm]
        if nm.startswith('iris'):
            c, a = np.roll(c, shift, axis=(0, 1)), np.roll(a, shift, axis=(0, 1))
        out = over(out, c, a)
    return out


ov = still.copy()
eye_disc = disc(eyes[0]['cx'], eyes[0]['cy'], eyes[0]['r']) | disc(eyes[1]['cx'], eyes[1]['cy'], eyes[1]['r'])
for m, c in ((win, (0, 1, 0)), (U, (1, 1, 0)), (eye_disc, (0, 1, 1)), ((blushes[0]['rho'] <= 1) | (blushes[1]['rho'] <= 1), (1, 0, 1))):
    ov[m & ~ndi.binary_erosion(m)] = c
hp = np.clip(.5 + (body - ndi.gaussian_filter(body, (5, 5, 0))) * 8, 0, 1)
views = [still, body, comp(('blush_l', 'blush_r', 'mouth')),
         comp(('blush_l', 'blush_r', 'eye_l', 'eye_r', 'iris_l', 'iris_r', 'mouth'), shift=(4, 8)), ov, hp]
tiles = [Image.fromarray(((v * alpha0[..., None] + bgc * (1 - alpha0[..., None]))[fy0:fy1, fx0:fx1] * 255 + .5)
                         .clip(0, 255).astype(np.uint8)) for v in views]
tw, th = tiles[0].size
sheet = Image.new('RGB', (tw * 3 + 12, th * 2 + 6), 'black')
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % 3) * (tw + 6), (i // 3) * (th + 6)))
sheet.save(DBG / 'coco_parts_sheet.png')
print(f'확인용 {DBG / "coco_parts_sheet.png"} · 끝 {time.time() - t0:.0f}s')
