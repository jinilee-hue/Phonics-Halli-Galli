"""카드 낱말 읽어 주기 소리를 미리 만듭니다 — 기기마다 목소리가 달라지지 않게 (기기 내장 음성 대신).

목소리: Microsoft 신경망 음성 'Ana' (en-US-AnaNeural · 미국 영어 여자아이 · 'Cute'), 조금 느리게(-10%)
도구: edge-tts (무료 · 시제품용). 정식 출시 때는 같은 목소리를 Azure Speech(유료 정식 서비스)로 다시 만들거나 성우 녹음으로 바꿀 것.

결과
  assets/voice/<낱말>.mp3   낱말마다 한 파일 — 받은 원본 그대로(다시 압축 안 함), 끝에 붙은 긴 빈소리만 잘라 냄 · 24kHz 모노
  src/voice-data.js         window.VOICE_CLIPS = {낱말: base64 mp3} — 파일을 더블클릭해 열어도(file://) 소리가 나게 글자로 넣음
                            window.VOICE_TRIM  = {낱말: [시작 초, 크기 배수]} — 앞 빈소리 · 크기는 재생할 때 맞춤 (main.js speak)
낱말 목록은 src/words.js(tools/build_words.py가 만든 것)에서 카드에 나올 수 있는 낱말을 모두 모읍니다.
words.js가 바뀌면 이 스크립트를 다시 돌리세요. 받은 원본 소리는 ~/.cache/phonics-halli-galli/voice/ 에 남겨 두어 다시 돌릴 때 빠릅니다.

실행: /Users/jini/.hermes/bin/uv run --quiet --with edge-tts --with numpy python tools/build_voice.py
"""
import asyncio
import base64
import json
import pathlib
import re
import subprocess

import numpy as np

VOICE, RATE = 'en-US-AnaNeural', '-10%'
SR = 24000
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'assets' / 'voice'
JS = ROOT / 'src' / 'voice-data.js'
CACHE = pathlib.Path.home() / '.cache' / 'phonics-halli-galli' / 'voice' / f'{VOICE}_{RATE.replace("%", "pct")}'


# ── 1) 카드에 나올 수 있는 낱말 모두 (main.js의 level1Cards · level2Cards · level3Cards와 같은 칸)
src = (ROOT / 'src' / 'words.js').read_text(encoding='utf-8')
W = json.loads(src[src.index('{'): src.rindex('}') + 1])
words = set()
for lv in ('level1', 'level2'):
    for w in W[lv]['words']:
        words |= {w['base'], w['plural']}
L3 = W['level3']
for w in L3['es'] + L3['regular']:
    words |= {w['base'], w['plural']}
for t in L3['traps']:
    words.add(t['w'])
    if t.get('plural'):
        words.add(t['plural'])
words = sorted(x.strip() for x in words if x and x.strip())
fname = lambda w: re.sub(r'[^a-z0-9]+', '_', w.lower()).strip('_')
assert len({fname(w) for w in words}) == len(words), '파일 이름이 겹치는 낱말이 있음'
print(f'낱말 {len(words)}개 (1단계 {len(W["level1"]["words"]) * 2} · 2단계 {len(W["level2"]["words"]) * 2} · 3단계 나머지)')


# ── 2) 받기 (캐시에 없는 것만, 6개씩 동시에)
async def fetch_all():
    import edge_tts
    CACHE.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(6)
    todo = [w for w in words if not (CACHE / f'{fname(w)}.mp3').exists()]

    async def one(w):
        async with sem:
            for attempt in range(4):
                try:
                    tmp = CACHE / f'{fname(w)}.part'
                    await edge_tts.Communicate(f'{w}.', VOICE, rate=RATE).save(str(tmp))   # 마침표: 끝을 내려 읽게
                    tmp.rename(CACHE / f'{fname(w)}.mp3')
                    return
                except Exception as e:                                                       # 가끔 끊김 → 다시
                    if attempt == 3:
                        raise RuntimeError(f'{w}: {e}')
                    await asyncio.sleep(1.5 * (attempt + 1))
    await asyncio.gather(*(one(w) for w in todo))
    return len(todo)


got = asyncio.run(fetch_all())
print(f'새로 받음 {got}개 · 캐시 {CACHE}')


