"""반복 구간의 박마다 크기를 고르게(내레이션 밑에서 음악이 줄어 있던 자리 메움) → 게임용 파일로 저장.

결과
  /tmp/gl/hg/bgm/bgm_final.wav               확인용
  <프로젝트>/assets/bgm_loop.wav             원본 보관 (44.1kHz 16bit 스테레오, 한 바퀴)
  <프로젝트>/src/bgm-data.js                 window.BGM_WAV = base64 (index.html을 더블클릭해 열어도 쓸 수 있게)
"""
import base64
import io
import json
import pathlib
import subprocess

import numpy as np
import soundfile as sf

D = pathlib.Path('/tmp/gl/hg/bgm')
P = pathlib.Path('/Users/jini/Documents/Jini/2026/Phonics/Phonics-Halli-Galli')
x, sr = sf.read(D / 'bgm_loop.wav', always_2d=True)
x = x.astype(np.float64)
meta = json.loads((D / 'loop.json').read_text())
beat = meta['beat']
N = len(x)
nb = int(round(N / (beat * sr)))                     # 16박
edges = np.round(np.arange(nb + 1) * N / nb).astype(int)


def beat_db(y):
    m = y.mean(1)
    return np.array([20 * np.log10(np.sqrt(np.mean(m[a:b] ** 2)) + 1e-12) for a, b in zip(edges[:-1], edges[1:])])


before = beat_db(x)
target = np.median(before)
corr = np.clip(target - before, -3.0, 4.0)           # 줄어 있던 박은 최대 +4dB, 큰 박은 최대 -3dB
# 박 가운데에 보정값을 두고 이어지게(한 바퀴 돌아 처음과 끝이 맞물리게) 부드럽게 잇기
centers = (edges[:-1] + edges[1:]) / 2
cx = np.concatenate([centers - N, centers, centers + N])
cy = np.concatenate([corr, corr, corr])
t = np.arange(N)
i = np.searchsorted(cx, t) - 1
f = (t - cx[i]) / (cx[i + 1] - cx[i])
f = f * f * (3 - 2 * f)                               # smoothstep
gain_db = cy[i] * (1 - f) + cy[i + 1] * f
y = x * (10 ** (gain_db / 20))[:, None]
after = beat_db(y)
print('박별 크기(dB) 전:', np.round(before - target, 1))
print('박별 크기(dB) 후:', np.round(after - np.median(after), 1))
print(f'박 사이 크기 차이(최대-최소): 전 {before.max() - before.min():.1f} dB → 후 {after.max() - after.min():.1f} dB')
print(f'이음새 이득 차: {abs(gain_db[-1] - gain_db[0]):.3f} dB')

# 다시 -18 LUFS, 최고치 0.89 이하
sf.write(D / 'tmp_flat.wav', y, sr, subtype='FLOAT')
r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(D / 'tmp_flat.wav'), '-af', 'ebur128', '-f', 'null', '-'],
                   capture_output=True, text=True).stderr
I = float(r.split('Integrated loudness:')[1].split('I:')[1].split('LUFS')[0])
g = 10 ** ((-18 - I) / 20)
g = min(g, .89 / np.abs(y).max())
y *= g
print(f'{I:.1f} LUFS → ×{g:.2f}, 최고치 {np.abs(y).max():.2f}')

sf.write(D / 'bgm_final.wav', y, sr, subtype='PCM_16')
sf.write(D / 'bgm_final_x3.wav', np.concatenate([y] * 3), sr, subtype='PCM_16')
(P / 'assets').mkdir(exist_ok=True)
sf.write(P / 'assets' / 'bgm_loop.wav', y, sr, subtype='PCM_16')

buf = io.BytesIO()
sf.write(buf, y, sr, format='WAV', subtype='PCM_16')
b64 = base64.b64encode(buf.getvalue()).decode('ascii')
js = ('// tools/bgm/finish_loop.py 가 만든 파일입니다 — 인트로 영상 음악(목소리 뺀 것)의 한 바퀴(4마디).\n'
      '// index.html을 더블클릭해 열어도(file://) 쓸 수 있게 소리 파일을 글자(base64)로 넣어 두었어요. 원본: assets/bgm_loop.wav\n'
      f'window.BGM_LOOP = {{ bpm: {60 / beat:.2f}, bars: {nb // 4}, seconds: {N / sr:.6f}, samples: {N}, rate: {sr} }};\n'
      f'window.BGM_WAV = "{b64}";\n')
(P / 'src' / 'bgm-data.js').write_text(js, encoding='utf-8')
print(f'src/bgm-data.js {len(js) / 1e6:.2f} MB, 한 바퀴 {N / sr:.3f}s ({N} samples @ {sr})')
