/* ════════════════════════════════════════════
   Music DL — Renderer
═══════════════════════════════════════════════ */
'use strict';

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

/* ── État global ── */
let appState = { version: '', settings: {}, library: [], playlists: [], recents: [] };
let searchResults = [];
let lastSearchError = null;
let lastDlError = null;
let queueSnap = [];
let currentPage = 0;
let currentPlId = null;
let online = navigator.onLine;

/* État lecteur */
const audio = $('#audio');
let playQueue = [];      // ids
let playPos = -1;
let shuffleOn = false;
let repeatMode = 0;      // 0:off 1:all 2:one
let currentTrack = null;

/* ── Helpers ── */
const escMap = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => escMap[c]);
const local = (p) => 'mdl://local/?p=' + encodeURIComponent(p);
const fmtDur = (s) => {
  if (s == null || isNaN(s)) return '—';
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`;
};
const fmtDurLong = (total) => {
  total = Math.round(total || 0);
  const h = Math.floor(total / 3600), m = Math.round((total % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, '0')}min` : `${m}min`;
};
const fmtViews = (n) => {
  if (!n) return null;
  if (typeof n === 'string') return n;
  return new Intl.NumberFormat('fr-FR', { notation: 'compact', maximumFractionDigits: 1 }).format(n) + ' vues';
};
const SVG_NOTE = (sz, op) => `<svg width="${sz}" height="${sz}" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,${op})" stroke-width="1.5" stroke-linecap="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;
const T_CLASSES = ['t1', 't2', 't3', 't4', 't5', 't6', 't7', 't8'];
const tClass = (i) => T_CLASSES[i % T_CLASSES.length];
const trackById = (id) => appState.library.find((t) => t.id === id);

/* ── Toasts ── */
function showToast(msg, type) {
  const wrap = $('#toast-wrap');
  const t = document.createElement('div');
  t.className = 'toast ' + (type || 'info');
  const icons = {
    success: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>',
    error: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    info: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
  };
  t.innerHTML = `<div class="toast-ico">${icons[type] || icons.info}</div><span>${esc(msg)}</span>`;
  wrap.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 280); }, 3200);
}

/* ── Fenêtre ── */
$('#dot-close').addEventListener('click', () => window.mdl.close());
$('#dot-min').addEventListener('click', () => window.mdl.minimize());
$('#dot-max').addEventListener('click', () => window.mdl.maximize());

/* ── Navigation ── */
function goPage(n) {
  currentPage = n;
  [0, 1, 2].forEach((i) => {
    $('#ni' + i).classList.toggle('on', i === n);
    $('#pg' + i).classList.toggle('on', i === n);
  });
}
$$('.ni').forEach((el) => el.addEventListener('click', () => goPage(+el.dataset.page)));
$('#goto-search-btn').addEventListener('click', () => goPage(0));

/* ── Modals génériques ── */
$$('[data-close]').forEach((b) => b.addEventListener('click', () => $('#' + b.dataset.close).classList.remove('on')));
$$('.modal-back').forEach((m) => m.addEventListener('click', (e) => { if (e.target === m) m.classList.remove('on'); }));

let inputModalCb = null;
function askInput({ title, label, value, okLabel }, cb) {
  $('#input-modal-title').textContent = title;
  $('#input-modal-label').textContent = label;
  $('#input-modal-ok').textContent = okLabel || 'Valider';
  const f = $('#input-modal-field');
  f.value = value || '';
  inputModalCb = cb;
  $('#input-modal').classList.add('on');
  setTimeout(() => f.focus(), 60);
}
$('#input-modal-ok').addEventListener('click', submitInputModal);
$('#input-modal-field').addEventListener('keydown', (e) => { if (e.key === 'Enter') submitInputModal(); });
function submitInputModal() {
  const v = $('#input-modal-field').value.trim();
  if (!v) return;
  $('#input-modal').classList.remove('on');
  if (inputModalCb) inputModalCb(v);
}

let confirmCb = null;
function askConfirm({ title, html, okLabel }, cb) {
  $('#confirm-title').textContent = title || 'Confirmer';
  $('#confirm-text').innerHTML = html;
  $('#confirm-ok').textContent = okLabel || 'Supprimer';
  confirmCb = cb;
  $('#confirm-modal').classList.add('on');
}
$('#confirm-ok').addEventListener('click', () => {
  $('#confirm-modal').classList.remove('on');
  if (confirmCb) confirmCb();
});

/* ── Menu contextuel (ajouter à une playlist) ── */
const ctxMenu = $('#ctx-menu');
function openPlaylistMenu(anchor, trackId) {
  const items = appState.playlists.map((p) =>
    `<div class="ctx-item" data-pl="${esc(p.id)}">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
      ${esc(p.name)}
    </div>`).join('');
  ctxMenu.innerHTML = `
    <div class="ctx-title">Ajouter à…</div>
    ${items || '<div class="ctx-empty">Aucune playlist</div>'}
    <div class="ctx-sep"></div>
    <div class="ctx-item" data-new="1">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      Nouvelle playlist
    </div>`;
  ctxMenu.querySelectorAll('.ctx-item').forEach((it) => {
    it.addEventListener('click', async () => {
      closeCtx();
      if (it.dataset.new) {
        askInput({ title: 'Nouvelle playlist', label: 'Nom de la playlist', okLabel: 'Créer' }, async (name) => {
          const r = await window.mdl.createPlaylist(name);
          if (r.ok) {
            appState.playlists.push(r.playlist);
            await window.mdl.addToPlaylist(r.playlist.id, trackId);
            r.playlist.tracks.push(trackId);
            renderPlaylists();
            showToast(`Ajoutée à "${name}"`, 'success');
          }
        });
      } else {
        const pl = appState.playlists.find((p) => p.id === it.dataset.pl);
        if (pl) {
          if (pl.tracks.includes(trackId)) { showToast('Déjà dans cette playlist', 'info'); return; }
          await window.mdl.addToPlaylist(pl.id, trackId);
          pl.tracks.push(trackId);
          renderPlaylists();
          if (currentPlId === pl.id) renderPlaylistDetail();
          showToast(`Ajoutée à "${pl.name}"`, 'success');
        }
      }
    });
  });
  const r = anchor.getBoundingClientRect();
  ctxMenu.classList.add('on');
  const mw = ctxMenu.offsetWidth, mh = ctxMenu.offsetHeight;
  let x = Math.min(r.left, window.innerWidth - mw - 8);
  let y = r.bottom + 6;
  if (y + mh > window.innerHeight - 8) y = r.top - mh - 6;
  ctxMenu.style.left = x + 'px';
  ctxMenu.style.top = Math.max(8, y) + 'px';
}
function closeCtx() { ctxMenu.classList.remove('on'); }
document.addEventListener('click', (e) => { if (!ctxMenu.contains(e.target) && !e.target.closest('[data-addpl]')) closeCtx(); });
window.addEventListener('blur', closeCtx);

/* ════════ RECHERCHE ════════ */
function setSearchState(state) {
  ['empty', 'loading', 'error', 'results'].forEach((s) => $('#ss-' + s).classList.toggle('on', s === state));
}

async function runSearch(q) {
  const query = (q != null ? q : $('#search-input').value).trim();
  if (q != null) $('#search-input').value = q;
  if (!query) { setSearchState('empty'); return; }
  if (!online) { showToast('Hors ligne — connexion requise', 'error'); return; }
  lastSearchError = null;
  searchResults = [];
  setSearchState('loading');
  $('#dl-all-btn').style.display = 'none';
  const r = await window.mdl.search(query);
  if (!r.ok) {
    lastSearchError = r.error || 'Erreur inconnue';
    $('#ss-error-msg').textContent = lastSearchError;
    setSearchState('error');
    return;
  }
  searchResults = r.results;
  appState.recents = [query, ...appState.recents.filter((x) => x.toLowerCase() !== query.toLowerCase())].slice(0, 6);
  renderRecents();
  renderResults(query);
  setSearchState('results');
}
$('#search-btn').addEventListener('click', () => runSearch());
$('#search-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') runSearch(); });

function trackStatus(id) {
  if (trackById(id)) return 'done';
  const q = queueSnap.find((x) => x.id === id);
  if (q) return q.status === 'downloading' ? 'downloading' : 'queued';
  return 'none';
}

function renderResults(query) {
  $('#res-bar').innerHTML = `<strong>${searchResults.length} résultat${searchResults.length > 1 ? 's' : ''}</strong>&nbsp;pour "${esc(query)}" &nbsp;·&nbsp; YouTube Music`;
  const list = $('#rc-list');
  list.innerHTML = '';
  searchResults.forEach((t, i) => {
    const card = document.createElement('div');
    card.className = 'rcard';
    card.dataset.id = t.id;
    card.innerHTML = `
      <div class="rcard-thumb ${tClass(i)}">
        <img src="${esc(t.thumb)}" loading="lazy" onerror="this.remove()">
        ${t.duration ? `<div class="rcard-dur">${fmtDur(t.duration)}</div>` : ''}
      </div>
      <div class="rcard-info">
        <div class="rcard-title">${esc(t.title)}</div>
        <div class="rcard-meta">
          <span class="rcard-ch">${esc(t.artist || 'Inconnu')}</span>
          ${t.views ? `<span class="rcard-sep">·</span><span class="rcard-views">${fmtViews(t.views)}</span>` : ''}
        </div>
        <div class="rcard-prog-wrap" style="display:none">
          <div class="rcard-prog"><div class="rcard-prog-fill" style="width:0%"></div></div>
          <div class="rcard-prog-lbl">Téléchargement… 0%</div>
        </div>
      </div>
      <div class="rcard-acts"></div>`;
    list.appendChild(card);
    refreshCard(t.id);
  });
  $('#dl-all-btn').style.display = searchResults.length ? '' : 'none';
}

function refreshCard(id) {
  const card = document.querySelector(`.rcard[data-id="${CSS.escape(id)}"]`);
  if (!card) return;
  const st = trackStatus(id);
  const acts = card.querySelector('.rcard-acts');
  const progWrap = card.querySelector('.rcard-prog-wrap');
  if (st === 'done') {
    progWrap.style.display = 'none';
    acts.innerHTML = `<div class="done-badge"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>Téléchargée</div>`;
  } else if (st === 'downloading' || st === 'queued') {
    const q = queueSnap.find((x) => x.id === id);
    const pct = q ? q.pct : 0;
    const phase = q ? q.phase : 'En attente…';
    progWrap.style.display = '';
    progWrap.querySelector('.rcard-prog-fill').style.width = pct + '%';
    progWrap.querySelector('.rcard-prog-lbl').textContent = st === 'queued' ? 'En attente…' : `${phase} ${pct}%`;
    acts.innerHTML = `<button class="dl-btn busy"><span class="spinner"></span></button>`;
  } else {
    progWrap.style.display = 'none';
    acts.innerHTML = `<button class="dl-btn" title="Télécharger">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    </button>`;
    acts.querySelector('.dl-btn').addEventListener('click', () => startDownload(id));
  }
}

async function startDownload(id) {
  const t = searchResults.find((x) => x.id === id) || trackById(id);
  if (!t) return;
  if (!online) { showToast('Hors ligne — connexion requise', 'error'); return; }
  const r = await window.mdl.download({ id: t.id, title: t.title, artist: t.artist, thumb: t.thumb, duration: t.duration });
  if (r.ok) showToast('Téléchargement démarré', 'info');
  else showToast(r.error || 'Impossible de télécharger', 'error');
}
$('#dl-all-btn').addEventListener('click', () => {
  const todo = searchResults.filter((t) => trackStatus(t.id) === 'none');
  if (!todo.length) { showToast('Tout est déjà téléchargé', 'info'); return; }
  todo.forEach((t) => startDownload(t.id));
  showToast(`${todo.length} téléchargement${todo.length > 1 ? 's' : ''} lancé${todo.length > 1 ? 's' : ''}`, 'info');
});

/* ── Récents ── */
function renderRecents() {
  const wrap = $('#recents-wrap'), box = $('#recents');
  if (!appState.recents.length) { wrap.style.display = 'none'; return; }
  wrap.style.display = '';
  box.innerHTML = '';
  appState.recents.forEach((q, i) => {
    const el = document.createElement('div');
    el.className = 'qa';
    el.innerHTML = `<div class="qa-dot ${tClass(i)}"><svg width="10" height="10" viewBox="0 0 24 24" fill="white"><circle cx="11" cy="11" r="7" fill="none" stroke="white" stroke-width="2.4"/><path d="m21 21-4.35-4.35" stroke="white" stroke-width="2.4" stroke-linecap="round"/></svg></div><span>${esc(q)}</span>`;
    el.title = q;
    el.addEventListener('click', () => { goPage(0); runSearch(q); });
    box.appendChild(el);
  });
}

/* ════════ FILE DE TÉLÉCHARGEMENTS ════════ */
window.mdl.on('dl:queue', (snap) => {
  queueSnap = snap;
  renderQueue();
  searchResults.forEach((t) => refreshCard(t.id));
});
window.mdl.on('dl:done', ({ track }) => {
  lastDlError = null;
  appState.library = appState.library.filter((t) => t.id !== track.id);
  appState.library.push(track);
  showToast(`"${track.title}" téléchargée`, 'success');
  renderLibrary();
  renderPlaylists();
  refreshCard(track.id);
});
window.mdl.on('dl:error', ({ id, title, error }) => {
  lastDlError = error;
  showToast(`Échec : ${title} — ${error}`, 'error');
  refreshCard(id);
});

function renderQueue() {
  const box = $('#sb-queue'), list = $('#sb-queue-list');
  $('#sb-queue-badge').textContent = queueSnap.length;
  box.classList.toggle('show', queueSnap.length > 0);
  list.innerHTML = '';
  queueSnap.slice(0, 4).forEach((q) => {
    const el = document.createElement('div');
    el.className = 'sq-item';
    el.innerHTML = `
      <div class="sq-thumb">${q.thumb ? `<img src="${esc(q.thumb)}">` : ''}</div>
      <div class="sq-info">
        <div class="sq-name">${esc(q.title)}</div>
        <div class="sq-prog"><div class="sq-prog-fill" style="width:${q.pct}%"></div></div>
      </div>
      <span class="sq-pct">${q.status === 'waiting' ? '…' : q.pct + '%'}</span>`;
    list.appendChild(el);
  });
}

/* ════════ BIBLIOTHÈQUE ════════ */
let sortKey = 'title', sortDir = 1, libFilter = '';
const sortArrow = document.querySelector('.lib-col-h .sort-arrow');

$$('#lib-cols .lib-col-h').forEach((h) => {
  h.addEventListener('click', () => {
    const k = h.dataset.sort;
    if (!k) return;
    if (sortKey === k) sortDir = -sortDir;
    else { sortKey = k; sortDir = 1; }
    $$('#lib-cols .lib-col-h').forEach((x) => { x.classList.remove('sorted', 'desc'); });
    h.classList.add('sorted');
    if (sortDir < 0) h.classList.add('desc');
    h.appendChild(sortArrow);
    renderLibrary();
  });
});
$('#lib-filter').addEventListener('input', () => { libFilter = $('#lib-filter').value.trim().toLowerCase(); renderLibrary(); });
$('#open-folder-btn').addEventListener('click', () => window.mdl.openFolder());

function visibleLibrary() {
  let list = appState.library.slice();
  if (libFilter) {
    list = list.filter((t) =>
      (t.title || '').toLowerCase().includes(libFilter) ||
      (t.artist || '').toLowerCase().includes(libFilter) ||
      (t.album || '').toLowerCase().includes(libFilter));
  }
  list.sort((a, b) => {
    let va = a[sortKey], vb = b[sortKey];
    if (sortKey === 'duration' || sortKey === 'year') { va = va || 0; vb = vb || 0; return (va - vb) * sortDir; }
    return String(va || '').localeCompare(String(vb || ''), 'fr', { sensitivity: 'base' }) * sortDir;
  });
  return list;
}

function renderLibrary() {
  const list = visibleLibrary();
  const all = appState.library;
  const empty = all.length === 0;

  $('#lib-stats').style.display = empty ? 'none' : '';
  $('#lib-cols').style.display = empty ? 'none' : '';
  $('#lib-pb').style.display = empty ? 'none' : '';
  $('#lib-empty-state').style.display = empty ? 'flex' : 'none';

  const totalDur = all.reduce((s, t) => s + (t.duration || 0), 0);
  const artists = new Set(all.map((t) => (t.artist || '').toLowerCase()).filter(Boolean)).size;
  $('#lib-sub').textContent = `${all.length} titre${all.length > 1 ? 's' : ''} · ${fmtDurLong(totalDur)}`;
  $('#st-count').textContent = all.length;
  $('#st-count').nextSibling.textContent = ` titre${all.length > 1 ? 's' : ''}`;
  $('#st-dur').textContent = fmtDurLong(totalDur);
  $('#st-artists').textContent = artists;
  $('#st-artists').nextSibling.textContent = ` artiste${artists > 1 ? 's' : ''}`;
  $('#pl-sub').textContent = `${appState.playlists.length} playlist${appState.playlists.length > 1 ? 's' : ''} · ${appState.playlists.reduce((s, p) => s + p.tracks.length, 0)} titres`;

  const pb = $('#lib-pb');
  pb.innerHTML = '';
  list.forEach((t, i) => pb.appendChild(buildRow(t, i, { context: 'lib', list })));
}

function buildRow(t, i, { context, list, plId }) {
  const row = document.createElement('div');
  row.className = 'lib-row' + (currentTrack && currentTrack.id === t.id ? ' playing' : '');
  row.dataset.id = t.id;
  const isPlaying = currentTrack && currentTrack.id === t.id;
  const eqPaused = audio.paused ? ' paused' : '';
  row.innerHTML = `
    <div class="rc-n-wrap">
      ${isPlaying
        ? `<div class="rc-eq${eqPaused}" style="display:flex"><div class="rc-eq-b"></div><div class="rc-eq-b"></div><div class="rc-eq-b"></div></div>`
        : `<div class="rc-n">${i + 1}</div>`}
      <div class="rc-play-ico"><svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg></div>
    </div>
    <div class="rc-thumb ${tClass(i)}">${t.cover ? `<img src="${local(t.cover)}" loading="lazy" onerror="this.remove()">` : `<div class="rc-thumb-ph">${SVG_NOTE(14, '.3')}</div>`}</div>
    <div class="rc-info">
      <div class="rc-title">${esc(t.title)}</div>
      <div class="rc-artist">${esc(t.artist || 'Inconnu')}</div>
    </div>
    <div class="rc-album">${esc(t.album || '—')}</div>
    <div class="rc-year">${t.year || '—'}</div>
    <div class="rc-dur">${fmtDur(t.duration)}</div>
    <div class="rc-acts">
      ${context === 'pl'
        ? `<button class="act-btn del" data-act="plremove" title="Retirer de la playlist"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"/></svg></button>`
        : `<button class="act-btn" data-act="addpl" data-addpl="1" title="Ajouter à une playlist"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg></button>`}
      <button class="act-btn${t.favorite ? ' faved' : ''}" data-act="fav" title="Favori"><svg width="12" height="12" viewBox="0 0 24 24" fill="${t.favorite ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg></button>
      <button class="act-btn del" data-act="del" title="Supprimer"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg></button>
    </div>`;

  row.addEventListener('click', (e) => {
    const btn = e.target.closest('.act-btn');
    if (!btn) { startQueue(list.map((x) => x.id), i); return; }
    const act = btn.dataset.act;
    if (act === 'addpl') openPlaylistMenu(btn, t.id);
    else if (act === 'fav') toggleFavorite(t.id);
    else if (act === 'del') confirmDeleteTrack(t);
    else if (act === 'plremove') {
      window.mdl.removeFromPlaylist(plId, t.id);
      const pl = appState.playlists.find((p) => p.id === plId);
      if (pl) pl.tracks = pl.tracks.filter((x) => x !== t.id);
      renderPlaylistDetail();
      renderPlaylists();
      showToast('Retirée de la playlist', 'info');
    }
  });
  return row;
}

function confirmDeleteTrack(t) {
  askConfirm({
    title: 'Supprimer le titre',
    html: `Supprimer <strong>${esc(t.title)}</strong> de la bibliothèque ?<br>Le fichier audio sera aussi supprimé du dossier.`,
    okLabel: 'Supprimer'
  }, async () => {
    if (currentTrack && currentTrack.id === t.id) stopPlayback();
    await window.mdl.deleteTrack(t.id);
    appState.library = appState.library.filter((x) => x.id !== t.id);
    appState.playlists.forEach((p) => { p.tracks = p.tracks.filter((id) => id !== t.id); });
    renderLibrary();
    renderPlaylists();
    if (currentPlId) renderPlaylistDetail();
    searchResults.forEach((x) => refreshCard(x.id));
    showToast('Titre supprimé', 'info');
  });
}

async function toggleFavorite(id) {
  const t = trackById(id);
  if (!t) return;
  t.favorite = !t.favorite;
  await window.mdl.setFavorite(id, t.favorite);
  renderLibrary();
  if (currentPlId) renderPlaylistDetail();
  syncPlayerUI();
}

/* ════════ PLAYLISTS ════════ */
function mosaicHtml(pl, cellSvgSize) {
  const tracks = pl.tracks.map(trackById).filter(Boolean).slice(0, 4);
  let cells = '';
  for (let i = 0; i < 4; i++) {
    const t = tracks[i];
    if (t && t.cover) cells += `<div class="pl-cover-cell"><img src="${local(t.cover)}" loading="lazy"></div>`;
    else cells += `<div class="pl-cover-cell ${tClass(i + pl.name.length)}"><svg width="${cellSvgSize}" height="${cellSvgSize}" viewBox="0 0 24 24" fill="white" opacity=".8"><polygon points="5 3 19 12 5 21 5 3"/></svg></div>`;
  }
  return cells;
}

function renderPlaylists() {
  const grid = $('#pl-grid');
  grid.innerHTML = '';
  appState.playlists.forEach((pl) => {
    const tracks = pl.tracks.map(trackById).filter(Boolean);
    const dur = tracks.reduce((s, t) => s + (t.duration || 0), 0);
    const card = document.createElement('div');
    card.className = 'pl-card';
    card.innerHTML = `
      <div class="pl-cover">${mosaicHtml(pl, 15)}</div>
      <div class="pl-foot">
        <div class="pl-foot-info">
          <div class="pl-name">${esc(pl.name)}</div>
          <div class="pl-meta">${tracks.length} titre${tracks.length > 1 ? 's' : ''} · <span>${fmtDurLong(dur)}</span></div>
        </div>
        <div class="pl-foot-acts">
          <button class="pl-act" data-act="shuffle" title="Lecture aléatoire"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M16 3h5v5"/><path d="m21 3-7 7"/><path d="M16 21h5v-5"/><path d="m21 21-7-7"/><path d="M3 3l4 4"/><path d="M3 21l4-4"/></svg></button>
          <button class="pl-act del" data-act="del" title="Supprimer"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/></svg></button>
        </div>
      </div>`;
    card.addEventListener('click', (e) => {
      const btn = e.target.closest('.pl-act');
      if (!btn) { openPlaylist(pl.id); return; }
      if (btn.dataset.act === 'shuffle') {
        const ids = pl.tracks.filter(trackById);
        if (!ids.length) { showToast('Playlist vide', 'info'); return; }
        shuffleOn = true;
        startQueue(shuffleArray(ids.slice()), 0);
        syncPlayerUI();
      } else if (btn.dataset.act === 'del') {
        askConfirm({
          title: 'Supprimer la playlist',
          html: `Supprimer la playlist <strong>${esc(pl.name)}</strong> ?<br>Les titres restent dans la bibliothèque.`,
        }, async () => {
          await window.mdl.deletePlaylist(pl.id);
          appState.playlists = appState.playlists.filter((p) => p.id !== pl.id);
          if (currentPlId === pl.id) closePlaylist();
          renderPlaylists();
          renderLibrary();
          showToast('Playlist supprimée', 'info');
        });
      }
    });
    grid.appendChild(card);
  });

  const newCard = document.createElement('div');
  newCard.className = 'pl-card new-card';
  newCard.innerHTML = `
    <div class="pl-new-ico"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg></div>
    <div class="pl-new-lbl">Créer une playlist</div>`;
  newCard.addEventListener('click', () => newPlaylistFlow());
  grid.appendChild(newCard);
}

function newPlaylistFlow() {
  askInput({ title: 'Nouvelle playlist', label: 'Nom de la playlist', okLabel: 'Créer' }, async (name) => {
    const r = await window.mdl.createPlaylist(name);
    if (r.ok) {
      appState.playlists.push(r.playlist);
      renderPlaylists();
      renderLibrary();
      showToast(`Playlist "${name}" créée`, 'success');
    }
  });
}
$('#new-pl-btn').addEventListener('click', newPlaylistFlow);

function openPlaylist(id) {
  currentPlId = id;
  $('#pv-grid').classList.remove('on');
  $('#pv-detail').classList.add('on');
  renderPlaylistDetail();
}
function closePlaylist() {
  currentPlId = null;
  $('#pv-detail').classList.remove('on');
  $('#pv-grid').classList.add('on');
}
$('#pld-back').addEventListener('click', closePlaylist);

function renderPlaylistDetail() {
  const pl = appState.playlists.find((p) => p.id === currentPlId);
  if (!pl) { closePlaylist(); return; }
  const tracks = pl.tracks.map(trackById).filter(Boolean);
  $('#pld-mosaic').innerHTML = mosaicHtml(pl, 13).replace(/pl-cover-cell/g, 'pld-mosaic-cell');
  $('#pld-name').textContent = pl.name;
  const dur = tracks.reduce((s, t) => s + (t.duration || 0), 0);
  const artists = [...new Set(tracks.map((t) => t.artist).filter(Boolean))].slice(0, 3).join(', ');
  $('#pld-sub').innerHTML = `
    <span>${tracks.length} titre${tracks.length > 1 ? 's' : ''}</span>
    <span class="pld-dot">·</span><span>${fmtDurLong(dur)}</span>
    ${artists ? `<span class="pld-dot">·</span><span style="color:rgba(79,136,248,.7)">${esc(artists)}${tracks.length > 3 ? '…' : ''}</span>` : ''}`;
  $('#pld-play').disabled = !tracks.length;
  $('#pld-shuffle').disabled = !tracks.length;
  const box = $('#pld-tracks');
  box.innerHTML = '';
  if (!tracks.length) {
    box.innerHTML = `<div class="empty-state"><div class="empty-title">Playlist vide</div><div class="empty-sub">Ajoute des titres depuis la bibliothèque avec le bouton +</div></div>`;
    return;
  }
  tracks.forEach((t, i) => box.appendChild(buildRow(t, i, { context: 'pl', list: tracks, plId: pl.id })));
}
$('#pld-play').addEventListener('click', () => {
  const pl = appState.playlists.find((p) => p.id === currentPlId);
  if (!pl) return;
  const ids = pl.tracks.filter(trackById);
  if (ids.length) startQueue(ids, 0);
});
$('#pld-shuffle').addEventListener('click', () => {
  const pl = appState.playlists.find((p) => p.id === currentPlId);
  if (!pl) return;
  const ids = pl.tracks.filter(trackById);
  if (!ids.length) return;
  shuffleOn = true;
  startQueue(shuffleArray(ids.slice()), 0);
  syncPlayerUI();
});
$('#pld-rename').addEventListener('click', () => {
  const pl = appState.playlists.find((p) => p.id === currentPlId);
  if (!pl) return;
  askInput({ title: 'Renommer la playlist', label: 'Nom de la playlist', value: pl.name, okLabel: 'Renommer' }, async (name) => {
    await window.mdl.renamePlaylist(pl.id, name);
    pl.name = name;
    renderPlaylistDetail();
    renderPlaylists();
  });
});

/* ════════ LECTEUR ════════ */
function shuffleArray(a) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function startQueue(ids, index) {
  playQueue = ids.slice();
  playPos = index;
  if (shuffleOn) {
    const first = playQueue.splice(index, 1)[0];
    shuffleArray(playQueue);
    playQueue.unshift(first);
    playPos = 0;
  }
  loadTrack(playQueue[playPos]);
}

function loadTrack(id) {
  const t = trackById(id);
  if (!t) { nextTrack(); return; }
  currentTrack = t;
  audio.src = local(t.file);
  audio.play().catch(() => showToast('Lecture impossible — fichier introuvable ?', 'error'));
  syncPlayerUI();
  renderLibrary();
  if (currentPlId) renderPlaylistDetail();
  updateMediaSession();
}

function stopPlayback() {
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  currentTrack = null;
  syncPlayerUI();
  renderLibrary();
}

function prevTrack() {
  if (!playQueue.length) return;
  if (audio.currentTime > 4) { audio.currentTime = 0; return; }
  playPos = (playPos - 1 + playQueue.length) % playQueue.length;
  loadTrack(playQueue[playPos]);
}
function nextTrack(auto) {
  if (!playQueue.length) return;
  if (auto && repeatMode === 2) { audio.currentTime = 0; audio.play(); return; }
  if (playPos >= playQueue.length - 1) {
    if (repeatMode === 1 || !auto) { playPos = 0; loadTrack(playQueue[0]); }
    else stopPlayback();
    return;
  }
  playPos++;
  loadTrack(playQueue[playPos]);
}

function togglePlay() {
  if (!currentTrack) {
    const list = visibleLibrary();
    if (list.length) startQueue(list.map((t) => t.id), 0);
    return;
  }
  if (audio.paused) audio.play();
  else audio.pause();
}

$('#btn-play').addEventListener('click', togglePlay);
$('#gl-play').addEventListener('click', togglePlay);
$('#btn-prev').addEventListener('click', prevTrack);
$('#gl-prev').addEventListener('click', prevTrack);
$('#btn-next').addEventListener('click', () => nextTrack(false));
$('#gl-next').addEventListener('click', () => nextTrack(false));

function toggleShuffle() {
  shuffleOn = !shuffleOn;
  if (shuffleOn && playQueue.length > 1 && playPos >= 0) {
    const current = playQueue[playPos];
    const rest = playQueue.filter((_, i) => i !== playPos);
    shuffleArray(rest);
    playQueue = [current, ...rest];
    playPos = 0;
  }
  syncPlayerUI();
  showToast(shuffleOn ? 'Lecture aléatoire activée' : 'Lecture aléatoire désactivée', 'info');
}
function toggleRepeat() {
  repeatMode = (repeatMode + 1) % 3;
  syncPlayerUI();
  showToast(['Répétition désactivée', 'Répéter tout', 'Répéter le titre'][repeatMode], 'info');
}
$('#btn-shuffle').addEventListener('click', toggleShuffle);
$('#gl-shuffle').addEventListener('click', toggleShuffle);
$('#btn-repeat').addEventListener('click', toggleRepeat);
$('#gl-repeat').addEventListener('click', toggleRepeat);

/* Favori (player + GL) */
$('#ply-fav').addEventListener('click', () => currentTrack && toggleFavorite(currentTrack.id));
$('#gl-fav').addEventListener('click', () => currentTrack && toggleFavorite(currentTrack.id));

/* Volume */
let lastVolume = parseFloat(localStorage.getItem('mdl-volume') || '0.8');
audio.volume = lastVolume;
function setVolume(v, save) {
  v = Math.max(0, Math.min(1, v));
  audio.volume = v;
  audio.muted = false;
  if (save !== false) { lastVolume = v || lastVolume; localStorage.setItem('mdl-volume', String(v)); }
  syncVolumeUI();
}
function syncVolumeUI() {
  const v = audio.muted ? 0 : audio.volume;
  $('#vol-fill').style.width = (v * 100) + '%';
  $('#ico-vol').style.display = v > 0 ? '' : 'none';
  $('#ico-mute').style.display = v > 0 ? 'none' : '';
}
$('#vol-btn').addEventListener('click', () => {
  if (audio.muted || audio.volume === 0) { audio.muted = false; setVolume(lastVolume || 0.8); }
  else { audio.muted = true; syncVolumeUI(); }
});
bindBar($('#vol-bar'), (ratio) => setVolume(ratio));
$('#vol-bar').addEventListener('wheel', (e) => {
  e.preventDefault();
  setVolume(audio.volume + (e.deltaY < 0 ? 0.05 : -0.05));
});

/* Barres de progression (seek) */
function bindBar(el, onRatio) {
  let dragging = false;
  const update = (e) => {
    const r = el.getBoundingClientRect();
    onRatio(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)));
  };
  el.addEventListener('mousedown', (e) => { dragging = true; update(e); });
  window.addEventListener('mousemove', (e) => { if (dragging) update(e); });
  window.addEventListener('mouseup', () => { dragging = false; });
}
bindBar($('#ply-track'), (r) => { if (audio.duration) audio.currentTime = r * audio.duration; });
bindBar($('#gl-track'), (r) => { if (audio.duration) audio.currentTime = r * audio.duration; });

/* Événements audio */
audio.addEventListener('timeupdate', () => {
  const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
  $('#ply-fill').style.width = pct + '%';
  $('#gl-fill').style.width = pct + '%';
  $('#ply-prog-mini').style.width = pct + '%';
  $('#time-cur').textContent = fmtDur(audio.currentTime);
  $('#gl-time-cur').textContent = fmtDur(audio.currentTime);
  const tot = audio.duration || (currentTrack && currentTrack.duration) || 0;
  $('#time-tot').textContent = fmtDur(tot);
  $('#gl-time-tot').textContent = fmtDur(tot);
});
audio.addEventListener('ended', () => nextTrack(true));
audio.addEventListener('play', syncPlayerUI);
audio.addEventListener('pause', syncPlayerUI);

function syncPlayerUI() {
  const playing = !audio.paused && currentTrack;
  $('#ico-play').style.display = playing ? 'none' : '';
  $('#ico-pause').style.display = playing ? '' : 'none';
  $('#gl-ico-play').style.display = playing ? 'none' : '';
  $('#gl-ico-pause').style.display = playing ? '' : 'none';
  $('#btn-shuffle').classList.toggle('active', shuffleOn);
  $('#gl-shuffle').classList.toggle('on', shuffleOn);
  $('#btn-repeat').classList.toggle('active', repeatMode > 0);
  $('#gl-repeat').classList.toggle('on', repeatMode > 0);

  const eq = $('#ply-eq');
  if (currentTrack) {
    eq.style.display = 'flex';
    eq.classList.toggle('paused', !playing);
    $('#ply-title').textContent = currentTrack.title;
    $('#ply-artist').textContent = currentTrack.artist || 'Inconnu';
    $('#gl-title').textContent = currentTrack.title;
    $('#gl-artist').textContent = currentTrack.artist || 'Inconnu';
    const fav = !!currentTrack.favorite;
    $('#ply-fav').classList.toggle('on', fav);
    $('#gl-fav').classList.toggle('on', fav);
    const art = $('#ply-art'), glArt = $('#gl-art');
    if (currentTrack.cover) {
      art.innerHTML = `<img src="${local(currentTrack.cover)}">`;
      glArt.querySelector('img')?.remove();
      glArt.insertAdjacentHTML('afterbegin', `<img src="${local(currentTrack.cover)}">`);
      glArt.querySelector('.gl-art-ph').style.display = 'none';
    } else {
      art.innerHTML = SVG_NOTE(16, '.22');
      glArt.querySelector('img')?.remove();
      glArt.querySelector('.gl-art-ph').style.display = '';
    }
  } else {
    eq.style.display = 'none';
    $('#ply-title').textContent = 'Aucune lecture';
    $('#ply-artist').textContent = '—';
    $('#ply-art').innerHTML = SVG_NOTE(16, '.22');
    $('#ply-fill').style.width = '0%';
    $('#gl-fill').style.width = '0%';
    $('#ply-prog-mini').style.width = '0%';
    $('#time-cur').textContent = '0:00';
    $('#time-tot').textContent = '0:00';
  }
  // Synchroniser l'égaliseur des lignes de la bibliothèque
  $$('.lib-row .rc-eq').forEach((e) => e.classList.toggle('paused', !playing));
  syncVolumeUI();
}

/* Grand lecteur */
function openGL() { if (currentTrack) $('#grand-lecteur').classList.add('on'); }
function closeGL() { $('#grand-lecteur').classList.remove('on'); }
$('#ply-left').addEventListener('click', openGL);
$('#exp-btn').addEventListener('click', openGL);
$('#gl-close').addEventListener('click', closeGL);
$('#gl-backdrop').addEventListener('click', closeGL);

/* MediaSession (touches média + overlay Windows) */
function updateMediaSession() {
  if (!('mediaSession' in navigator) || !currentTrack) return;
  try {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: currentTrack.title,
      artist: currentTrack.artist || '',
      album: currentTrack.album || '',
      artwork: currentTrack.cover ? [{ src: local(currentTrack.cover), sizes: '512x512', type: 'image/jpeg' }] : []
    });
    navigator.mediaSession.setActionHandler('play', () => audio.play());
    navigator.mediaSession.setActionHandler('pause', () => audio.pause());
    navigator.mediaSession.setActionHandler('previoustrack', prevTrack);
    navigator.mediaSession.setActionHandler('nexttrack', () => nextTrack(false));
    navigator.mediaSession.setActionHandler('seekto', (d) => { if (d.seekTime != null) audio.currentTime = d.seekTime; });
  } catch (_) {}
}

/* Raccourcis clavier */
document.addEventListener('keydown', (e) => {
  const typing = ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName);
  if (e.code === 'Space' && !typing) { e.preventDefault(); togglePlay(); }
  if (e.key === 'Escape') { closeGL(); closeCtx(); $$('.modal-back.on').forEach((m) => m.classList.remove('on')); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
    e.preventDefault();
    if (currentPage === 1) $('#lib-filter').focus();
    else { goPage(0); $('#search-input').focus(); }
  }
});

/* ════════ EN LIGNE / HORS LIGNE ════════ */
function setOnline(v) {
  if (online === v) return;
  online = v;
  applyOnlineUI();
  showToast(v ? 'Connexion rétablie' : 'Mode hors ligne — ta musique reste disponible', v ? 'success' : 'error');
}
function applyOnlineUI() {
  const badge = $('#online-badge');
  badge.className = 'online' + (online ? '' : ' offline');
  badge.innerHTML = `<div class="online-dot"></div>${online ? 'En ligne' : 'Hors ligne'}`;
  $('#offline-banner').classList.toggle('show', !online);
  $('#search-input').disabled = !online;
  $('#search-btn').disabled = !online;
}
window.addEventListener('online', () => setOnline(true));
window.addEventListener('offline', () => setOnline(false));
$('#retry-online').addEventListener('click', async () => {
  const ok = await pingNet();
  setOnline(ok);
  if (!ok) showToast('Toujours hors ligne', 'error');
});
async function pingNet() {
  if (!navigator.onLine) return false;
  try {
    const ctl = new AbortController();
    const to = setTimeout(() => ctl.abort(), 4000);
    await fetch('https://www.gstatic.com/generate_204', { mode: 'no-cors', cache: 'no-store', signal: ctl.signal });
    clearTimeout(to);
    return true;
  } catch (_) { return false; }
}
setInterval(async () => setOnline(await pingNet()), 25000);

/* ════════ PARAMÈTRES ════════ */
let pendingSettings = {};
$('#settings-btn').addEventListener('click', () => {
  pendingSettings = { ...appState.settings };
  $('#folder-display').textContent = pendingSettings.folder;
  $$('#opt-quality .opt-btn').forEach((b) => b.classList.toggle('on', b.dataset.v === pendingSettings.quality));
  $$('#opt-format .opt-btn').forEach((b) => b.classList.toggle('on', b.dataset.v === pendingSettings.format));
  $('#settings-modal').classList.add('on');
});
$$('#opt-quality .opt-btn').forEach((b) => b.addEventListener('click', () => {
  pendingSettings.quality = b.dataset.v;
  $$('#opt-quality .opt-btn').forEach((x) => x.classList.toggle('on', x === b));
}));
$$('#opt-format .opt-btn').forEach((b) => b.addEventListener('click', () => {
  pendingSettings.format = b.dataset.v;
  $$('#opt-format .opt-btn').forEach((x) => x.classList.toggle('on', x === b));
}));
$('#folder-pick').addEventListener('click', async () => {
  const r = await window.mdl.chooseFolder();
  if (r.ok) { pendingSettings.folder = r.folder; $('#folder-display').textContent = r.folder; }
});
$('#settings-save').addEventListener('click', async () => {
  const r = await window.mdl.saveSettings(pendingSettings);
  if (r.ok) {
    appState.settings = r.settings;
    $('#settings-modal').classList.remove('on');
    showToast('Paramètres sauvegardés', 'success');
  }
});

/* ════════ MISES À JOUR ════════ */
let updateState = 'idle';
window.mdl.on('update:available', ({ version }) => {
  updateState = 'available';
  $('#sb-update').classList.add('show');
  $('#sb-update-sub').textContent = `Version ${version} — prête à installer`;
  $('#sb-update-btn').textContent = 'Télécharger';
  $('#sb-update-btn').classList.remove('ready');
  $('#sb-update-prog').style.display = 'none';
  showToast(`Mise à jour disponible — v${version}`, 'info');
});
window.mdl.on('update:progress', ({ pct }) => {
  updateState = 'downloading';
  $('#sb-update-btn').textContent = `Téléchargement… ${pct}%`;
  $('#sb-update-prog').style.display = '';
  $('#sb-update-prog-fill').style.width = pct + '%';
});
window.mdl.on('update:ready', () => {
  updateState = 'ready';
  $('#sb-update-btn').textContent = 'Redémarrer pour installer';
  $('#sb-update-btn').classList.add('ready');
  $('#sb-update-prog').style.display = 'none';
  showToast('Mise à jour téléchargée', 'success');
});
window.mdl.on('update:error', ({ message }) => {
  if (updateState === 'downloading') {
    $('#sb-update-btn').textContent = 'Réessayer';
    showToast('Échec de la mise à jour : ' + message, 'error');
    updateState = 'available';
  }
});
$('#sb-update-btn').addEventListener('click', () => {
  if (updateState === 'available') { window.mdl.downloadUpdate(); $('#sb-update-btn').textContent = 'Téléchargement…'; }
  else if (updateState === 'ready') window.mdl.installUpdate();
});

/* ════════ INIT ════════ */
async function init() {
  appState = await window.mdl.getState();
  $('#win-title').textContent = `Music DL — v${appState.version}`;
  applyOnlineUI();
  renderRecents();
  renderLibrary();
  renderPlaylists();
  syncPlayerUI();
}
init();

/* ════════ HOOKS DE TEST (E2E) ════════ */
window.MDL_TEST = {
  search: (q) => runSearch(q),
  downloadFirst: () => { if (searchResults[0]) startDownload(searchResults[0].id); },
  goLibrary: () => goPage(1),
  goPlaylists: () => goPage(2),
  playFirst: () => {
    const list = visibleLibrary();
    if (list.length) startQueue(list.map((t) => t.id), 0);
  },
  openGL: () => openGL(),
  closeGL: () => closeGL(),
  state: () => JSON.stringify({
    page: currentPage,
    results: searchResults.length,
    searchError: lastSearchError,
    queue: queueSnap.length,
    queuePct: queueSnap.reduce((m, q) => Math.max(m, q.pct), 0),
    library: appState.library.length,
    playing: !!currentTrack && !audio.paused,
    online,
    lastError: lastDlError
  })
};
