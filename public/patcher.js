// ─────────────────────────────────────────────
//  JV Patcher — pure-JS MP4 atom patcher
//  No FFmpeg. No re-encoding. Instant.
// ─────────────────────────────────────────────

let selectedFile = null;
let detectedFps  = 0;

// ── Logging ───────────────────────────────────
function log(msg, type = 'info') {
  const body = document.getElementById('logBody');
  const now  = new Date();
  const t    = [now.getHours(), now.getMinutes()]
    .map(n => String(n).padStart(2, '0')).join(':');
  const el   = document.createElement('div');
  el.className = 'log-line ' + type;
  el.innerHTML = `<span class="t">${t}</span><span class="m">${msg}</span>`;
  body.appendChild(el);
  body.scrollTop = body.scrollHeight;
  if (type === 'active') {
    document.getElementById('logDot').className = 'log-dot active';
  } else if (type === 'ok' || type === 'err') {
    document.getElementById('logDot').className = 'log-dot';
  }
}

function setProgress(pct, msg) {
  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressLabel').textContent = msg;
}

// ── File handling ─────────────────────────────
const dropZone  = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', e => {
  if (e.target.files[0]) handleFile(e.target.files[0]);
});

window.clearFile = function () {
  selectedFile = null;
  detectedFps  = 0;
  document.getElementById('fileInfo').classList.remove('show');
  document.getElementById('downloadSection').classList.remove('show');
  document.getElementById('progressSection').classList.remove('show');
  document.getElementById('patchBtn').disabled = true;
  fileInput.value = '';
  log('File cleared', 'info');
};

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith('.mp4')) {
    log('Only .mp4 files supported', 'err');
    return;
  }
  selectedFile = file;
  document.getElementById('downloadSection').classList.remove('show');
  document.getElementById('progressSection').classList.remove('show');
  document.getElementById('fileName').textContent  = file.name;
  document.getElementById('fileSize').textContent  = (file.size / 1024 / 1024).toFixed(2) + ' MB';
  document.getElementById('fileFps').textContent   = 'detecting...';
  document.getElementById('fileInfo').classList.add('show');
  document.getElementById('patchBtn').disabled = false;

  try {
    const fps = await detectFpsNative(file);
    detectedFps = fps;
    document.getElementById('fileFps').textContent = fps + ' FPS detected';
    log(`Loaded: ${file.name} — ${fps} FPS`, 'info');
  } catch (e) {
    detectedFps = 0;
    document.getElementById('fileFps').textContent = 'FPS unknown';
    log(`Loaded: ${file.name}`, 'info');
  }
}

// ── Fast native FPS detection ─────────────────
async function detectFpsNative(file) {
  const parts = [file.slice(0, Math.min(file.size, 1024 * 1024))];
  if (file.size > 1024 * 1024) {
    const tailStart = Math.max(1024 * 1024, file.size - 3 * 1024 * 1024);
    parts.push(file.slice(tailStart));
  }
  const buffers = await Promise.all(parts.map(p => p.arrayBuffer()));
  const total   = buffers.reduce((s, b) => s + b.byteLength, 0);
  const data    = new Uint8Array(total);
  let offset = 0;
  for (const b of buffers) { data.set(new Uint8Array(b), offset); offset += b.byteLength; }

  const r32 = (d, o) => ((d[o] << 24) | (d[o+1] << 16) | (d[o+2] << 8) | d[o+3]) >>> 0;

  function findAll(d, name) {
    const enc = new TextEncoder().encode(name);
    const out = [];
    for (let i = 0; i <= d.length - enc.length; i++) {
      let ok = true;
      for (let j = 0; j < enc.length; j++) {
        if (d[i + j] !== enc[j]) { ok = false; break; }
      }
      if (ok) out.push(i);
    }
    return out;
  }

  for (const trakPos of findAll(data, 'trak')) {
    const boxStart = trakPos - 4;
    if (boxStart < 0) continue;
    const boxSize = r32(data, boxStart);
    if (boxSize < 8 || boxStart + boxSize > data.length) continue;
    const trak = data.slice(boxStart, boxStart + boxSize);

    let isVideo = false;
    for (const hp of findAll(trak, 'hdlr')) {
      if (hp + 16 <= trak.length) {
        const ht = String.fromCharCode(trak[hp+12], trak[hp+13], trak[hp+14], trak[hp+15]);
        if (ht === 'vide') { isVideo = true; break; }
      }
    }
    if (!isVideo) continue;

    let timescale = 0;
    for (const mp of findAll(trak, 'mdhd')) {
      const ver = trak[mp + 4];
      timescale = (ver === 0) ? r32(trak, mp + 16) : r32(trak, mp + 24);
      if (timescale > 0) break;
    }
    if (!timescale) continue;

    for (const sp of findAll(trak, 'stts')) {
      const count = r32(trak, sp + 8);
      if (count === 0 || count > 500) continue;
      const delta = r32(trak, sp + 16);
      if (delta > 0) {
        const fps = timescale / delta;
        if (fps >= 1 && fps <= 360) return Math.round(fps * 100) / 100;
      }
    }
    for (const fps of [240, 120, 90, 60, 50, 48, 30, 25, 24]) {
      if (timescale % fps === 0) return fps;
    }
  }
  return 30;
}

