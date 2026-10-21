#!/usr/bin/env python3
"""카드 단어 만들기: 연구팩(필수 문법 27 v0.26)의 교재 출현 낱말 → src/words.js

    python3 tools/build_words.py            # 점검만 (요약 출력)
    python3 tools/build_words.py --write    # src/words.js 쓰기

출처 (다운로드 폴더 '2026_1018_1-1. 최종- Essential_Grammar_27_v0.26')
- 1-1 전과정_필수문법27 v0.26 › '16 단어별 과정별' · 기준 1(나온 낱말 전부) · NP-01 규칙 복수형 -s
  나이 = 교재 등급: 5세 SAD K·FPR K / 6세 SAD A·FPR A / 7세 SAD B·FPR B
- 3-2 문법학습단계 5-7세 v0.5 › '09_문장별 학습 단계' (7세 교재 문장)
  → 3단계 함정 낱말: s로 끝나지만 하나인 명사 (bus, class, grass …)

사람이 정하는 것은 그림 자리 한글 뜻(KO)과 단계별로 빼는 낱말(EXCLUDE, 이유 포함)뿐입니다.
"""
import json, os, re, sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from xlsx_read import sheet  # noqa: E402

SRC = os.path.expanduser('~/Downloads/2026_1018_1-1. 최종- Essential_Grammar_27_v0.26')
if '--src' in sys.argv:
    SRC = sys.argv[sys.argv.index('--src') + 1]
F27 = os.path.join(SRC, '1-1. 최종- SAD_FPR_KAB_전과정_필수문법27_v0.26.xlsx')
FST = os.path.join(SRC, '3-2. SAD_FPR_KAB_SB_문법학습단계_5-7세_v0.5.xlsx')

BOOK_COL = {'SAD K': 6, 'SAD A': 7, 'SAD B': 8, 'FPR K': 9, 'FPR A': 10, 'FPR B': 11}
AGE_OF = {'K': 5, 'A': 6, 'B': 7}
PAGE_RE = re.compile(r'p\.?\s*(\d+)(?:\((\d+)\))?')

# ---------------------------------------------------------------- 그림 자리 한글 뜻: (뜻, 세는 말)
KO = {
    # 5세
    'cat': ('고양이', '마리'), 'cracker': ('크래커', '개'), 'hat': ('모자', '개'), 'bat': ('박쥐', '마리'),
    'bug': ('벌레', '마리'), 'dog': ('강아지', '마리'), 'dot': ('점', '개'), 'egg': ('달걀', '개'),
    'fox': ('여우', '마리'), 'hill': ('언덕', '개'), 'jet': ('제트기', '대'), 'jug': ('물병', '개'),
    'leg': ('다리', '개'), 'lip': ('입술', '개'), 'pan': ('프라이팬', '개'), 'pet': ('반려동물', '마리'),
    'pig': ('돼지', '마리'), 'pot': ('냄비', '개'),
    # 6세
    'bird': ('새', '마리'), 'can': ('깡통', '개'), 'clown': ('광대', '명'), 'coin': ('동전', '개'),
    'kid': ('아이', '명'), 'plant': ('식물', '그루'), 'log': ('통나무', '개'), 'monkey': ('원숭이', '마리'),
    'pup': ('새끼 강아지', '마리'), 'sail': ('돛', '개'), 'seed': ('씨앗', '개'), 'song': ('노래', '곡'),
    'tree': ('나무', '그루'), 'toad': ('두꺼비', '마리'), 'balloon': ('풍선', '개'), 'bean': ('콩', '개'),
    'bear': ('곰', '마리'), 'bike': ('자전거', '대'), 'coat': ('외투', '벌'), 'dollar': ('달러 지폐', '장'),
    'friend': ('친구', '명'), 'frog': ('개구리', '마리'), 'orange': ('오렌지', '개'), 'pea': ('완두콩', '개'),
    'snack': ('과자', '개'), 'sock': ('양말', '짝'), 'squirrel': ('다람쥐', '마리'), 'swing': ('그네', '개'),
    'turtle': ('거북', '마리'), 'ant': ('개미', '마리'), 'bee': ('벌', '마리'), 'bell': ('종', '개'),
    'block': ('블록', '개'), 'car': ('자동차', '대'), 'cave': ('동굴', '개'), 'cloud': ('구름', '개'),
    'crab': ('게', '마리'), 'cup': ('컵', '개'), 'cupcake': ('컵케이크', '개'), 'fan': ('선풍기', '대'),
    'flower': ('꽃', '송이'), 'girl': ('여자아이', '명'), 'glove': ('장갑', '짝'), 'goat': ('염소', '마리'),
    'map': ('지도', '장'), 'mat': ('매트', '장'), 'nut': ('견과', '개'), 'paw': ('동물 발', '개'),
    'pen': ('펜', '자루'), 'rose': ('장미', '송이'), 'shoe': ('신발', '짝'), 'sled': ('썰매', '대'),
    'spot': ('얼룩점', '개'), 'toe': ('발가락', '개'), 'toy': ('장난감', '개'),
}

