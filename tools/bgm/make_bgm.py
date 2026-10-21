"""배경음악 다시 만들기 — 더 깨끗한 목소리 분리(BS-RoFormer)로 같은 4마디를 자름.

예전 판(Demucs)은 내레이션 밑의 음악이 '물 먹은 듯 깨지는' 소리가 남았음.
같은 구간(박 1→17, 126.66 BPM, 7.58초)을 새 분리본에서 잘라 비교하고, 더 깨끗한 쪽으로 저장.

입력: /tmp/gl/hg/bgm/sep2/intro_(Instrumental)_model_bs_roformer_ep_317_sdr_12.wav
      (audio-separator --model_filename model_bs_roformer_ep_317_sdr_12.9755.ckpt 로 만든 것)
결과: assets/bgm_loop.wav, src/bgm-data.js
"""
import base64
import io
import json
import pathlib
import subprocess

import librosa
import numpy as np
import soundfile as sf

D = pathlib.Path('/tmp/gl/hg/bgm')
P = pathlib.Path('/Users/jini/Documents/Jini/2026/Phonics/Phonics-Halli-Galli')
NEW = D / 'sep2' / 'intro_(Instrumental)_model_bs_roformer_ep_317_sdr_12.wav'
OLD = D / 'accomp.wav'
VOC = D / 'sep2' / 'intro_(Vocals)_model_bs_roformer_ep_317_sdr_12.wav'
meta = json.loads((D / 'loop.json').read_text())
beat = meta['beat']

new, sr = sf.read(NEW, always_2d=True)
old, sr2 = sf.read(OLD, always_2d=True)
voc, _ = sf.read(VOC, always_2d=True)
assert sr == sr2 == 44100, (sr, sr2)
n = min(len(new), len(old))
new, old, voc = new[:n], old[:n], voc[:n]

# ── 1) 깨짐 정도 비교: 목소리 있던 박 / 없던 박에서 고음 대역 잡음 정도(spectral flatness)와 '구멍'(크기 출렁임)
grid = np.arange(meta['t0'] - beat, n / sr, beat)
vm = voc.mean(1)
voiced = np.array([20 * np.log10(np.sqrt(np.mean(vm[int(a * sr): int((a + beat) * sr)] ** 2)) + 1e-12) > -35 for a in grid[:-1]])


def texture(x):
    m = x.mean(1).astype(np.float32)
    S = np.abs(librosa.stft(m, n_fft=2048, hop_length=512))
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=512)
    hb = (f > 1500) & (f < 9000)
    flat = librosa.feature.spectral_flatness(S=S[hb] + 1e-10)[0]
    # 프레임 사이 고음 대역 세기 출렁임 (깨지는 소리일수록 큼)
    e = 20 * np.log10(S[hb].sum(0) + 1e-9)
    jitter = np.abs(np.diff(e, prepend=e[0]))
    on = np.zeros_like(t, bool)
    for k, g in enumerate(grid[:-1]):
        if voiced[k]:
            on |= (t >= g) & (t < g + beat)
    music = (t >= grid[1]) & (t < grid[17])
    return (flat[on & music].mean(), flat[~on & music].mean(), jitter[on & music].mean(), jitter[~on & music].mean())


for name, x in (('예전(Demucs)', old), ('새(RoFormer)', new)):
    a, b, c, d = texture(x)
    print(f'{name}: 잡음 정도 목소리자리 {a:.3f} / 나머지 {b:.3f} (배율 {a / b:.1f})   출렁임 {c:.2f} / {d:.2f} dB')

# ── 2) 같은 구간 자르기 (박 1 → 17) + 40ms 크로스페이드
s0, s1 = int(round(meta['t0'] * sr)), int(round(meta['t1'] * sr))
xf = int(.040 * sr)


def cut(x):
    seg = x[s0 - xf: s1].copy()
    pre, body = seg[:xf], seg[xf:]
    w = np.linspace(0, np.pi / 2, xf)[:, None]
    body[-xf:] = body[-xf:] * np.cos(w) + pre * np.sin(w)
    return body


