"""인트로 음악(목소리 뺀 것)에서 이음새 없는 반복 구간을 잘라 배경음악으로 만든다.

1) 드럼 소리로 박자 격자를 정밀하게 맞춤 (박 길이 · 첫 박 위치)
2) 마디 첫 박(다운비트) 찾기: 킥(저음) 세기 + 끝맺음 큰 소리(피날레)가 마디 첫 박에 오도록
3) 피날레 앞까지의 4마디를 반복 구간으로 → 끝과 시작을 40ms 크로스페이드로 이어 붙임
4) 확인: 이음새의 소리 변화가 다른 박 경계와 비슷한지, 남은 목소리가 없는지
"""
import json
import subprocess

import librosa
import numpy as np
import soundfile as sf

D = '/tmp/gl/hg/bgm/'
acc, sr = sf.read(D + 'accomp.wav', always_2d=True)
drums = sf.read(D + 'stem_drums.wav', always_2d=True)[0].mean(1).astype(np.float32)
voice = sf.read(D + 'stem_vocals.wav', always_2d=True)[0].mean(1)
mono = acc.mean(1).astype(np.float32)
dur = len(mono) / sr

# ── 1) 박자 격자: 드럼 온셋 세기의 합이 최대가 되는 (박 길이, 위상)
hop = 128
env = librosa.onset.onset_strength(y=drums, sr=sr, hop_length=hop)
et = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=hop)
def score(P, ph):
    ts = np.arange(ph, dur - .05, P)
    idx = np.clip(np.round(ts * sr / hop).astype(int), 0, len(env) - 1)
    # 박 근처 ±1프레임 최대값
    return sum(env[max(0, i - 1): i + 2].max() for i in idx) / len(idx)
best = max(((score(P, ph), P, ph) for P in np.arange(.440, .500, .0005) for ph in np.arange(0, .5, .004)), key=lambda t: t[0])
_, P, ph = best
# 미세 조정
best = max(((score(p, q), p, q) for p in np.arange(P - .0006, P + .0006, .00005) for q in np.arange(ph - .006, ph + .006, .0005)), key=lambda t: t[0])
_, P, ph = best
print(f'박 길이 {P:.5f}s = {60 / P:.2f} BPM, 첫 박 {ph:.4f}s')
grid = np.arange(ph, dur, P)

# ── 2) 다운비트: 위상(0~3)마다 킥 세기 합
S = np.abs(librosa.stft(drums, n_fft=2048, hop_length=hop))
fq = librosa.fft_frequencies(sr=sr, n_fft=2048)
kick = np.maximum(0, np.diff(S[fq < 130].sum(0), prepend=0))
def at(arr, t, w=.04):
    i0, i1 = int((t - .01) * sr / hop), int((t + w) * sr / hop)
    return arr[max(0, i0): max(i0 + 1, i1)].max()
kk = np.array([at(kick, t) for t in grid])
loud = np.array([20 * np.log10(np.sqrt(np.mean(mono[int(t * sr): int((t + P) * sr)] ** 2)) + 1e-9) for t in grid])
fin = int(np.argmax(loud))                                  # 가장 큰 박 = 피날레
print('박별 킥 세기:', ' '.join(f'{i}:{v:.0f}' for i, v in enumerate(kk)))
print('박별 크기 dB:', ' '.join(f'{i}:{v:.0f}' for i, v in enumerate(loud)))
print(f'가장 큰 박(피날레) = {fin}번 박 ({grid[fin]:.3f}s)')
phase_kick = [kk[p::4].mean() for p in range(4)]
print('위상별 킥 평균:', [round(v, 1) for v in phase_kick])
down = fin % 4                                              # 피날레가 마디 첫 박에 온다고 봄
print(f'다운비트 위상 = {down} (킥이 가장 센 위상 = {int(np.argmax(phase_kick))})')

# ── 3) 반복 구간: 피날레 마디 바로 앞에서 끝나는 4마디 (안 되면 2마디)
bars = 4
start_beat = fin - 4 * bars
while start_beat < 0:
    bars //= 2
    start_beat = fin - 4 * bars
t0, t1 = grid[start_beat], grid[fin]
print(f'반복 구간: {start_beat}번 박 {t0:.4f}s → {fin}번 박 {t1:.4f}s  ({bars}마디, {t1 - t0:.3f}s)')

