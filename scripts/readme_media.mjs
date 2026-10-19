// Render the README media (animated GIFs + screenshots) from docs/index.html.
//
// Drives headless Chrome over the DevTools protocol (no extra npm packages; Node >= 22 for the
// built-in WebSocket). The page's requestAnimationFrame clock is replaced with a manual one, so every
// GIF frame advances the animation by exactly 1/FPS second no matter how long a screenshot takes.
// GIFs are encoded with ffmpeg (palettegen/paletteuse).
//
// Usage:  node scripts/readme_media.mjs
// Env:    CHROME=path/to/chrome   FFMPEG=path/to/ffmpeg   FPS=30
import { spawn, execFileSync } from 'node:child_process';
import { mkdirSync, rmSync, writeFileSync, existsSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';

const ROOT = resolve(import.meta.dirname, '..');
const OUT = join(ROOT, 'assets', 'readme');
const FRAMES = join(ROOT, 'build', 'readme_frames');
const PAGE = pathToFileURL(join(ROOT, 'docs', 'index.html')).href;
const CHROME = process.env.CHROME || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
].find(p => existsSync(p));
const FFMPEG = process.env.FFMPEG || 'ffmpeg';
const FPS = +(process.env.FPS || 30);
const PORT = 9333;
const sleep = ms => new Promise(r => setTimeout(r, ms));

// manual animation clock + language/theme, injected before the page's own scripts
const preload = (theme) => `
  try { localStorage.setItem('enso-atlas-lang', 'en'); localStorage.setItem('enso-atlas-theme', '${theme}'); } catch (e) {}
  (() => { let id = 0, t = 0; const q = new Map();
    window.requestAnimationFrame = cb => { q.set(++id, cb); return id; };
    window.cancelAnimationFrame = i => q.delete(i);
    window.__step = dt => { t += dt; const cbs = [...q.values()]; q.clear(); cbs.forEach(cb => cb(t)); };
  })();`;

async function chrome() {
  const dir = join(tmpdir(), 'enso-readme-chrome'); rmSync(dir, { recursive: true, force: true });
  const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--hide-scrollbars', `--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`, 'about:blank'], { stdio: 'ignore' });
  for (let i = 0; i < 50; i++) {
    try { const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const pg = list.find(t => t.type === 'page'); if (pg) return { proc, ws: pg.webSocketDebuggerUrl }; } catch (e) {}
    await sleep(200);
  }
  throw new Error('Chrome did not start');
}

function cdp(url) {
  const ws = new WebSocket(url); let id = 0; const pending = new Map(), waiters = [];
  ws.onmessage = ev => { const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(m.error.message)) : res(m.result); }
    else if (m.method) waiters.filter(w => w.method === m.method).forEach(w => { waiters.splice(waiters.indexOf(w), 1); w.res(m.params); }); };
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
  const once = method => new Promise(res => waiters.push({ method, res }));
  return new Promise(r => { ws.onopen = () => r({ send, once, close: () => ws.close() }); });
}