# ---------------------------------------------------------------- 단계별로 빼는 낱말 (이유)
EXCLUDE = {
    5: {
        'nap': '낮잠은 그림으로 하나·여럿을 보여 주기 어려움',
        'bill': '지폐·새 부리 두 뜻이라 그림이 헷갈림 (같은 쪽에 이름 Bill도 나옴)',
        'fox': '-es 복수는 3단계에서 다룸',
    },
    6: {
        'short': "shorts(반바지)는 늘 여럿 꼴이라 짝 카드 'short'가 성립하지 않음",
        'stair': "stairs(계단)는 거의 늘 여럿 꼴로 씀",
        'day': '그림으로 하나·여럿을 보여 주기 어려움', 'thing': '그림으로 하나·여럿을 보여 주기 어려움',
        'part': '그림으로 하나·여럿을 보여 주기 어려움', 'point': '그림으로 하나·여럿을 보여 주기 어려움',
        'score': '그림으로 하나·여럿을 보여 주기 어려움', 'sport': '그림으로 하나·여럿을 보여 주기 어려움',
        'wood': '그림으로 하나·여럿을 보여 주기 어려움', 'song': '그림으로 하나·여럿을 보여 주기 어려움',
        'box': '-es 복수는 3단계에서 다룸',
    },
    7: {
        'pant': "pants(바지)는 늘 여럿 꼴", 'stair': "stairs(계단)는 거의 늘 여럿 꼴로 씀",
        'lot': "lots는 'lots of'로 쓰는 말이라 셀 수 있는 낱말이 아님",
    },
}
# 3단계 그냥 -s 낱말은 교재에 2번 이상 나온 것만 (연구팩 안내: 최다 빈도 낱말부터 제작)
L3_MIN_N = 2
# 3단계 함정: s로 끝나지만 하나인 명사 후보 (7세 교재 문장에 실제로 나온 것만 남김)
TRAP_CANDIDATES = ['bus', 'class', 'grass', 'mess', 'circus', 'dress', 'glass', 'moss']


def pad(r, n):
    return list(r) + [''] * (n - len(r))


def es_plural(base, plural):
    return plural.lower() == base.lower() + 'es' and re.search(r'(s|x|z|sh|ch)$', base.lower())


# ---------------------------------------------------------------- 1) NP-01 낱말, 나이별
by_age = {5: OrderedDict(), 6: OrderedDict(), 7: OrderedDict()}
for r in sheet(F27, '16 단어별 과정별')[1:]:
    r = pad(r, 14)
    if r[0] != 'NP-01' or not r[2].startswith('1'):
        continue
    base, plural = r[3].strip().lower(), r[4].strip().lower()   # 문장 첫머리 대문자(Toads, Ducks) 정리
    for book, col in BOOK_COL.items():
        cell = r[col]
        if not cell:
            continue
        n = sum(int(m.group(2)) if m.group(2) else 1 for m in PAGE_RE.finditer(cell)) or 1
        w = by_age[AGE_OF[book[-1]]].setdefault(base, {'base': base, 'plural': plural, 'n': 0, 'pages': []})
        w['n'] += n
        w['pages'].append(f'{book} {cell}')

for age in by_age:
    by_age[age] = OrderedDict(sorted(by_age[age].items(), key=lambda kv: (-kv[1]['n'], kv[0])))
src_count = {age: len(by_age[age]) for age in by_age}


def item(w, with_ko):
    out = {'base': w['base'], 'plural': w['plural'], 'n': w['n'], 'src': ' · '.join(w['pages'])}
    if with_ko:
        ko, unit = KO[w['base']]
        out.update(ko=ko, unit=unit)
    return out


def take(age, with_ko, keep=lambda w: True):
    used, dropped = [], []
    for w in by_age[age].values():
        why = EXCLUDE.get(age, {}).get(w['base'])
        if why:
            dropped.append({'w': w['plural'], 'why': why})
        elif keep(w):
            used.append(item(w, with_ko))
    return used, dropped


