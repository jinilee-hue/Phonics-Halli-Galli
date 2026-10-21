"""종 그림(assets/bell.png)에서 얼굴 조각(눈 2 · 입 · 볼터치 2)을 떼어 내 표정 애니메이션용으로 만듭니다.

결과
  assets/bell_parts/body.png       얼굴을 모두 지운 종 몸통 (눈 · 입 · 볼터치와 그 둘레 그림자까지 지우고 노란 면을 매끈하게 메움)
  assets/bell_parts/<조각>.png     eye_l · eye_r · mouth · blush_l · blush_r — 원래 그림 그대로 (반투명 가장자리 · 그림자까지)
  assets/bell_parts/parts.json     조각 위치(원본 픽셀) · 입 선 굵기 · 선 색
  src/bell-parts.js                window.BELL_PARTS (src/bell-face.js가 씀)
몸통 위에 조각을 모두 제자리에 겹치면 원본과 똑같습니다 (아래 '복원 오차'로 확인).
눈을 감으면 눈 조각만 숨기므로, 몸통은 볼터치 둘레까지 깨끗해야 얼룩이 안 남아요 → 볼터치도 따로 떼어 냅니다.
종 그림을 바꾸면 이 스크립트를 다시 돌리세요.

실행: /Users/jini/.hermes/bin/uv run --quiet --with pillow --with numpy --with scipy --with scikit-image python tools/build_bell_parts.py
"""
import json
import pathlib
import time

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage.restoration import inpaint_biharmonic

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'assets' / 'bell.png'
OUT = ROOT / 'assets' / 'bell_parts'
JS = ROOT / 'src' / 'bell-parts.js'
DBG = pathlib.Path('/tmp/gl/hg')
FEATS = ('eye_l', 'eye_r', 'mouth', 'blush_l', 'blush_r')
rng = np.random.default_rng(7)
t0 = time.time()

im = np.asarray(Image.open(SRC).convert('RGBA')).astype(np.float64) / 255
H, W = im.shape[:2]
rgb, alpha0 = im[..., :3], im[..., 3]
LUMA = np.array([0.299, 0.587, 0.114])
lum = rgb @ LUMA
r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
yy = np.mgrid[0:H, 0:W][0]
unit = np.sqrt(W * H) / 1270            # 예전 종(1221×1076) 기준 거리 → 이 그림 크기로
core = {}

# ── 1) 눈 · 입: 얼굴 높이(위에서 30~62%)의 노랗지 않은 어두운 덩어리
#    (눈 아래쪽은 밝은 갈색이라 lum<.55까지, 눈 속 흰 반짝임은 구멍 메우기로 포함)
yellowish = (r > .78) & (g > .55) & (b < .5)
dark = (alpha0 > .5) & (lum < .55) & ~yellowish
lab, n = ndi.label(dark)
sizes = ndi.sum(dark, lab, np.arange(1, n + 1))
cands = []
for i in np.nonzero(sizes >= 1500)[0] + 1:
    m = lab == i
    ys, xs = np.nonzero(m)
    cy, cx = ys.mean(), xs.mean()
    if .30 * H < cy < .62 * H and .2 * W < cx < .8 * W and m.sum() < .03 * W * H:
        cands.append((int(m.sum()), cx, cy, m))
cands.sort(key=lambda t: -t[0])
assert len(cands) >= 3, f'눈 · 입을 못 찾음: {[(c[0], round(c[1]), round(c[2])) for c in cands]}'
eyes = sorted(cands[:2], key=lambda t: t[1])
mouth = cands[2]
assert mouth[2] > max(eyes[0][2], eyes[1][2]) and eyes[0][1] < mouth[1] < eyes[1][1], '입이 두 눈 사이 아래에 있지 않음'
core['eye_l'], core['eye_r'], core['mouth'] = (ndi.binary_fill_holes(c[3]) for c in (eyes[0], eyes[1], mouth))