// ── Pure-JS MP4 Atom Patcher ──────────────────
async function patchMp4Atoms(arrayBuffer, targetFps) {
  const data = new Uint8Array(arrayBuffer);

  const r32 = (d, o) => ((d[o] << 24) | (d[o+1] << 16) | (d[o+2] << 8) | d[o+3]) >>> 0;
  const w32 = (d, o, v) => {
    v = v >>> 0;
    d[o]   = (v >> 24) & 0xff;
    d[o+1] = (v >> 16) & 0xff;
    d[o+2] = (v >>  8) & 0xff;
    d[o+3] =  v        & 0xff;
  };

  function findAll(d, name, start, end) {
    const enc = new TextEncoder().encode(name);
    const out = [];
    end = Math.min(end || d.length, d.length);
    for (let i = start || 0; i <= end - enc.length; i++) {
      let ok = true;
      for (let j = 0; j < enc.length; j++) {
        if (d[i + j] !== enc[j]) { ok = false; break; }
      }
      if (ok) out.push(i);
    }
    return out;
  }

  let patchCount = 0;

  for (const trakPos of findAll(data, 'trak')) {
    const boxStart = trakPos - 4;
    if (boxStart < 0) continue;
    const boxSize = r32(data, boxStart);
    if (boxSize < 8 || boxStart + boxSize > data.length) continue;

    let isVideo = false;
    for (const hp of findAll(data, 'hdlr', boxStart, boxStart + boxSize)) {
      if (hp + 16 <= boxStart + boxSize) {
        const ht = String.fromCharCode(data[hp+12], data[hp+13], data[hp+14], data[hp+15]);
        if (ht === 'vide') { isVideo = true; break; }
      }
    }
    if (!isVideo) continue;

    let timescale = 0;
    for (const mp of findAll(data, 'mdhd', boxStart, boxStart + boxSize)) {
      const ver = data[mp + 4];
      timescale = (ver === 0) ? r32(data, mp + 16) : r32(data, mp + 24);
      if (timescale > 0) break;
    }
    if (!timescale) continue;

    const newDelta = Math.round(timescale / targetFps);
    if (newDelta <= 0) continue;

    for (const sp of findAll(data, 'stts', boxStart, boxStart + boxSize)) {
      const entryCount = r32(data, sp + 8);
      if (entryCount === 0 || entryCount > 500) continue;
      for (let e = 0; e < entryCount; e++) {
        const deltaOffset = sp + 16 + e * 8;
        if (deltaOffset + 4 <= data.length) {
          w32(data, deltaOffset, newDelta);
          patchCount++;
        }
      }
    }
    log(`Patched stts: timescale=${timescale}, delta=${newDelta} (${targetFps} FPS)`, 'info');
  }

  if (patchCount === 0) throw new Error('No patchable stts entries found in video track');
  return data.buffer;
}

// ── Run Patch ─────────────────────────────────
window.runPatch = async function () {
  if (!selectedFile) return;

  const btn = document.getElementById('patchBtn');
  btn.disabled = true;
  btn.innerHTML = `<svg style="animation:spin 1s linear infinite" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"/></svg> Patching...`;

  document.getElementById('progressSection').classList.add('show');
  document.getElementById('downloadSection').classList.remove('show');
  setProgress(10, 'Reading file...');
  log('Starting patch → 60 FPS', 'active');

  try {
    const t0 = performance.now();

    setProgress(30, 'Reading MP4 into memory...');
    const arrayBuffer = await selectedFile.arrayBuffer();
    log(`Read ${(arrayBuffer.byteLength / 1024 / 1024).toFixed(2)} MB`, 'info');

    setProgress(55, 'Patching MP4 atoms...');
    log('Patching stts sample_delta in video track...', 'info');
    const patched = await patchMp4Atoms(arrayBuffer, 60);

    setProgress(85, 'Building output...');
    const blob = new Blob([patched], { type: 'video/mp4' });
    const url  = URL.createObjectURL(blob);
    const name = selectedFile.name.replace(/\.mp4$/i, '') + '_JV60FPS.mp4';

    const dlBtn  = document.getElementById('downloadBtn');
    dlBtn.href     = url;
    dlBtn.download = name;

    const elapsed = ((performance.now() - t0) / 1000).toFixed(2);
    setProgress(100, `Done in ${elapsed}s`);
    document.getElementById('downloadSection').classList.add('show');
    log(`Done in ${elapsed}s → ${name} (${(blob.size / 1024 / 1024).toFixed(2)} MB)`, 'ok');

  } catch (err) {
    log('Error: ' + err.message, 'err');
    setProgress(0, 'Error — check log');
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"/></svg> Patch to 60 FPS`;
  }
};