# 시작 · 끝을 가장 가까운 '0을 지나는 점'으로 살짝 옮겨 딸깍 소리 방지 (±2ms)
def zc(x, t):
    i = int(round(t * sr)); w = int(.002 * sr)
    seg = x[i - w: i + w]
    z = np.nonzero(np.diff(np.signbit(seg)))[0]
    return (i - w + z[np.argmin(np.abs(z - w))]) if len(z) else i
s0, s1 = zc(mono, t0), zc(mono, t1)
xf = int(.040 * sr)
seg = acc[s0 - xf: s1].copy()                               # 앞에 xf만큼 더 (크로스페이드 재료)
pre, body = seg[:xf], seg[xf:]
tail = body[-xf:]
w = np.linspace(0, np.pi / 2, xf)[:, None]
body[-xf:] = tail * np.cos(w) + pre * np.sin(w)             # 끝이 시작 바로 앞 소리로 이어지게 (같은 세기 크로스페이드)
loop = body

# ── 4) 확인
rep = np.concatenate([loop, loop, loop])
m = rep.mean(1).astype(np.float32)
flux = librosa.onset.onset_strength(y=m, sr=sr, hop_length=hop)
L = len(loop)
seams = [L, 2 * L]
bl = [int(round((grid[b] - grid[start_beat]) * sr)) for b in range(start_beat, fin)]
beat_pos = [p + k * L for k in range(3) for p in bl]
fl = lambda pos: flux[max(0, pos // hop - 2): pos // hop + 3].max()
seam_f = [fl(p) for p in seams]
beat_f = [fl(p) for p in beat_pos if all(abs(p - s) > hop * 4 for s in seams)]
print(f'이음새 소리 변화 {np.round(seam_f, 2)} vs 다른 박 경계 중앙값 {np.median(beat_f):.2f} (최대 {np.max(beat_f):.2f})')
jump = np.abs(rep[L] - rep[L - 1]).max()
typ = np.percentile(np.abs(np.diff(rep, axis=0)).max(1), 99.9)
print(f'이음새 샘플 차이 {jump:.4f} (보통 99.9% {typ:.4f})')
# 남은 목소리: 반복 구간에서 목소리 대역 세기와 분리된 목소리 세기의 상관
seg_v = voice[s0: s1]
seg_a = mono[s0: s1]
def band_env(x):
    X = np.abs(librosa.stft(x.astype(np.float32), n_fft=1024, hop_length=512))
    f = librosa.fft_frequencies(sr=sr, n_fft=1024)
    return X[(f > 300) & (f < 3500)].sum(0)
ev, ea = band_env(seg_v), band_env(seg_a)
print(f'목소리 세기 ↔ 음악의 목소리 대역 세기 상관 {np.corrcoef(ev, ea)[0, 1]:.2f} (0 근처면 목소리 흔적 적음)')

# 크기 맞춤: -18 LUFS 근처(재생할 때 게임에서 더 줄임), 최고치 -1 dBFS 넘지 않게
sf.write(D + 'loop_raw.wav', loop, sr, subtype='FLOAT')
r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', D + 'loop_raw.wav', '-af', 'ebur128', '-f', 'null', '-'],
                   capture_output=True, text=True).stderr
I = float(r.split('Integrated loudness:')[1].split('I:')[1].split('LUFS')[0])
g = 10 ** ((-18 - I) / 20)
pk = np.abs(loop).max() * g
if pk > .89:
    g *= .89 / pk
loop_n = loop * g
print(f'원래 {I:.1f} LUFS → ×{g:.2f} (최고치 {np.abs(loop_n).max():.2f})')
sf.write(D + 'bgm_loop.wav', loop_n, sr, subtype='PCM_16')
sf.write(D + 'bgm_loop_x3.wav', np.concatenate([loop_n] * 3), sr, subtype='PCM_16')
json.dump({'bpm': 60 / P, 'beat': P, 'bars': bars, 't0': s0 / sr, 't1': s1 / sr, 'len': L / sr, 'gain': g}, open(D + 'loop.json', 'w'), indent=1)
print('saved', L / sr, 's')
