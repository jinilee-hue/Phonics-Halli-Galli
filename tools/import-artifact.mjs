#!/usr/bin/env node
// 원본 가져오기: Claude 아티팩트 → 공유 → 내보내기 → HTML 로 받은 파일을 이 프로젝트에 넣습니다.
//
//   node tools/import-artifact.mjs                    ← 다운로드 폴더에서 가장 최근 할리갈리 HTML을 찾아서
//   node tools/import-artifact.mjs ~/Downloads/x.html ← 파일을 직접 지정
//   node tools/import-artifact.mjs --replace          ← 작업본(index.html, src/)을 새 원본으로 덮어쓰기
//
// 1. 받은 파일을 original/ 에 날짜를 붙여 그대로 보관합니다. (수정 금지, 비교 기준)
// 2. 작업본이 아직 없을 때만 원본을 나눠서 작업본을 만듭니다.
//      <style>  → src/style.css
//      <script> → src/main.js
//      나머지   → index.html
//    작업본이 이미 있으면 건드리지 않고, 이전 원본과 달라진 줄 수만 알려 줍니다.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const DL = path.join(os.homedir(), 'Downloads');
const ORIG = path.join(ROOT, 'original');
const args = process.argv.slice(2);
const replace = args.includes('--replace');
const fileArg = args.find(a => !a.startsWith('--'));

function newestCandidate() {
  const recent = fs.readdirSync(DL)
    .filter(f => /\.html?$/i.test(f))
    .map(f => ({ f: path.join(DL, f), t: fs.statSync(path.join(DL, f)).mtimeMs }))
    .filter(x => Date.now() - x.t < 3 * 24 * 3600 * 1000)
    .sort((a, b) => b.t - a.t);
  const looksRight = x => /hall?i|galli|할리|갈리/i.test(path.basename(x.f)) ||
    /hall?i\s*galli|할리\s*갈리/i.test(fs.readFileSync(x.f, 'utf8').slice(0, 4000));
  return (recent.find(looksRight) || {}).f;
}

/* <style> and inline <script> blocks move to their own files; everything else stays in index.html */
function split(html) {
  const styles = [];
  let out = html.replace(/<style[^>]*>([\s\S]*?)<\/style>[ \t]*\n?/gi, (m, css) => {
    styles.push(css.replace(/^\n/, ''));
    return styles.length === 1 ? '<link rel="stylesheet" href="/src/style.css" />\n' : '';
  });
  const scripts = [];
  out = out.replace(/<script(?![^>]*\bsrc=)(?![^>]*\btype=["'](?:module|application\/(?:ld\+)?json)["'])[^>]*>([\s\S]*?)<\/script>[ \t]*\n?/gi,
    (m, js) => { scripts.push(js.replace(/^\n/, '')); return '\u0000SCRIPT\u0000'; });
  const last = out.lastIndexOf('\u0000SCRIPT\u0000');
  out = out.replace(/\u0000SCRIPT\u0000/g, (m, off) => off === last ? '<script type="module" src="/src/main.js"></script>\n' : '');
  return { html: out, css: styles.join('\n'), js: scripts.join('\n') };
}

const src = fileArg ? path.resolve(fileArg.replace(/^~/, os.homedir())) : newestCandidate();
if (!src || !fs.existsSync(src)) {
  console.error('가져올 HTML을 찾지 못했어요. Claude에서 공유 → 내보내기 → HTML로 받은 뒤 다시 실행하거나, 파일 경로를 붙여 주세요.');
  process.exit(1);
}
const html = fs.readFileSync(src, 'utf8');
const hash = crypto.createHash('sha1').update(html).digest('hex').slice(0, 8);
fs.mkdirSync(ORIG, { recursive: true });

// 1) keep the original (skip if the same file is already kept)
const kept = fs.readdirSync(ORIG).filter(f => /\.html?$/i.test(f)).sort();
const same = kept.find(f => crypto.createHash('sha1').update(fs.readFileSync(path.join(ORIG, f))).digest('hex').slice(0, 8) === hash);
const prev = kept.filter(f => f !== same).pop();
let keep;
if (same) {
  keep = path.join(ORIG, same);
  console.log('같은 원본이 이미 있어요 →', path.relative(ROOT, keep));
} else {
  const d = new Date();
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}_${String(d.getHours()).padStart(2, '0')}${String(d.getMinutes()).padStart(2, '0')}`;
  keep = path.join(ORIG, `${stamp}_${path.basename(src)}`);
  fs.copyFileSync(src, keep);
  console.log('원본 보관 →', path.relative(ROOT, keep));
}

// 2) working copy
const working = fs.existsSync(path.join(ROOT, 'src', 'main.js'));
if (!working || replace) {
  const { html: page, css, js } = split(html);
  const from = path.relative(ROOT, keep);
  fs.mkdirSync(path.join(ROOT, 'src'), { recursive: true });
  fs.writeFileSync(path.join(ROOT, 'index.html'), page);
  fs.writeFileSync(path.join(ROOT, 'src', 'style.css'), `/* 원본: ${from} 의 <style> */\n${css}`);
  fs.writeFileSync(path.join(ROOT, 'src', 'main.js'), `// 원본: ${from} 의 <script>\n${js}`);
  console.log(`작업본 ${working ? '덮어씀' : '만듦'} → index.html, src/style.css (${css.split('\n').length}줄), src/main.js (${js.split('\n').length}줄)`);
} else if (!same) {
  console.log('작업본(index.html, src/)은 그대로 두었어요. 새 원본의 내용을 작업본에 옮기려면 아래 차이를 보고 반영하세요.');
  if (prev) {
    let diff = '';
    try { execFileSync('diff', ['-u', path.join(ORIG, prev), keep], { encoding: 'utf8' }); }
    catch (e) { diff = e.stdout || ''; }
    const add = (diff.match(/^\+(?!\+\+)/gm) || []).length, del = (diff.match(/^-(?!--)/gm) || []).length;
    console.log(`이전 원본(${prev})과 비교: +${add}줄 / -${del}줄`);
    console.log(`자세히: diff -u "original/${prev}" "${path.relative(ROOT, keep)}"`);
  }
}
console.log('\n실행: 실행.command 더블클릭, 또는 npm run dev → http://localhost:5181');