# 1단계 (5세): 5세 교재 낱말 전부 (-es인 foxes도 5세 교재에 나와서 포함)
l1, l1_out = take(5, True)
# 2단계 (6세): -s 짝(cat / cats)
l2, l2_out = take(6, True, keep=lambda w: not es_plural(w['base'], w['plural']))
# 3단계 (7세): -es 짝 · 함정 · 그냥 -s
l3_es, _ = take(7, False, keep=lambda w: es_plural(w['base'], w['plural']))
l3_regular, l3_out = take(7, False, keep=lambda w: not es_plural(w['base'], w['plural']) and w['n'] >= L3_MIN_N)

missing = [w['base'] for w in l1 + l2 if w['base'] not in KO]
assert not missing, f'한글 뜻(KO)이 없는 낱말: {missing}'

# ---------------------------------------------------------------- 2) 3단계 함정 (7세 교재 문장에서 확인)
sentences = [pad(r, 8) for r in sheet(FST, '09_문장별 학습 단계')[1:]]
b_sentences = [r for r in sentences if r[0].endswith(' B')]
traps = []
for t in TRAP_CANDIDATES:
    hits = [r for r in b_sentences if re.search(r'\b' + t + r'\b', r[5], re.I)]
    # 동사로 쓰인 문장(cross, pass 같은)은 후보에서 이미 뺐고, 명사로 쓴 문장만 남도록 a/the/our/his 뒤를 우선
    if not hits:
        continue
    plural = t + 'es'
    p_hits = [r for r in b_sentences if re.search(r'\b' + plural + r'\b', r[5], re.I)]
    ex = hits[0]
    traps.append({'w': t, 'n': len(hits), 'src': f"{ex[0]} p.{ex[3]}", 'sentence': ex[5].strip(),
                  # 짝 카드(buses처럼)는 7세 교재 문장에 나온 경우만
                  **({'plural': plural, 'pluralSrc': f"{p_hits[0][0]} p.{p_hits[0][3]}"} if p_hits and plural not in ('glasses',) else {})})
traps.sort(key=lambda t: -t['n'])

data = OrderedDict(
    source=OrderedDict(
        pack='필수 문법 27 × 6과정 출현 낱말 분석 v0.26 (2026-10-18)',
        sheet="1-1 › 16 단어별 과정별 · 기준 1(나온 낱말 전부) · NP-01 규칙 복수형 -s",
        traps="3-2 문법학습단계 v0.5 › 09_문장별 학습 단계 (7세 SAD B · FPR B 문장)",
        level3Regular=f"7세 그냥 -s 낱말은 교재 출현 {L3_MIN_N}번 이상만",
        books={'5': 'SAD K · FPR K', '6': 'SAD A · FPR A', '7': 'SAD B · FPR B'},
        counts={str(a): src_count[a] for a in src_count},
    ),
    level1=OrderedDict(age=5, words=l1, excluded=l1_out),
    level2=OrderedDict(age=6, words=l2, excluded=l2_out),
    level3=OrderedDict(age=7, es=l3_es, traps=traps, regular=l3_regular, excluded=l3_out),
)

# ---------------------------------------------------------------- report
print(f"교재 NP-01 낱말: 5세 {src_count[5]} · 6세 {src_count[6]} · 7세 {src_count[7]}")
print(f"1단계 {len(l1)}개 (뺀 것 {len(l1_out)}: {', '.join(x['w'] for x in l1_out)})")
print('   ', ', '.join(f"{w['plural']}({w['n']})" for w in l1))
print(f"2단계 {len(l2)}개 (뺀 것 {len(l2_out)}: {', '.join(x['w'] for x in l2_out)})")
print('   ', ', '.join(f"{w['plural']}({w['n']})" for w in l2))
print(f"3단계 -es {len(l3_es)}: {', '.join(w['plural'] for w in l3_es)}")
trap_txt = ', '.join(t['w'] + ('/' + t['plural'] if 'plural' in t else '') + '(%d)' % t['n'] for t in traps)
print(f"      함정 {len(traps)}: {trap_txt}")
print(f"      그냥 -s {len(l3_regular)} (교재 {L3_MIN_N}번 이상 · 뺀 것: {', '.join(x['w'] for x in l3_out)})")
print('   ', ', '.join(f"{w['plural']}({w['n']})" for w in l3_regular))

if '--write' in sys.argv:
    out = os.path.join(ROOT, 'src', 'words.js')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('// tools/build_words.py 가 연구팩에서 만든 파일입니다. 직접 고치지 말고 스크립트를 다시 돌리세요.\n')
        f.write('// 파일을 더블클릭해 열어도(file://) 돌아가도록 모듈이 아닌 전역 변수로 둡니다.\n')
        f.write('window.WORDS = ')
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write(';\n')
    print('wrote', os.path.relpath(out, ROOT), os.path.getsize(out), 'bytes')