# ── 2) 볼터치: 얼굴 높이의 분홍 덩어리 중 큰 것 2개
#    (분홍은 파랑 성분이 초록만큼 높아 갈색 · 노랑과 구별됨. 아래 빨간 받침 반사광은 높이로 뺌. 오른쪽 볼은 그늘이라 조금 어두움)
pinkish = (alpha0 > .5) & (r > .7) & (r - g > .18) & (b > g * .9) & (b > .40) & (yy > .40 * H) & (yy < .65 * H)
lb, nb = ndi.label(pinkish)
bsz = ndi.sum(pinkish, lb, np.arange(1, nb + 1))
keep = [i + 1 for i in np.argsort(bsz)[::-1][:2] if bsz[i] > 1500 * unit * unit]
assert len(keep) == 2, f'볼터치를 2개 못 찾음: {sorted(bsz)[-4:]}'
core['blush_l'], core['blush_r'] = sorted((ndi.binary_fill_holes(lb == i) for i in keep), key=lambda m: np.nonzero(m)[1].mean())
for k in FEATS:
    ys, xs = np.nonzero(core[k])
    print(f'{k}: 중심 ({xs.mean():.0f}, {ys.mean():.0f}) 크기 {np.ptp(xs) + 1}×{np.ptp(ys) + 1}')

# ── 3) 다시 칠할 자리: 눈 · 입 둘레(그림자까지) + 볼터치 둘레(번짐까지). 이 바깥 경계가 깨끗한 노란 면이어야 얼룩이 안 남음
dist = {k: ndi.distance_transform_edt(~core[k]) for k in FEATS}
d_face = np.minimum.reduce([dist['eye_l'], dist['eye_r'], dist['mouth']])
d_blush = np.minimum(dist['blush_l'], dist['blush_r'])
U = ndi.binary_fill_holes(((d_face < 46 * unit) | (d_blush < 24 * unit)) & (alpha0 > .99))
ring = ndi.binary_dilation(U, iterations=3) & ~U & (alpha0 > .99)
known = (~U & (alpha0 > .99)).astype(float)
sm = ndi.gaussian_filter(lum * known, 14) / np.maximum(ndi.gaussian_filter(known, 14), 1e-6)
dv = (lum - sm)[ring] * 255
print(f'경계 밝기 튐(0에 가까울수록 깨끗): 1%={np.percentile(dv, 1):.1f} 99%={np.percentile(dv, 99):.1f} /255')

# ── 4) 몸통: 칠할 자리를 경계에서 매끈하게 이어 메우고(바이하모닉), 노란 면 결(그레인)을 같은 세기로
ys, xs = np.nonzero(U)
pad = int(24 * unit)
y0, y1, x0, x1 = max(0, ys.min() - pad), min(H, ys.max() + pad + 1), max(0, xs.min() - pad), min(W, xs.max() + pad + 1)
Uc = U[y0:y1, x0:x1]
print(f'메울 자리 {int(U.sum())}px (상자 {x1 - x0}×{y1 - y0}) 메우는 중…', flush=True)
filled = inpaint_biharmonic(rgb[y0:y1, x0:x1].copy(), Uc, channel_axis=-1)
print(f'  메움 끝 {time.time() - t0:.0f}s', flush=True)
body = rgb.copy()
body[y0:y1, x0:x1][Uc] = np.clip(filled, 0, 1)[Uc]
hp = lum - ndi.gaussian_filter(lum, 1.5)
band = (yy > .30 * H) & (yy < .65 * H)
yellow = (alpha0 > .99) & band & ~ndi.binary_dilation(U, iterations=8) & (lum > .6) & yellowish
grain = 1.4826 * np.median(np.abs(hp[yellow] - np.median(hp[yellow])))
noise = rng.standard_normal((H, W))
noise -= ndi.gaussian_filter(noise, 1.5)
noise *= grain / noise.std()
feather = np.clip(ndi.distance_transform_edt(U) / 4, 0, 1)
tint = rgb[yellow].mean(0) / rgb[yellow].mean()
body = np.clip(body + (noise * feather)[..., None] * tint, 0, 1)
print(f'노란 면 결 세기 {grain * 255:.2f}/255')

# ── 5) 조각: 원본 = α·조각색 + (1-α)·몸통. 칠한 자리를 가까운 조각에 나눠 줌
#    볼터치는 10px 덜 가깝게 쳐서 눈 그림자는 눈 조각으로 (눈 감으면 그림자도 같이 사라지게).
#    단, 볼터치 그림 자체(+가장자리 3px)는 늘 볼터치 조각.
score = np.stack([dist['eye_l'], dist['eye_r'], dist['mouth'], dist['blush_l'] + 10 * unit, dist['blush_r'] + 10 * unit])
own = np.argmin(score, 0)
for j, k in ((3, 'blush_l'), (4, 'blush_r')):
    own[ndi.binary_dilation(core[k], iterations=3)] = j