loop = cut(new)
N = len(loop)
nb = int(round(N / (beat * sr)))
edges = np.round(np.arange(nb + 1) * N / nb).astype(int)


def beat_db(y):
    m = y.mean(1)
    return np.array([20 * np.log10(np.sqrt(np.mean(m[a:b] ** 2)) + 1e-12) for a, b in zip(edges[:-1], edges[1:])])


before = beat_db(loop)
med = np.median(before)
print('박별 크기(새, dB):', np.round(before - med, 1))
# ── 3) 박 사이 크기를 살짝만 고르게 (±2dB 안에서, 부드럽게 · 한 바퀴 이어지게)
corr = np.clip(med - before, -2.0, 2.0) * 0.8
centers = (edges[:-1] + edges[1:]) / 2
cx = np.concatenate([centers - N, centers, centers + N])
cy = np.concatenate([corr, corr, corr])
t = np.arange(N)
i = np.searchsorted(cx, t) - 1
f = (t - cx[i]) / (cx[i + 1] - cx[i])
f = f * f * (3 - 2 * f)
g_db = cy[i] * (1 - f) + cy[i + 1] * f
y = loop * (10 ** (g_db / 20))[:, None]
after = beat_db(y)
print(f'박 사이 크기 차이: {before.max() - before.min():.1f} dB → {after.max() - after.min():.1f} dB')

# ── 4) 크기 -18 LUFS, 최고치 0.89 이하
sf.write(D / 'tmp_v2.wav', y, sr, subtype='FLOAT')
r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(D / 'tmp_v2.wav'), '-af', 'ebur128', '-f', 'null', '-'],
                   capture_output=True, text=True).stderr
I = float(r.split('Integrated loudness:')[1].split('I:')[1].split('LUFS')[0])
k = min(10 ** ((-18 - I) / 20), .89 / np.abs(y).max())
y *= k
print(f'{I:.1f} LUFS → ×{k:.2f}, 최고치 {np.abs(y).max():.2f}')

# 이음새 확인
rep = np.concatenate([y, y])
jump = np.abs(rep[N] - rep[N - 1]).max()
typ = np.percentile(np.abs(np.diff(rep, axis=0)).max(1), 99.9)
print(f'이음새 샘플 차이 {jump:.4f} (보통 99.9% {typ:.4f})')

sf.write(D / 'bgm_v2.wav', y, sr, subtype='PCM_16')
sf.write(D / 'bgm_v2_x3.wav', np.concatenate([y] * 3), sr, subtype='PCM_16')
sf.write(D / 'bgm_v1_x3.wav', sf.read(D / 'bgm_final_x3.wav')[0], sr, subtype='PCM_16')
sf.write(P / 'assets' / 'bgm_loop.wav', y, sr, subtype='PCM_16')
buf = io.BytesIO()
sf.write(buf, y, sr, format='WAV', subtype='PCM_16')
b64 = base64.b64encode(buf.getvalue()).decode('ascii')
js = ('// tools/bgm/make_bgm.py 가 만든 파일입니다 — 인트로 영상 음악(목소리를 BS-RoFormer로 뺀 것)의 한 바퀴(4마디).\n'
      '// index.html을 더블클릭해 열어도(file://) 쓸 수 있게 소리 파일을 글자(base64)로 넣어 두었어요. 원본: assets/bgm_loop.wav\n'
      f'window.BGM_LOOP = {{ bpm: {60 / beat:.2f}, bars: {nb // 4}, seconds: {N / sr:.6f}, samples: {N}, rate: {sr} }};\n'
      f'window.BGM_WAV = "{b64}";\n')
(P / 'src' / 'bgm-data.js').write_text(js, encoding='utf-8')
print(f'저장: assets/bgm_loop.wav, src/bgm-data.js ({len(js) / 1e6:.2f} MB), 한 바퀴 {N / sr:.3f}s')
