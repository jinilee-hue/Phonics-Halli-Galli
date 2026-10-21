"""카드 그림(assets/card/card_*.png)을 게임용 가벼운 사본으로 만듭니다. 원본은 건드리지 않습니다.

  - 모서리 바깥의 검은 바탕을 투명하게 → 탁자 위에 둥근 카드로 보임
  - 크기를 600×800(3:4, 게임 카드 비율)으로 통일 (cat/cats 원본만 크기가 달라서 함께 맞춤)
  - 모든 카드 모서리를 같은 둥글기(R)로 다듬어 CSS 그림자와 정확히 맞춤
  - WebP로 저장 (34장 원본 약 23MB → 몇 MB)
  - src/cards.js 에 그림이 있는 낱말 목록을 적음 (게임이 이 목록으로 그림 카드를 씀)

실행: /Users/jini/.hermes/bin/uv run --quiet --with pillow --with numpy --with scipy python tools/build_cards.py
"""
import json
import pathlib

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'assets' / 'card'
OUT = ROOT / 'assets' / 'card_web'
JS = ROOT / 'src' / 'cards.js'
OW, OH = 600, 800
R = 0.075          # 모서리 둥글기 = 카드 폭의 7.5% (CSS .card.art .f 의 border-radius 와 같은 값)
SS = 4             # 모서리 매끈하게: 4배로 그려서 줄임


def rounded_mask(w, h, r):
    W, H, rr = w * SS, h * SS, r * SS
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32) + .5
    cx = np.clip(xx, rr, W - rr)
    cy = np.clip(yy, rr, H - rr)
    inside = ((xx - cx) ** 2 + (yy - cy) ** 2) <= rr * rr
    m = Image.fromarray((inside * 255).astype(np.uint8)).resize((w, h), Image.BOX)
    return np.asarray(m).astype(np.float32) / 255


def black_corners(rgb):
    """네 모서리에 닿은 검은 덩어리 (카드 바깥 바탕)."""
    H, W = rgb.shape[:2]
    dark = rgb.max(-1) < .2
    box = np.zeros_like(dark)
    k = int(W * .14)
    box[:k, :k] = box[:k, -k:] = box[-k:, :k] = box[-k:, -k:] = True
    lab, _ = ndi.label(dark & box)
    ids = {lab[0, 0], lab[0, -1], lab[-1, 0], lab[-1, -1]} - {0}
    return np.isin(lab, list(ids))


def corner_radius(alpha_or_black, W):
    """맨 윗줄에서 카드가 시작하는 x (= 모서리 둥글기, 원본 px)."""
    row = alpha_or_black[0]
    xs = np.nonzero(row)[0]
    return int(xs.min()) if len(xs) else 0


OUT.mkdir(exist_ok=True)
files = sorted(SRC.glob('card_*.png')) + [SRC / f'{n}.png' for n in ('my_card', 'coco_card') if (SRC / f'{n}.png').exists()]   # 카드 뒷면(나 · Coco)도 같은 모양으로
art, total_in, total_out, radii_black = {}, 0, 0, []
for p in files:
    word = p.stem[len('card_'):] if p.stem.startswith('card_') else p.stem
    im = Image.open(p).convert('RGBA')
    a = np.asarray(im).astype(np.float32) / 255
    rgb, alpha = a[..., :3], a[..., 3].copy()
    H, W = alpha.shape
    blk = black_corners(rgb)
    if blk.any():
        # 검은 바탕과 섞인 가장자리 픽셀: 검은색을 빼고 원래 카드색 + 반투명으로 되돌림
        band = ndi.binary_dilation(blk, iterations=4) & ~blk
        inner = ~ndi.binary_dilation(blk, iterations=4)
        _, (iy, ix) = ndi.distance_transform_edt(~inner, return_indices=True)
        F = rgb[iy, ix]
        al = np.clip((rgb * F).sum(-1) / np.maximum((F * F).sum(-1), 1e-6), 0, 1)
        alpha[blk] = 0
        alpha[band] = np.minimum(alpha[band], al[band])
        rgb = np.where(band[..., None], np.clip(rgb / np.maximum(alpha[..., None], 1e-3), 0, 1), rgb)
        radii_black.append(corner_radius(~blk, W) / W)
    # 카드 둘레 투명 여백을 잘라 내고 3:4로 맞춤 (cat/cats 원본은 0.79라 가로를 약간 줄임)
    ys, xs = np.nonzero(alpha > .04)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    ratio = (x1 - x0) / (y1 - y0)
    img = Image.fromarray((np.dstack([rgb, alpha]) * 255 + .5).astype(np.uint8), 'RGBA').crop((x0, y0, x1, y1))
    if p.stem.startswith('card_'):
        out = img.resize((OW, OH), Image.LANCZOS)
        oa = np.asarray(out).astype(np.float32)
        oa[..., 3] *= rounded_mask(OW, OH, R * OW)
        out = Image.fromarray((oa + .5).astype(np.uint8), 'RGBA')
    else:
        # 카드 뒷면(my_card · coco_card): 가운데 동그란 S가 찌그러지지 않게 비율은 그대로 두고 높이만 맞춰 가운데 놓음
        bw = round(OH * ratio)
        out = Image.new('RGBA', (OW, OH), (0, 0, 0, 0))
        out.alpha_composite(img.resize((bw, OH), Image.LANCZOS), ((OW - bw) // 2, 0))
    dst = OUT / f'card_{word}.webp'
    out.save(dst, 'WEBP', quality=88, method=6)
    total_in += p.stat().st_size
    total_out += dst.stat().st_size
    art[word] = f'./assets/card_web/card_{word}.webp'
    note = (f'  ※ 비율 {ratio:.3f} 그대로 (높이 맞춤, 가로 {bw}px 가운데)' if not p.stem.startswith('card_') else
            f'  ※ 비율 {ratio:.3f} → 0.750 (가로 {(1 - .75 / ratio) * 100:.1f}% 줄임)' if abs(ratio - .75) > .005 else '')
    print(f'{word:10s} {W}x{H} → {OW}x{OH}  모서리 {"검은 바탕→투명" if blk.any() else "원래 투명"}  {dst.stat().st_size // 1024} KB{note}')

print(f'\n{len(files)}장  {total_in / 1e6:.1f} MB → {total_out / 1e6:.2f} MB')
print(f'검은 바탕 카드의 원래 둥글기 {min(radii_black) * 100:.1f}% ~ {max(radii_black) * 100:.1f}% (폭 대비) → 모두 {R * 100:.1f}%로 통일')
assert R >= max(radii_black) - .002, '통일 둥글기 R이 원래보다 작으면 검은 모서리가 남을 수 있음'

JS.write_text('// tools/build_cards.py 가 만든 파일입니다. 카드 그림을 바꾸면 스크립트를 다시 돌리세요.\n'
              '// 그림이 있는 낱말 → 게임용 그림 경로 (원본은 assets/card)\n'
              f'window.CARD_ART = {json.dumps(art, ensure_ascii=False, indent=1)};\n', encoding='utf-8')
print(JS)