D = rgb - body
parts, recon = {}, body.copy()
for j, name in enumerate(FEATS):
    c, reg = core[name], (own == j) & U
    inner = ndi.binary_erosion(c, iterations=1)
    _, (jy, jx) = ndi.distance_transform_edt(~inner, return_indices=True)
    V = rgb[jy, jx] - body
    a = np.clip((D * V).sum(-1) / np.maximum((V * V).sum(-1), 1e-6), 0, 1)
    lo = np.where(D > 0, D / np.maximum(1 - body, 1e-6), np.where(D < 0, -D / np.maximum(body, 1e-6), 0)).max(-1)
    a = np.clip(np.maximum(a, lo), 0, 1)
    a[inner] = 1
    a[~reg] = 0
    col = np.clip(np.where(a[..., None] > 0, body + D / np.maximum(a[..., None], 1e-6), 0), 0, 1)
    recon = a[..., None] * col + (1 - a[..., None]) * recon
    cys, cxs = np.nonzero(c)
    ys, xs = np.nonzero(a > 0)
    bx0, bx1, by0, by1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    parts[name] = dict(x=bx0, y=by0, w=bx1 - bx0, h=by1 - by0,
                       cx=round(float(cxs.mean()), 1), cy=round(float(cys.mean()), 1),
                       core=[int(cxs.min()), int(cys.min()), int(cxs.max()), int(cys.max())],
                       layer=np.dstack([col, a])[by0:by1, bx0:bx1])
err = np.abs(recon - rgb).max(-1)[alpha0 > .99]
print(f'복원 오차: 최대 {err.max() * 255:.2f}/255')

# 입 선 굵기 · 눈 · 입 색 (새로 그리는 표정 선을 원래 그림에 맞추기 위해)
mm = core['mouth']
colsum = mm.sum(0)
thick = float(np.median(colsum[colsum > 0]))
feat = rgb[(core['eye_l'] | core['eye_r'] | mm) & (lum < .3)]
ink = '#%02x%02x%02x' % tuple((np.median(feat, 0) * 255).round().astype(int))
print(f'입 선 굵기 {thick:.0f}px, 선 색 {ink}')

OUT.mkdir(exist_ok=True)
for f in OUT.glob('*.png'):
    f.unlink()
Image.fromarray((np.dstack([body, alpha0]) * 255 + .5).astype(np.uint8)).save(OUT / 'body.png', optimize=True)
meta = {'W': W, 'H': H, 'stroke': round(thick, 1), 'ink': ink}
for name, p in parts.items():
    Image.fromarray((p['layer'] * 255 + .5).astype(np.uint8)).save(OUT / f'{name}.png', optimize=True)
    meta[name] = {k: p[k] for k in ('x', 'y', 'w', 'h', 'cx', 'cy', 'core')}
(OUT / 'parts.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
JS.write_text('// tools/build_bell_parts.py 가 만든 파일입니다 — 종 얼굴 조각 위치(원본 픽셀)와 선 굵기 · 색.\n'
              f'window.BELL_PARTS = {json.dumps(meta)};\n', encoding='utf-8')
print(json.dumps(meta))

# 확인용: 원본 / 눈 뺀 얼굴(눈 감을 때 바탕) / 눈 · 입 뺀 얼굴
DBG.mkdir(parents=True, exist_ok=True)
bgc = np.array([90, 140, 150]) / 255


def stack(names):
    out = body.copy()
    for nm in names:
        p = parts[nm]
        sl = (slice(p['y'], p['y'] + p['h']), slice(p['x'], p['x'] + p['w']))
        L = p['layer']
        out[sl] = L[..., 3:4] * L[..., :3] + (1 - L[..., 3:4]) * out[sl]
    return out


views = [rgb, stack(('blush_l', 'blush_r', 'mouth')), stack(('blush_l', 'blush_r'))]
tiles = [Image.fromarray(((v * alpha0[..., None] + bgc * (1 - alpha0[..., None]))[y0:y1, x0:x1] * 255 + .5).astype(np.uint8)) for v in views]
sheet = Image.new('RGB', (tiles[0].width, tiles[0].height * 3 + 12), 'black')
for i, t in enumerate(tiles):
    sheet.paste(t, (0, i * (t.height + 6)))
sheet.save(DBG / 'bp3_sheet.png')
print(f'끝 {time.time() - t0:.0f}s')
