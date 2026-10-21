# Phonics Halli Galli

**공유 주소: https://jinilee-hue.github.io/Phonics-Halli-Galli/**
(GitHub Pages — main 브랜치에 푸시하면 1~2분 뒤 이 주소에 반영돼요)

파닉스 할리갈리 게임을 업그레이드하는 작업 폴더입니다.

- 원본: Claude 아티팩트 "Phonics Halli Galli — Coco" (공유 → 내보내기 → HTML)
- 원본은 `original/`에 받은 그대로 두고, 고치는 작업은 `index.html`과 `src/`에서만 합니다.

## 실행

- `실행.command`를 더블클릭하면 브라우저가 열립니다 → http://localhost:5181
  (처음 한 번은 패키지 설치로 1분쯤 걸려요. 이미 켜져 있으면 브라우저만 새로 열어요)
- `index.html`을 더블클릭해도 게임이 돌아가요 (서버 없이)
- 화면이 예전 그대로면 브라우저에서 새로고침(⌘R)
- 태블릿에서 보기: `npm run dev -- --host` 로 켠 뒤, 같은 와이파이의 태블릿에서 화면에 나온 Network 주소로 접속

## 카드 단어 = 교재 낱말

카드 단어는 연구팩 **필수 문법 27 v0.26**(다운로드 폴더 `2026_1018_1-1. 최종- Essential_Grammar_27_v0.26`)에서 뽑습니다.

```
python3 tools/build_words.py --write   # 연구팩 → src/words.js
```

| 단계 | 교재 | 쓰는 낱말 |
|---|---|---|
| 1단계 · 5세 | SAD K · FPR K | NP-01 규칙 복수형 -s 낱말 (cats, crackers, hats …) |
| 2단계 · 6세 | SAD A · FPR A | NP-01 낱말을 짝으로 (cat / cats) |
| 3단계 · 7세 | SAD B · FPR B | -es 짝 (box / boxes) + s로 끝나는 단수 함정 (bus, class, grass …) + -s 낱말 |

- 출처 시트: `1-1 › 16 단어별 과정별`(기준 1 · 나온 낱말 전부), 함정 낱말은 `3-2 › 09_문장별 학습 단계`의 7세 교재 문장
- 판마다 단계 목록에서 새로 뽑아 덱을 만듭니다.
- 빼는 낱말과 이유는 `tools/build_words.py`의 `EXCLUDE`에 있고, `src/words.js`의 `excluded`에도 남습니다.
- 그림 자리 한글 뜻(고양이 여러 마리 …)은 `KO`에서 정합니다.

## 원본 다시 받기

Claude에서 아티팩트를 고친 뒤 다시 HTML로 받았다면:

```
node tools/import-artifact.mjs            # original/에 새 원본 보관 + 이전 원본과 달라진 줄 수 알려 줌
node tools/import-artifact.mjs --replace  # 작업본을 새 원본으로 덮어쓰기 (작업한 내용이 사라지니 주의)
```

## 구조

| 경로 | 내용 |
|---|---|
| `original/` | 원본 아티팩트 (수정 금지, 비교 기준) |
| `index.html` | 화면 구조 (원본 HTML + 인트로 · BI · 결과 화면) |
| `src/style.css` | 원본의 `<style>` (그대로) |
| `src/upgrade.css` | 업그레이드 스타일 — 인트로 영상, BI 로고, 결과 화면 |
| `src/main.js` | 게임 로직 (원본의 `<script>`) — 단어는 `words.js`, 결과는 `result.js`, 시작은 `intro.js` |
| `src/intro.js` | 인트로 영상 재생 → 끝나거나 SKIP하면 시작 화면 |
| `src/result.js` | 결과 화면: 왼쪽 승패 · 오른쪽 우리 반 순위 (반 친구 기록은 예시, 연동 전) |
| `src/words.js` | 카드 단어 (자동 생성, 직접 고치지 않음) |
| `tools/build_words.py` | 연구팩 → `src/words.js` |
| `tools/import-artifact.mjs` | 원본 가져오기 |
| `assets/intro.mp4` | 인트로 영상 |
| `assets/bi.png` | 시작 화면 BI |
| `assets/bg_box.png` | 게임 화면 테두리 그림 (지금은 쓰지 않음) |
| `assets/bell.png` | 가운데 종 그림 (그림자는 그림에 붙이지 않고 탁자에 따로 깔아요) |
| `assets/start_btn.png` | 시작 화면 START 버튼 그림 |
| `assets/card/` | 5세(1단계) 카드 그림 원본 34장 (`card_낱말.png`, 하나/여럿) |
| `assets/card_web/` | 게임용 카드 사본 (모서리 투명 처리 · 600×800 WebP). `tools/build_cards.py`가 원본에서 만들어요 |
| `src/cards.js` | 그림이 있는 낱말 목록 (자동 생성) |
| `assets/bgm_loop.wav` | 배경음악 (인트로 영상 음악에서 목소리를 빼고 4마디를 이음새 없이 자른 것, 7.6초) |
| `src/bgm-data.js` | 위 음악을 글자로 넣은 파일 (더블클릭 실행용, 자동 생성) |
| `src/bgm.js` | 배경음악 재생: 시작 화면 · 게임 화면에서 크기만 바꿔 끊김 없이 이어짐, 낱말 읽을 때 줄어듦, 소리 버튼으로 같이 꺼짐 |
| `tools/bgm/` | 배경음악 만드는 스크립트 (목소리 분리 → 반복 구간 자르기 → 크기 맞춤) |
| `assets/bell_old.png` | 예전 종 그림 (지금은 `assets/bell.png`가 새 종) |
| `src/orbit.js` | 시작 화면: 5세 카드 6장이 종 둘레를 빙글빙글 돌고, 가끔 뒤집혀 카드 뒷면(`my_card` · `coco_card`)이 보여요 |
| `src/bell-face.js` | 종 표정과 몸짓 (인트로 영상 참고): 깜빡 · 윙크 · 누르면 꾹 눈 감고 납작 + 소리 물결 · 맞으면 활짝 · 틀리면 '앗' |
| `assets/bell_parts/` · `src/bell-parts.js` | 종 그림에서 떼어 낸 얼굴 조각(눈 · 입 · 볼터치)과 위치. `tools/build_bell_parts.py`가 만들어요 — 종 그림을 바꾸면 다시 돌리기 |
| `docs/카드_낱말_목록.xlsx` | 게임 카드 낱말 목록 (단계별 · 나온 쪽 · 뺀 낱말과 이유) |
| `tools/export_words.py` | 위 엑셀을 `src/words.js`에서 다시 만드는 스크립트 |
| `실행.command` | 더블클릭 실행 |

## 정해 둔 것

- Coco 모습: 꼬마종 (`index.html`의 `data-look="bell"`). 모습 고르기 버튼은 뺐어요.
- 인트로: 브라우저가 소리 있는 자동재생을 막으면 소리 없이 재생해요. 화면을 누르면 소리가 켜져요 (소리 켜기 버튼은 없음).
- 결과 순위: 모은 S가 많은 순, 같으면 빠른 순. '나'만 실제 기록이고 반 친구 11명은 예시예요.
- 단계 고르기: 지금은 숨김 → 늘 1단계(5세). 다시 보이게 하려면 `src/upgrade.css`의 `.level{ display:none; }` 한 줄을 지워요.
- 소리: 오른쪽 위 스피커를 누르면 세로 소리 막대가 내려와요 (맨 아래 = 끔). 시작 화면에도 있고, 고른 크기는 기기에 기억돼요.
