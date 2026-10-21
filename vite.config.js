import { defineConfig } from 'vite';

// The game is plain HTML/CSS/JS (the Claude artifact export); Vite only serves it with live reload.
// no-store: the browser always gets the newest files, so a normal refresh shows every change.
export default defineConfig({
  server: { port: 5181, headers: { 'Cache-Control': 'no-store' } },
  preview: { port: 5181 },
});