async function openPage(c, theme, width = 1240, height = 900) {
  await c.send('Page.enable'); await c.send('Runtime.enable');
  await c.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
  const { identifier } = await c.send('Page.addScriptToEvaluateOnNewDocument', { source: preload(theme) });
  const loaded = c.once('Page.loadEventFired'); await c.send('Page.navigate', { url: PAGE }); await loaded;
  await sleep(2500);                                    // fonts + d3 from CDN
  await c.send('Page.removeScriptToEvaluateOnNewDocument', { identifier });
  await js(c, `document.querySelector('.top').style.display = 'none'`);   // the sticky bar would overlap the clips
}
const js = async (c, expr) => (await c.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result.value;

async function rectOf(c, sel, padTop = 0) {
  // sel: one selector, or [first, last] to clip the union of two elements; section padding is skipped
  const sels = JSON.stringify([].concat(sel));
  return js(c, `(() => { const els = ${sels}.map(s => document.querySelector(s));
    window.scrollTo(0, els[0].getBoundingClientRect().top + scrollY - 70 - ${padTop});
    const rs = els.map(e => { const r = e.getBoundingClientRect(), pt = e.tagName === 'SECTION' ? parseFloat(getComputedStyle(e).paddingTop) : 0;
      return { l: r.left, t: r.top + pt, r: r.right, b: r.bottom }; });
    const l = Math.min(...rs.map(r => r.l)), t = Math.min(...rs.map(r => r.t)), r = Math.max(...rs.map(r => r.r)), b = Math.max(...rs.map(r => r.b));
    return { x: Math.round(l + scrollX), y: Math.round(t + scrollY - ${padTop}), width: Math.round(r - l), height: Math.round(b - t + ${padTop}) }; })()`);
}
async function shot(c, clip, file) {
  const { data } = await c.send('Page.captureScreenshot', { format: 'png', clip: { ...clip, scale: 1 }, captureBeyondViewport: true });
  writeFileSync(file, Buffer.from(data, 'base64'));
}

// record `seconds` of animation; `events` = [[atSecond, jsExpression], ...]
async function record(c, name, sel, seconds, events = [], padTop = 0) {
  const dir = join(FRAMES, name); rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
  const clip = await rectOf(c, sel, padTop);
  for (let i = 0; i < 6; i++) { await js(c, `__step(${1000 / FPS})`); await sleep(30); }   // let observers start the loops
  const n = Math.round(seconds * FPS); let ev = 0;
  for (let f = 0; f < n; f++) {
    while (ev < events.length && events[ev][0] * FPS <= f) await js(c, events[ev++][1]);
    await js(c, `__step(${1000 / FPS})`);
    await shot(c, clip, join(dir, `f${String(f).padStart(4, '0')}.png`));
  }
  const gif = join(OUT, `${name}.gif`);
  execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', join(dir, 'f%04d.png'),
    '-vf', 'split[a][b];[a]palettegen=stats_mode=diff:max_colors=192[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle',
    '-loop', '0', gif]);
  console.log(`${name}.gif  ${n} frames @ ${FPS} fps  ${(statSync(gif).size / 1e6).toFixed(1)} MB  ${clip.width}x${clip.height}`);
}

async function still(c, name, sel, padTop = 0, before = '') {
  if (before) { await js(c, before); for (let i = 0; i < 4; i++) { await js(c, `__step(${1000 / FPS})`); await sleep(40); } }
  const clip = await rectOf(c, sel, padTop); await sleep(150);
  for (let i = 0; i < 3; i++) { await js(c, `__step(${1000 / FPS})`); await sleep(40); }
  await shot(c, clip, join(OUT, `${name}.png`)); console.log(`${name}.png  ${clip.width}x${clip.height}`);
}

mkdirSync(OUT, { recursive: true });
const { proc, ws } = await chrome();
try {
  const c = await cdp(ws);
  const preset = p => `document.querySelector('#chips [data-p="${p}"]').click()`;
  for (const theme of ['dark', 'light']) {
    await openPage(c, theme);
    // hero: all seasons -> La Nina -> El Nino, with the HUD numbers updating
    await record(c, `hero-${theme}`, '.deck', 7.5, [[0, preset('all')], [2.5, preset('nina')], [5, preset('nino')]]);
  }
  await openPage(c, 'dark');
  await record(c, 'replay', '.rp', 8, [[0, `document.getElementById('s8').click(); document.querySelector('#rpChips [data-y="2020"]').click()`]]);
  await still(c, 'calendar', ['#calCount', '#calLeg']);
  await still(c, 'duel', '#duel');
  await still(c, 'wipe', '#wipeMap');
  await still(c, 'scale', '#catScale');
  await still(c, 'types', '#types');
  await still(c, 'decomposition', '.grid4');
  c.close();
} finally { proc.kill(); }