# ── 3) 소리 파일: 받은 원본 mp3를 다시 압축하지 않고 그대로 씀 (첫소리 k · t · p 같은 짧은 소리가 뭉개지지 않게)
#    - 끝에 붙은 긴 빈소리만 잘라 냄: 말 끝 + 0.15초까지 (복수 -s의 '스'는 작아서 넉넉히). 프레임 단위 복사라 소리 손실 없음
#    - 앞 빈소리 · 크기는 파일을 고치지 않고 재생할 때 맞춤 → window.VOICE_TRIM = {낱말: [시작 초, 크기 배수]}
#      시작: 말이 시작하기 0.12초 전부터 재생 — 그사이 배경음악이 먼저 줄어들고(0.08초), 기기 소리 장치(블루투스 · 아이패드)가
#            깨어날 틈이 있어서 첫소리가 묻히거나 먹히지 않음 (전에는 0.03초라 빠듯했음)
#      크기: 말소리 크기를 -17dBFS로, 가장 큰 곳은 -1dBFS를 넘지 않게 (전과 같은 크기)
LEAD, TAIL = .12, .15
FR = int(SR * .01)                                            # 10ms 틀


def decode(p):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(p), '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def speech(x):
    """10ms 틀마다 소리 세기 + 말소리 틀 (가장 큰 소리보다 50dB 작은 것까지 '소리'로 봄)"""
    n = len(x) // FR
    rms = np.sqrt((x[:n * FR].reshape(n, FR) ** 2).mean(1) + 1e-12)
    return rms, np.nonzero(rms > rms.max() * 10 ** (-50 / 20))[0]


OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob('*.mp3'):
    f.unlink()
clips, trim, report = {}, {}, []
for w in words:
    raw = CACHE / f'{fname(w)}.mp3'
    _, act = speech(decode(raw))
    dst = OUT / f'{fname(w)}.mp3'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(raw), '-t', f'{(act[-1] + 1) * FR / SR + TAIL:.3f}',
                    '-c:a', 'copy', '-map_metadata', '-1', '-id3v2_version', '0', '-write_xing', '0', str(dst)], check=True)
    y = decode(dst)                                           # 잘라 낸 파일로 다시 잼 (브라우저가 푸는 것과 같은 기준)
    rms, act = speech(y)
    voiced = rms[act[0]:act[-1] + 1]
    loud = np.sqrt((voiced[voiced > voiced.max() * .1] ** 2).mean())   # 말소리 부분의 크기
    g = min(10 ** (-17 / 20) / loud, 10 ** (-1 / 20) / np.abs(y).max())
    start = max(0., act[0] * FR / SR - LEAD)
    clips[w] = base64.b64encode(dst.read_bytes()).decode('ascii')
    trim[w] = [round(start, 3), round(float(g), 3)]
    report.append((w, len(y) / SR - start, dst.stat().st_size, start))

JS.write_text(
    '// tools/build_voice.py 가 만든 파일입니다 — 카드 낱말 읽어 주기 소리 (직접 고치지 마세요).\n'
    f'// 목소리: {VOICE} (Microsoft 신경망 음성 · 여자아이) · 빠르기 {RATE} · edge-tts로 만듦 (시제품용)\n'
    '// 파일을 더블클릭해 열어도(file://) 소리가 나도록 mp3를 글자(base64)로 넣어 두었어요. 원본: assets/voice/*.mp3\n'
    f'window.VOICE_INFO = {json.dumps({"voice": VOICE, "rate": RATE, "count": len(clips)})};\n'
    '// 재생할 때 맞추는 값 [시작 초(말 시작 0.12초 전), 크기 배수(말소리 -17dBFS)] — src/main.js speak()가 씀\n'
    f'window.VOICE_TRIM = {json.dumps(trim, separators=(",", ":"))};\n'
    'window.VOICE_CLIPS = {\n' + ',\n'.join(f'{json.dumps(w)}:"{b}"' for w, b in clips.items()) + '\n};\n',
    encoding='utf-8')
d = np.array([r[1] for r in report])
print(f'만든 소리 {len(clips)}개 · 길이 {d.min():.2f}~{d.max():.2f}초 (가운데 {np.median(d):.2f}) · '
      f'mp3 합계 {sum(r[2] for r in report) / 1024:.0f}KB · voice-data.js {JS.stat().st_size / 1024:.0f}KB')
print('가장 짧은 5개:', [(r[0], round(r[1], 2)) for r in sorted(report, key=lambda r: r[1])[:5]])
print('가장 긴 5개:', [(r[0], round(r[1], 2)) for r in sorted(report, key=lambda r: -r[1])[:5]])
(DBG := pathlib.Path('/tmp/gl/hg')).mkdir(parents=True, exist_ok=True)
(DBG / 'voice_words.json').write_text(json.dumps(words), encoding='utf-8')
