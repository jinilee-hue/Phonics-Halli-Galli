#!/bin/bash
# 더블클릭하면 게임을 켜고 브라우저를 엽니다. 처음 한 번은 패키지를 설치합니다.
# 이미 켜져 있으면 새로 켜지 않고, 브라우저만 최신 화면으로 엽니다.
cd "$(dirname "$0")" || exit 1
URL="http://localhost:5181/?v=$(date +%s)"

if curl -s -o /dev/null --max-time 1 http://localhost:5181/; then
  open "$URL"
  exit 0
fi

# npm 찾기: 기본 PATH → Homebrew → /usr/local → ~/.local → Hermes에 들어 있는 Node
for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin" "$HOME/.hermes/node/bin"; do
  command -v npm >/dev/null 2>&1 && break
  [ -x "$d/npm" ] && export PATH="$d:$PATH"
done
if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js(npm)를 찾지 못했어요. 대신 index.html을 더블클릭해서 열어도 게임이 돌아가요."
  read -r -n 1 -p "아무 키나 누르면 닫혀요."
  exit 1
fi
if [ "$1" = "--check" ]; then
  echo "npm: $(command -v npm) ($(npm -v))"
  exit 0
fi

if [ ! -d node_modules ]; then
  npm install || { read -r -n 1 -p "설치에 실패했어요. 아무 키나 누르면 닫혀요."; exit 1; }
fi
( sleep 2; open "$URL" ) &
npm run dev -- --port 5181 --strictPort
