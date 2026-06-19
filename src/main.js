/* ════════════════════════════════════════════
   Music DL — Main process
   Recherche + téléchargement YouTube Music (yt-dlp/ffmpeg),
   bibliothèque locale, playlists, auto-update GitHub.
═══════════════════════════════════════════════ */
const { app, BrowserWindow, ipcMain, dialog, shell, protocol, Tray, Menu } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { Readable } = require('stream');
const { autoUpdater } = require('electron-updater');

/* ── Chemins ── */
const BIN = app.isPackaged
  ? path.join(process.resourcesPath, 'bin')
  : path.join(__dirname, '..', 'bin');
const YTDLP = path.join(BIN, 'yt-dlp.exe');
const COVERS = path.join(app.getPath('userData'), 'covers');
const LYRICS = path.join(app.getPath('userData'), 'lyrics');
const STORE_FILE = path.join(app.getPath('userData'), 'store.json');

/* ── Store (bibliothèque, playlists, paramètres, récents) ── */
const DEFAULT_STORE = {
  settings: { folder: path.join(app.getPath('music'), 'Music DL'), quality: '192', format: 'mp3', closeToTray: true },
  library: [],
  playlists: [],
  recents: [],
  plays: {},
  onlineMeta: {},  // { [id]: { id,title,artist,album,duration,thumb, fav:bool } } — titres NON telecharges references par un favori / une playlist
  interests: []    // [{ browseId, name, photo, ts }] — artistes ouverts (gout de l'utilisateur) -> reco "Pour toi"
};
let store = loadStore();

function loadStore() {
  try {
    const raw = JSON.parse(fs.readFileSync(STORE_FILE, 'utf8'));
    return {
      settings: Object.assign({}, DEFAULT_STORE.settings, raw.settings),
      library: Array.isArray(raw.library) ? raw.library : [],
      playlists: Array.isArray(raw.playlists) ? raw.playlists : [],
      recents: Array.isArray(raw.recents) ? raw.recents : [],
      plays: (raw.plays && typeof raw.plays === 'object' && !Array.isArray(raw.plays)) ? raw.plays : {},
      onlineMeta: (raw.onlineMeta && typeof raw.onlineMeta === 'object' && !Array.isArray(raw.onlineMeta)) ? raw.onlineMeta : {},
      interests: Array.isArray(raw.interests) ? raw.interests : []
    };
  } catch (_) {
    // Fichier present mais illisible (corrompu/tronque) : le sauvegarder AVANT de
    // repartir des defauts -> ne jamais perdre la bibliotheque en silence.
    try {
      if (fs.existsSync(STORE_FILE) && fs.statSync(STORE_FILE).size > 0) {
        fs.copyFileSync(STORE_FILE, STORE_FILE + '.corrupt-' + Date.now());
      }
    } catch (_) {}
    return JSON.parse(JSON.stringify(DEFAULT_STORE));
  }
}
function saveStore() {
  // Ecriture atomique : tmp + rename -> un crash en cours d'ecriture ne peut plus
  // tronquer store.json (qui declencherait le fallback ci-dessus = perte totale).
  try {
    const tmp = STORE_FILE + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(store, null, 2));
    fs.renameSync(tmp, STORE_FILE);
  } catch (_) {}
}
function ensureDirs() {
  try { fs.mkdirSync(store.settings.folder, { recursive: true }); } catch (_) {}
  try { fs.mkdirSync(COVERS, { recursive: true }); } catch (_) {}
  try { fs.mkdirSync(LYRICS, { recursive: true }); } catch (_) {}
}

/* ── Fenêtre ── */
let win = null;
let tray = null;
let quitting = false;

const ICON_PATH = path.join(__dirname, '..', 'build', 'icon.ico');

/* Barre système : fermer = réduire, la musique continue */
function createTray() {
  if (tray || !fs.existsSync(ICON_PATH)) return;
  tray = new Tray(ICON_PATH);
  tray.setToolTip('Music DL');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Ouvrir Music DL', click: () => { if (win) { win.show(); win.focus(); } } },
    { type: 'separator' },
    { label: 'Lecture / Pause', click: () => send('remote:cmd', { action: 'toggle' }) },
    { label: 'Titre suivant', click: () => send('remote:cmd', { action: 'next' }) },
    { label: 'Titre précédent', click: () => send('remote:cmd', { action: 'prev' }) },
    { type: 'separator' },
    { label: 'Quitter', click: () => { quitting = true; app.quit(); } }
  ]));
  tray.on('click', () => { if (win) { win.show(); win.focus(); } });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1120, height: 690,
    minWidth: 940, minHeight: 580,
    frame: false,
    show: false,
    backgroundColor: '#06080f',
    icon: fs.existsSync(path.join(__dirname, '..', 'build', 'icon.ico'))
      ? path.join(__dirname, '..', 'build', 'icon.ico') : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.once('ready-to-show', () => win.show());
  win.on('maximize', () => send('win:maximized', true));
  win.on('unmaximize', () => send('win:maximized', false));
  win.on('close', (e) => {
    const e2e = process.env.MUSICDL_E2E || process.env.MUSICDL_E2E_UPDATE;
    if (store.settings.closeToTray !== false && !quitting && !e2e && tray) {
      e.preventDefault();
      win.hide();
    }
  });
  win.on('closed', () => { win = null; });
}

function send(channel, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

/* ── Protocole local pour lire MP3 + pochettes (mdl://local?p=<path>) ── */
protocol.registerSchemesAsPrivileged([
  { scheme: 'mdl', privileges: { bypassCSP: true, stream: true, supportFetchAPI: true } }
]);

/* ── Utilitaires ── */
function sanitizeName(name) {
  return String(name)
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[. ]+$/, '')
    .slice(0, 120) || 'titre';
}
function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 7); }
function trackUrl(id) { return 'https://www.youtube.com/watch?v=' + id; }

function runYtdlp(args, { onLine } = {}) {
  return new Promise((resolve) => {
    const child = spawn(YTDLP, args, { windowsHide: true });
    let out = '', err = '', buf = '';
    child.stdout.on('data', (d) => {
      out += d;
      if (onLine) {
        buf += d;
        const lines = buf.split(/\r?\n/);
        buf = lines.pop();
        lines.forEach((l) => l && onLine(l));
      }
    });
    child.stderr.on('data', (d) => { err += d; });
    child.on('error', (e) => resolve({ code: -1, out, err: String(e) }));
    child.on('close', (code) => {
      if (onLine && buf) onLine(buf);
      resolve({ code, out, err });
    });
  });
}

/* ══ RECHERCHE ══ */
/* API officielle interne de YouTube Music (InnerTube) : chansons, albums et
   playlists avec métadonnées et pochettes carrées. Repli yt-dlp si l'API change. */
const INNERTUBE_PARAMS = {
  songs: 'EgWKAQIIAWoQEAMQBBAJEAoQBRAREBAQFQ%3D%3D',
  albums: 'EgWKAQIYAWoQEAMQBBAJEAoQBRAREBAQFQ%3D%3D',
  artists: 'EgWKAQIgAWoQEAMQBBAJEAoQBRAREBAQFQ%3D%3D',
  playlists: 'Eg-KAQwIABAAGAAgACgBMABqChAEEAMQCRAFEAo%3D'
};

async function innertube(endpoint, body) {
  const ctl = new AbortController();
  const to = setTimeout(() => ctl.abort(), 9000);
  try {
    const res = await fetch(`https://music.youtube.com/youtubei/v1/${endpoint}?prettyPrint=false`, {
      method: 'POST',
      signal: ctl.signal,
      headers: {
        'Content-Type': 'application/json',
        'Origin': 'https://music.youtube.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
      },
      body: JSON.stringify({
        context: { client: { clientName: 'WEB_REMIX', clientVersion: '1.20250602.01.00', hl: 'fr', gl: 'FR' } },
        ...body
      })
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return await res.json();
  } finally {
    clearTimeout(to);
  }
}

function walkJson(node, fn) {
  if (!node || typeof node !== 'object') return;
  fn(node);
  if (Array.isArray(node)) { node.forEach((n) => walkJson(n, fn)); return; }
  for (const k of Object.keys(node)) walkJson(node[k], fn);
}

function parseSearchResponse(data, kind) {
  const items = [];
  walkJson(data, (n) => {
    if (!n.musicResponsiveListItemRenderer) return;
    const item = kind === 'songs'
      ? parseMusicItem(n.musicResponsiveListItemRenderer)
      : parseCollectionItem(n.musicResponsiveListItemRenderer, kind);
    if (item) items.push(item);
  });
  const seen = new Set();
  const results = [];
  for (const it of items) {
    const key = it.id || it.browseId;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    results.push(it);
  }
  let token = null;
  walkJson(data, (n) => {
    if (token) return;
    if (n.nextContinuationData && n.nextContinuationData.continuation) token = n.nextContinuationData.continuation;
    else if (n.continuationCommand && n.continuationCommand.token) token = n.continuationCommand.token;
  });
  return { results, token };
}

async function ytMusicSearch(query, kind) {
  const data = await innertube('search', { query, params: INNERTUBE_PARAMS[kind] || INNERTUBE_PARAMS.songs });
  return parseSearchResponse(data, kind);
}

/* Page suivante de résultats (scroll infini, max ~200 côté interface) */
async function ytMusicMore(token, kind) {
  const data = await innertube('search', { continuation: token });
  return parseSearchResponse(data, kind);
}

/* Suggestions de frappe (comme sur le site officiel) */
async function ytMusicSuggest(input) {
  const data = await innertube('music/get_search_suggestions', { input });
  const out = [];
  walkJson(data, (n) => {
    if (n.searchSuggestionRenderer && n.searchSuggestionRenderer.suggestion) {
      const txt = (n.searchSuggestionRenderer.suggestion.runs || []).map((r) => r.text).join('');
      if (txt && !out.includes(txt)) out.push(txt);
    }
  });
  return out.slice(0, 7);
}

/* Page artiste complète : en-tête (nom, photo, abonnés), top titres, discographie */
async function getArtist(browseId) {
  try {
    const data = await innertube('browse', { browseId });
    let header = null;
    walkJson(data, (n) => {
      if (!header && (n.musicImmersiveHeaderRenderer || n.musicVisualHeaderRenderer)) {
        header = n.musicImmersiveHeaderRenderer || n.musicVisualHeaderRenderer;
      }
    });
    let name = '', subs = '', photo = null;
    if (header) {
      name = (header.title && header.title.runs && header.title.runs[0].text) || '';
      walkJson(header, (n) => {
        if (!subs && n.subscriberCountText && n.subscriberCountText.runs) subs = n.subscriberCountText.runs.map((r) => r.text).join('');
        if (!photo && n.thumbnails && Array.isArray(n.thumbnails) && n.thumbnails.length) photo = n.thumbnails[n.thumbnails.length - 1].url.replace(/=w\d+-h\d+[^=]*$/, '=w480-h480');
      });
    }
    const topSongs = [];
    const seenS = new Set();
    walkJson(data, (n) => {
      const r = n.musicResponsiveListItemRenderer;
      if (!r) return;
      const id = r.playlistItemData && r.playlistItemData.videoId;
      if (!id || seenS.has(id) || topSongs.length >= 10) return;
      const cols = (r.flexColumns || []).map((c) => {
        const t = c.musicResponsiveListItemFlexColumnRenderer;
        return (t && t.text && t.text.runs) || [];
      });
      const title = cols[0] && cols[0][0] ? cols[0][0].text : null;
      if (!title) return;
      let artist = name;
      for (const run of cols.slice(1).flat()) {
        const page = run.navigationEndpoint && run.navigationEndpoint.browseEndpoint
          && run.navigationEndpoint.browseEndpoint.browseEndpointContextSupportedConfigs
          && run.navigationEndpoint.browseEndpoint.browseEndpointContextSupportedConfigs.browseEndpointContextMusicConfig
          && run.navigationEndpoint.browseEndpoint.browseEndpointContextSupportedConfigs.browseEndpointContextMusicConfig.pageType;
        if (page === 'MUSIC_PAGE_TYPE_ARTIST') { artist = (run.text || '').trim(); break; }
      }
      seenS.add(id);
      topSongs.push({ id, title, artist, duration: parseFixedDuration(r), thumb: itemThumb(r, id) });
    });
    const albums = collectArtistAlbums(data, name);
    const related = collectRelatedArtists(data, browseId);
    if (!name && !topSongs.length && !albums.length) return { ok: false, error: 'Artiste introuvable' };
    return { ok: true, artist: { browseId, name, subs, photo, topSongs, albums, related } };
  } catch (e) {
    return { ok: false, error: 'Impossible de charger cet artiste' };
  }
}

async function getArtistByName(nameQuery) {
  try {
    const res = await ytMusicSearch(nameQuery, 'artists');
    const top = res.results[0];
    if (!top) return { ok: false, error: 'Artiste introuvable' };
    return getArtist(top.browseId);
  } catch (_) {
    return { ok: false, error: 'Artiste introuvable' };
  }
}

/* Artistes liés ("les fans aiment aussi") d'une page artiste -> reco de nouveaux artistes. */
function collectRelatedArtists(data, selfBrowseId) {
  const out = [];
  const seen = new Set();
  walkJson(data, (n) => {
    const r = n.musicTwoRowItemRenderer;
    if (!r) return;
    const be = r.navigationEndpoint && r.navigationEndpoint.browseEndpoint;
    const bid = be && be.browseId;
    if (!bid || !/^UC/.test(bid) || bid === selfBrowseId || seen.has(bid)) return;
    const name = r.title && r.title.runs && r.title.runs[0] && r.title.runs[0].text;
    if (!name) return;
    const thumbs = ((((r.thumbnailRenderer || {}).musicThumbnailRenderer || {}).thumbnail || {}).thumbnails) || [];
    const thumb = thumbs.length ? thumbs[thumbs.length - 1].url.replace(/=w\d+-h\d+/, '=w160-h160') : null;
    seen.add(bid);
    out.push({ browseId: bid, name, thumb });
  });
  return out.slice(0, 8);
}

function collectArtistAlbums(data, artistName) {
  const albums = [];
  const seen = new Set();
  walkJson(data, (n) => {
    const r = n.musicTwoRowItemRenderer;
    if (!r) return;
    const be = r.navigationEndpoint && r.navigationEndpoint.browseEndpoint;
    if (!be || !/^MPREb/.test(be.browseId || '') || seen.has(be.browseId)) return;
    const title = r.title && r.title.runs && r.title.runs[0] && r.title.runs[0].text;
    if (!title) return;
    const subRuns = ((r.subtitle && r.subtitle.runs) || []).map((x) => (x.text || '').trim()).filter((x) => x && x !== '•');
    let year = null, type = 'Album';
    for (const txt of subRuns) {
      if (/^\d{4}$/.test(txt)) year = Number(txt);
      else if (/single/i.test(txt)) type = 'Single';
      else if (/^EP$/i.test(txt)) type = 'EP';
    }
    const thumbs = ((((r.thumbnailRenderer || {}).musicThumbnailRenderer || {}).thumbnail || {}).thumbnails) || [];
    const thumb = thumbs.length ? thumbs[thumbs.length - 1].url.replace(/=w\d+-h\d+/, '=w232-h232') : null;
    seen.add(be.browseId);
    albums.push({ browseId: be.browseId, kind: 'album', title, artist: artistName, year, info: type, thumb });
  });
  albums.sort((a, b) => (a.info === 'Single') - (b.info === 'Single') || (b.year || 0) - (a.year || 0));
  return albums.slice(0, 40);
}

/* Discographie officielle d'un artiste (albums + singles de sa page) */
async function getArtistAlbums(artistBrowseId, artistName) {
  const data = await innertube('browse', { browseId: artistBrowseId });
  const albums = [];
  const seen = new Set();
  walkJson(data, (n) => {
    const r = n.musicTwoRowItemRenderer;
    if (!r) return;
    const be = r.navigationEndpoint && r.navigationEndpoint.browseEndpoint;
    if (!be || !/^MPREb/.test(be.browseId || '') || seen.has(be.browseId)) return;
    const title = r.title && r.title.runs && r.title.runs[0] && r.title.runs[0].text;
    if (!title) return;
    const subRuns = ((r.subtitle && r.subtitle.runs) || []).map((x) => (x.text || '').trim()).filter((x) => x && x !== '•');
    let year = null, type = 'Album';
    for (const txt of subRuns) {
      if (/^\d{4}$/.test(txt)) year = Number(txt);
      else if (/single/i.test(txt)) type = 'Single';
      else if (/^EP$/i.test(txt)) type = 'EP';
    }
    const thumbs = ((((r.thumbnailRenderer || {}).musicThumbnailRenderer || {}).thumbnail || {}).thumbnails) || [];
    const thumb = thumbs.length ? thumbs[thumbs.length - 1].url.replace(/=w\d+-h\d+/, '=w232-h232') : null;
    seen.add(be.browseId);
    albums.push({ browseId: be.browseId, kind: 'album', title, artist: artistName, year, info: type, thumb, fromArtist: true });
  });
  // Albums d'abord, puis EPs/singles, du plus récent au plus ancien
  albums.sort((a, b) => (a.info === 'Single') - (b.info === 'Single') || (b.year || 0) - (a.year || 0));
  return albums.slice(0, 40);
}

function itemThumb(r, fallbackId) {
  const thumbs = (((r.thumbnail || {}).musicThumbnailRenderer || {}).thumbnail || {}).thumbnails || [];
  let thumb = thumbs.length ? thumbs[thumbs.length - 1].url : (fallbackId ? 'https://i.ytimg.com/vi/' + fallbackId + '/mqdefault.jpg' : null);
  return thumb ? thumb.replace(/=w\d+-h\d+/, '=w232-h232') : null;
}

/* Carte album ou playlist dans les résultats de recherche */
function parseCollectionItem(r, kind) {
  try {
    const be = r.navigationEndpoint && r.navigationEndpoint.browseEndpoint;
    const browseId = be && be.browseId;
    if (!browseId) return null;
    if (kind === 'albums' && !/^MPREb/.test(browseId)) return null;
    if (kind === 'artists' && !/^UC/.test(browseId)) return null;
    if (kind === 'playlists' && !/^VL/.test(browseId)) return null;
    const cols = (r.flexColumns || []).map((c) => {
      const t = c.musicResponsiveListItemFlexColumnRenderer;
      return (t && t.text && t.text.runs) || [];
    });
    const title = cols[0] && cols[0][0] ? cols[0][0].text : null;
    if (!title) return null;
    const metaRuns = cols.slice(1).flat().map((x) => (x.text || '').trim()).filter((x) => x && x !== '•');
    let artist = '', year = null, info = '';
    if (kind === 'albums') {
      // "Album • Artiste • 2013"
      for (const txt of metaRuns) {
        if (/^\d{4}$/.test(txt)) year = Number(txt);
        else if (/^(EP|Single)$/i.test(txt)) info = txt;
        else if (!/^Album$/i.test(txt) && !artist) artist = txt;
      }
    } else if (kind === 'artists') {
      // "Artiste • 5,29 M auditeurs/mois"
      info = metaRuns.filter((t) => !/^Artiste$/i.test(t)).join(' · ');
    } else {
      // "Auteur • N vues"
      artist = metaRuns[0] || '';
      info = metaRuns.slice(1).join(' · ');
    }
    const kindOut = kind === 'albums' ? 'album' : (kind === 'artists' ? 'artist' : 'playlist');
    return { browseId, kind: kindOut, title, artist, year, info, thumb: itemThumb(r) };
  } catch (_) {
    return null;
  }
}

/* ══ ALBUM / PLAYLIST (browse InnerTube + repli yt-dlp) ══ */
function parseFixedDuration(r) {
  const f = ((r.fixedColumns || [])[0] || {}).musicResponsiveListItemFixedColumnRenderer;
  const txt = f && f.text && (f.text.runs || []).map((x) => x.text).join('');
  if (!txt || !/^\d+:\d{2}(:\d{2})?$/.test(txt.trim())) return null;
  const p = txt.trim().split(':').map(Number);
  return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1];
}

async function getCollection({ browseId, kind }) {
  try {
    const data = await innertube('browse', { browseId });
    let header = null;
    walkJson(data, (n) => {
      if (!header && (n.musicDetailHeaderRenderer || n.musicResponsiveHeaderRenderer)) {
        header = n.musicDetailHeaderRenderer || n.musicResponsiveHeaderRenderer;
      }
    });
    let title = '', artist = '', year = null;
    if (header) {
      title = (header.title && header.title.runs && header.title.runs[0].text) || '';
      const subRuns = []
        .concat((header.subtitle && header.subtitle.runs) || [])
        .concat((header.straplineTextOne && header.straplineTextOne.runs) || [])
        .map((x) => (x.text || '').trim()).filter((x) => x && x !== '•');
      for (const txt of subRuns) {
        if (/^\d{4}$/.test(txt)) year = Number(txt);
        else if (!/^(Album|EP|Single|Playlist)$/i.test(txt) && !/titre|vue|lecture|min\b|h\b/i.test(txt) && !artist) artist = txt;
      }
    }
    let cover = null;
    walkJson(data, (n) => {
      if (!cover && n.musicThumbnailRenderer && n.musicThumbnailRenderer.thumbnail) {
        const t = n.musicThumbnailRenderer.thumbnail.thumbnails;
        if (t && t.length) cover = t[t.length - 1].url;
      }
    });
    const tracks = [];
    const seen = new Set();
    walkJson(data, (n) => {
      const r = n.musicResponsiveListItemRenderer;
      if (!r) return;
      const id = r.playlistItemData && r.playlistItemData.videoId;
      if (!id || seen.has(id)) return;
      const cols = (r.flexColumns || []).map((c) => {
        const t = c.musicResponsiveListItemFlexColumnRenderer;
        return (t && t.text && t.text.runs) || [];
      });
      const tTitle = cols[0] && cols[0][0] ? cols[0][0].text : null;
      if (!tTitle) return;
      let tArtist = '';
      for (const run of cols.slice(1).flat()) {
        const page = run.navigationEndpoint && run.navigationEndpoint.browseEndpoint
          && run.navigationEndpoint.browseEndpoint.browseEndpointContextSupportedConfigs
          && run.navigationEndpoint.browseEndpoint.browseEndpointContextSupportedConfigs.browseEndpointContextMusicConfig
          && run.navigationEndpoint.browseEndpoint.browseEndpointContextSupportedConfigs.browseEndpointContextMusicConfig.pageType;
        if (page === 'MUSIC_PAGE_TYPE_ARTIST') { tArtist = (run.text || '').trim(); break; }
      }
      if (!tArtist && cols[1] && cols[1][0]) tArtist = (cols[1][0].text || '').trim();
      seen.add(id);
      tracks.push({
        id,
        title: tTitle,
        artist: tArtist || artist,
        duration: parseFixedDuration(r),
        thumb: itemThumb(r, id)
      });
    });
    if (!tracks.length) throw new Error('aucun titre');
    return { ok: true, collection: { browseId, kind, title, artist, year, cover, tracks } };
  } catch (e) {
    // Repli yt-dlp (flat playlist)
    const url = kind === 'album'
      ? 'https://music.youtube.com/browse/' + browseId
      : 'https://music.youtube.com/playlist?list=' + browseId.replace(/^VL/, '');
    const { code, out } = await runYtdlp([url, '--flat-playlist', '-j', '--no-warnings']);
    if (code !== 0 && !out.trim()) return { ok: false, error: 'Impossible de charger ce contenu' };
    const tracks = [];
    let title = '';
    for (const line of out.split(/\r?\n/)) {
      if (!line.trim()) continue;
      try {
        const e = JSON.parse(line);
        if (!e.id || e._type === 'playlist') continue;
        if (!title && e.playlist_title) title = e.playlist_title;
        tracks.push({
          id: e.id,
          title: e.title || 'Sans titre',
          artist: (e.channel || e.uploader || '').replace(/\s*-\s*Topic$/i, ''),
          duration: typeof e.duration === 'number' ? Math.round(e.duration) : null,
          thumb: 'https://i.ytimg.com/vi/' + e.id + '/mqdefault.jpg'
        });
      } catch (_) {}
    }
    if (!tracks.length) return { ok: false, error: 'Impossible de charger ce contenu' };
    return { ok: true, collection: { browseId, kind, title: title || 'Playlist', artist: '', year: null, cover: tracks[0].thumb, tracks } };
  }
}

function parseMusicItem(r) {
  try {
    const id = r.playlistItemData && r.playlistItemData.videoId;
    if (!id) return null;
    const cols = (r.flexColumns || []).map((c) => {
      const t = c.musicResponsiveListItemFlexColumnRenderer;
      return (t && t.text && t.text.runs) || [];
    });
    const title = cols[0] && cols[0][0] ? cols[0][0].text : null;
    if (!title) return null;
    let artist = '', album = '', duration = null, views = null;
    const metaRuns = cols.slice(1).flat();
    for (const run of metaRuns) {
      const txt = (run.text || '').trim();
      const page = run.navigationEndpoint && run.navigationEndpoint.browseEndpoint
        && run.navigationEndpoint.browseEndpoint.browseEndpointContextSupportedConfigs
        && run.navigationEndpoint.browseEndpoint.browseEndpointContextSupportedConfigs.browseEndpointContextMusicConfig
        && run.navigationEndpoint.browseEndpoint.browseEndpointContextSupportedConfigs.browseEndpointContextMusicConfig.pageType;
      if (page === 'MUSIC_PAGE_TYPE_ARTIST' && !artist) artist = txt;
      else if (page === 'MUSIC_PAGE_TYPE_ALBUM' && !album) album = txt;
      else if (/^\d+:\d{2}(:\d{2})?$/.test(txt)) {
        const p = txt.split(':').map(Number);
        duration = p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1];
      } else if (/lecture|écoute|view|play/i.test(txt) && /\d/.test(txt)) {
        views = txt;
      }
    }
    const thumbs = (((r.thumbnail || {}).musicThumbnailRenderer || {}).thumbnail || {}).thumbnails || [];
    let thumb = thumbs.length ? thumbs[thumbs.length - 1].url : 'https://i.ytimg.com/vi/' + id + '/mqdefault.jpg';
    // Demander une pochette plus grande à googleusercontent
    thumb = thumb.replace(/=w\d+-h\d+/, '=w232-h232');
    return { id, title, artist, album, duration, views, thumb };
  } catch (_) {
    return null;
  }
}

async function searchMusic(query, kind) {
  query = query.trim();
  kind = ['songs', 'albums', 'playlists'].includes(kind) ? kind : 'songs';
  const isUrl = /^https?:\/\//i.test(query);

  if (isUrl) {
    // Lien d'album ou de playlist → ouvrir directement la vue collection
    const mAlbum = query.match(/browse\/(MPREb[\w-]+)/);
    const mList = query.match(/[?&]list=([\w-]+)/);
    if (mAlbum) return { ok: true, collectionRef: { browseId: mAlbum[1], kind: 'album' } };
    if (mList && !/watch\?v=/.test(query)) return { ok: true, collectionRef: { browseId: 'VL' + mList[1], kind: 'playlist' } };

    const { code, out, err } = await runYtdlp([query, '-j', '--no-playlist', '--no-warnings', '--skip-download']);
    if (code !== 0 && !out.trim()) return { ok: false, error: cleanErr(err) };
    const results = [];
    for (const line of out.split(/\r?\n/)) {
      if (!line.trim()) continue;
      try {
        const e = JSON.parse(line);
        results.push({
          id: e.id,
          title: e.track || e.title || 'Sans titre',
          artist: (e.artist || e.channel || e.uploader || '').replace(/\s*-\s*Topic$/i, ''),
          album: e.album || '',
          duration: typeof e.duration === 'number' ? Math.round(e.duration) : null,
          views: e.view_count || null,
          thumb: 'https://i.ytimg.com/vi/' + e.id + '/mqdefault.jpg'
        });
      } catch (_) {}
    }
    if (!results.length) return { ok: false, error: 'Lien non reconnu' };
    return { ok: true, results, kind: 'songs' };
  }

  // ── Albums : mode intelligent — discographie officielle de l'artiste d'abord ──
  if (kind === 'albums') {
    const [artistRes, albumRes] = await Promise.all([
      ytMusicSearch(query, 'artists').catch(() => ({ results: [], token: null })),
      ytMusicSearch(query, 'albums').catch(() => ({ results: [], token: null }))
    ]);
    let artist = null;
    let artistAlbums = [];
    const top = artistRes.results[0];
    if (top) {
      const qn = query.toLowerCase(), an = (top.title || '').toLowerCase();
      // On n'affiche la discographie que si la recherche ressemble au nom de l'artiste
      if (qn.includes(an) || an.includes(qn)) {
        try {
          artistAlbums = await getArtistAlbums(top.browseId, top.title);
          if (artistAlbums.length) artist = { browseId: top.browseId, name: top.title, info: top.info, thumb: top.thumb };
        } catch (_) {}
      }
    }
    const seenIds = new Set(artistAlbums.map((a) => a.browseId));
    const rest = albumRes.results.filter((a) => !seenIds.has(a.browseId));
    const results = [...artistAlbums, ...rest];
    if (!results.length) return { ok: false, error: 'Aucun résultat' };
    store.recents = [query, ...store.recents.filter((r) => r.toLowerCase() !== query.toLowerCase())].slice(0, 6);
    saveStore();
    return { ok: true, results, kind, artist, continuation: albumRes.token };
  }

  // 1) API YouTube Music (+ detection de l'artiste en parallele pour la banniere des Titres)
  let results = [];
  let token = null;
  let artist = null;
  try {
    const [r, artistRes] = await Promise.all([
      ytMusicSearch(query, kind),
      kind === 'songs' ? ytMusicSearch(query, 'artists').catch(() => ({ results: [] })) : Promise.resolve({ results: [] })
    ]);
    results = r.results;
    token = r.token;
    const top = artistRes.results && artistRes.results[0];
    if (top && top.browseId) {
      const qn = query.toLowerCase(), an = (top.title || '').toLowerCase();
      // On n'affiche la banniere que si la recherche ressemble au nom de l'artiste
      if (qn.includes(an) || an.includes(qn)) {
        artist = { browseId: top.browseId, name: top.title, info: top.info, thumb: top.thumb };
      }
    }
  } catch (_) { /* repli ci-dessous */ }

  // Playlists : pas de repli équivalent côté yt-dlp
  if (!results.length && kind !== 'songs') {
    return { ok: false, error: 'Aucun résultat' };
  }

  // 2) Repli : recherche YouTube via yt-dlp (chansons uniquement)
  if (!results.length) {
    const { code, out, err } = await runYtdlp(['ytsearch12:' + query, '--flat-playlist', '-j', '--no-warnings']);
    if (code !== 0 && !out.trim()) return { ok: false, error: cleanErr(err) };
    for (const line of out.split(/\r?\n/)) {
      if (!line.trim()) continue;
      try {
        const e = JSON.parse(line);
        const thumbs = Array.isArray(e.thumbnails) ? e.thumbnails : [];
        results.push({
          id: e.id,
          title: e.title || 'Sans titre',
          artist: (e.channel || e.uploader || '').replace(/\s*-\s*Topic$/i, ''),
          album: '',
          duration: typeof e.duration === 'number' ? Math.round(e.duration) : null,
          views: e.view_count || null,
          thumb: thumbs.length ? thumbs[thumbs.length - 1].url : ('https://i.ytimg.com/vi/' + e.id + '/mqdefault.jpg')
        });
      } catch (_) {}
    }
  }

  if (!results.length) return { ok: false, error: 'Aucun résultat' };
  store.recents = [query, ...store.recents.filter((r) => r.toLowerCase() !== query.toLowerCase())].slice(0, 6);
  saveStore();
  return { ok: true, results, kind, artist, continuation: token };
}
function cleanErr(err) {
  const line = String(err).split(/\r?\n/).find((l) => l.includes('ERROR')) || 'Erreur réseau ou service indisponible';
  return line.replace(/^ERROR:\s*/i, '').slice(0, 180);
}

/* ══ TÉLÉCHARGEMENTS (file d'attente, 3 en parallèle) ══ */
const queue = [];          // {id, title, artist, thumb, status:'waiting'|'downloading', pct, phase}
let activeCount = 0;
const MAX_PARALLEL = 3;

function queueSnapshot() {
  return queue.map((q) => ({ id: q.id, title: q.title, artist: q.artist, thumb: q.thumb, status: q.status, pct: q.pct, phase: q.phase }));
}
function notifyQueue() {
  send('dl:queue', queueSnapshot());
  // Progression dans la barre des tâches Windows
  if (win && !win.isDestroyed()) {
    const active = queue.filter((q) => q.status === 'downloading');
    if (!active.length) win.setProgressBar(-1);
    else win.setProgressBar(active.reduce((s, q) => s + q.pct, 0) / active.length / 100);
  }
}

function enqueueDownload(track) {
  if (queue.find((q) => q.id === track.id)) return { ok: false, error: 'Déjà dans la file' };
  if (store.library.find((t) => t.id === track.id)) return { ok: false, error: 'Déjà téléchargée' };
  const item = { ...track, status: 'waiting', pct: 0, phase: 'En attente…' };
  queue.push(item);
  notifyQueue();
  pump();
  return { ok: true };
}

function pump() {
  while (activeCount < MAX_PARALLEL) {
    const next = queue.find((q) => q.status === 'waiting');
    if (!next) break;
    next.status = 'downloading';
    activeCount++;
    processDownload(next).finally(() => {
      activeCount--;
      const i = queue.indexOf(next);
      if (i >= 0) queue.splice(i, 1);
      notifyQueue();
      pump();
    });
  }
}

async function processDownload(item) {
  ensureDirs();
  const fmt = store.settings.format === 'm4a' ? 'm4a' : 'mp3';
  const quality = ['128', '192', '320'].includes(store.settings.quality) ? store.settings.quality : '192';
  const base = sanitizeName(item.artist ? item.artist + ' - ' + item.title : item.title);
  const outFile = path.join(store.settings.folder, base + '.' + fmt);
  const coverFile = path.join(COVERS, item.id + '.jpg');

  // Métadonnées complètes en parallèle (album, année, durée précise)
  const metaPromise = runYtdlp([trackUrl(item.id), '-j', '--no-playlist', '--no-warnings', '--skip-download'])
    .then((r) => { try { return JSON.parse(r.out.split(/\r?\n/).find((l) => l.trim())); } catch (_) { return null; } });

  item.phase = 'Téléchargement…';
  const args = [
    trackUrl(item.id),
    '-f', 'bestaudio/best',
    '-x', '--audio-format', fmt,
    '--audio-quality', quality + 'K',
    '--embed-thumbnail', '--embed-metadata',
    '--write-thumbnail', '--convert-thumbnails', 'jpg',
    '--ppa', 'EmbedThumbnail+ffmpeg_o:-c:v mjpeg -vf crop="\'if(gt(ih,iw),iw,ih)\':\'if(gt(iw,ih),ih,iw)\'"',
    '-o', path.join(store.settings.folder, base + '.%(ext)s'),
    '-o', 'thumbnail:' + path.join(COVERS, item.id + '.%(ext)s'),
    '--ffmpeg-location', BIN,
    '--no-playlist', '--no-mtime', '--newline', '--no-warnings'
  ];

  const { code, err } = await runYtdlp(args, {
    onLine(line) {
      const m = line.match(/\[download\]\s+(\d+(?:\.\d+)?)%/);
      if (m) {
        item.pct = Math.min(99, Math.round(parseFloat(m[1])));
        item.phase = 'Téléchargement…';
        notifyQueue();
      } else if (line.startsWith('[ExtractAudio]')) {
        item.pct = 99; item.phase = 'Conversion ' + fmt.toUpperCase() + '…';
        notifyQueue();
      } else if (line.startsWith('[EmbedThumbnail]')) {
        item.phase = 'Pochette…';
        notifyQueue();
      }
    }
  });

  if (code !== 0 || !fs.existsSync(outFile)) {
    send('dl:error', { id: item.id, title: item.title, error: cleanErr(err) });
    return;
  }

  const meta = await metaPromise;
  const entry = {
    id: item.id,
    title: (meta && (meta.track || meta.title)) || item.title,
    artist: (meta && (meta.artist || meta.channel || meta.uploader)) || item.artist || '',
    album: (meta && meta.album) || item.album || '',
    year: (meta && (meta.release_year || (meta.upload_date ? Number(meta.upload_date.slice(0, 4)) : null))) || item.year || null,
    duration: (meta && meta.duration ? Math.round(meta.duration) : null) || item.duration || null,
    file: outFile,
    cover: fs.existsSync(coverFile) ? coverFile : null,
    favorite: false,
    addedAt: Date.now()
  };
  // L'artiste YouTube Music finit souvent par " - Topic"
  entry.artist = entry.artist.replace(/\s*-\s*Topic$/i, '');
  // Re-telechargement : conserver favori / anciennete / paroles deja connus (pas de reset)
  const prev = store.library.find((t) => t.id === entry.id);
  if (prev) {
    entry.favorite = !!prev.favorite;
    if (prev.addedAt) entry.addedAt = prev.addedAt;
    if (prev.hasLyrics) entry.hasLyrics = true;
  }
  // Etait reference en ligne (favori / playlist) -> conserve le favori puis devient un vrai titre local
  const om = store.onlineMeta[entry.id];
  if (om && om.fav) entry.favorite = true;
  delete store.onlineMeta[entry.id];
  store.library = store.library.filter((t) => t.id !== entry.id);
  store.library.push(entry);
  saveStore();
  send('dl:done', { track: entry });
  // Paroles en arrière-plan (n'échoue jamais le téléchargement)
  ensureLyrics(entry, false).then((ly) => {
    if (ly && ly.found) { entry.hasLyrics = true; saveStore(); send('lyrics:ready', { id: entry.id }); }
  }).catch(() => {});
}

/* ══ PAROLES (LRCLIB — gratuit, sans clé, stockées hors ligne) ══ */
const LRC_UA = 'MusicDL/1.2 (https://github.com/Advm000/musicdl)';

async function lrclibFetch(url) {
  const ctl = new AbortController();
  const to = setTimeout(() => ctl.abort(), 8000);
  try {
    const res = await fetch(url, { signal: ctl.signal, headers: { 'User-Agent': LRC_UA } });
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  } finally {
    clearTimeout(to);
  }
}

async function fetchLyrics(track) {
  const q = (s) => encodeURIComponent(String(s || '').trim());
  let data = null;
  // 1) get exact (artiste + titre + durée)
  if (track.artist && track.title) {
    let url = `https://lrclib.net/api/get?artist_name=${q(track.artist)}&track_name=${q(track.title)}`;
    if (track.album) url += `&album_name=${q(track.album)}`;
    if (track.duration) url += `&duration=${Math.round(track.duration)}`;
    data = await lrclibFetch(url);
  }
  // 2) repli : recherche
  if (!data || (!data.syncedLyrics && !data.plainLyrics)) {
    const arr = await lrclibFetch(`https://lrclib.net/api/search?q=${q((track.artist || '') + ' ' + track.title)}`);
    if (Array.isArray(arr) && arr.length) {
      // meilleure correspondance de durée si connue
      data = track.duration
        ? arr.reduce((best, c) => Math.abs((c.duration || 0) - track.duration) < Math.abs((best.duration || 0) - track.duration) ? c : best, arr[0])
        : arr[0];
    }
  }
  if (!data || (!data.syncedLyrics && !data.plainLyrics)) return { ok: false };
  return { ok: true, synced: data.syncedLyrics || '', plain: data.plainLyrics || '' };
}

function lyricsPath(id) { return path.join(LYRICS, id + '.json'); }

async function ensureLyrics(track, force) {
  ensureDirs();
  const p = lyricsPath(track.id);
  if (!force && fs.existsSync(p)) {
    try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) {}
  }
  const r = await fetchLyrics(track);
  const payload = r.ok
    ? { id: track.id, synced: r.synced, plain: r.plain, found: true }
    : { id: track.id, synced: '', plain: '', found: false };
  try { fs.writeFileSync(p, JSON.stringify(payload)); } catch (_) {}
  return payload;
}

ipcMain.handle('lyrics:get', async (_e, id) => {
  const p = lyricsPath(id);
  if (fs.existsSync(p)) {
    try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) {}
  }
  const t = store.library.find((x) => x.id === id);
  if (!t) return { id, synced: '', plain: '', found: false };
  return ensureLyrics(t, false);
});
ipcMain.handle('lyrics:refetch', async (_e, id) => {
  const t = store.library.find((x) => x.id === id);
  if (!t) return { id, synced: '', plain: '', found: false };
  return ensureLyrics(t, true);
});

/* ══ AUTO-UPDATE (GitHub Releases) ══ */
function setupUpdater() {
  if (!app.isPackaged) return;
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.on('update-available', (info) => send('update:available', { version: info.version }));
  autoUpdater.on('download-progress', (p) => send('update:progress', { pct: Math.round(p.percent) }));
  autoUpdater.on('update-downloaded', () => send('update:ready', {}));
  autoUpdater.on('error', (e) => send('update:error', { message: String(e && e.message || e).slice(0, 160) }));
  const check = () => autoUpdater.checkForUpdates().catch(() => {});
  setTimeout(check, 4000);
  setInterval(check, 30 * 60 * 1000);
}

/* ══ IPC ══ */
ipcMain.on('win:minimize', () => win && win.minimize());
ipcMain.on('win:maximize', () => { if (!win) return; win.isMaximized() ? win.unmaximize() : win.maximize(); });
ipcMain.on('win:close', () => win && win.close());

/* ── Mini-lecteur flottant (remplace la fenêtre principale) ── */
let miniWin = null;
let lastMiniState = null;
function createMiniWindow() {
  if (miniWin && !miniWin.isDestroyed()) { miniWin.show(); miniWin.focus(); return; }
  miniWin = new BrowserWindow({
    width: 252, height: 420,
    frame: false, alwaysOnTop: true, resizable: false,
    skipTaskbar: true, show: false, backgroundColor: '#00000000', transparent: true,
    icon: fs.existsSync(ICON_PATH) ? ICON_PATH : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  miniWin.loadFile(path.join(__dirname, 'renderer', 'mini.html'));
  miniWin.once('ready-to-show', () => miniWin.show());
  miniWin.webContents.once('did-finish-load', () => {
    if (lastMiniState && miniWin && !miniWin.isDestroyed()) miniWin.webContents.send('mini:state', lastMiniState);
  });
  miniWin.on('closed', () => {
    miniWin = null;
    send('remote:cmd', { action: 'miniClosed' });
    // Si le mini se ferme, on ne laisse pas l'app invisible
    if (win && !win.isDestroyed() && !win.isVisible() && !quitting) win.show();
  });
}
ipcMain.on('mini:open', () => {
  createMiniWindow();
  if (win && !win.isDestroyed()) win.hide(); // l'app SE TRANSFORME en mini-lecteur
});
ipcMain.on('mini:close', () => { if (miniWin && !miniWin.isDestroyed()) miniWin.close(); });
ipcMain.on('mini:cmd', (_e, payload) => {
  if (payload && payload.action === 'expand') {
    if (win) { win.show(); win.focus(); }
    if (miniWin && !miniWin.isDestroyed()) miniWin.close();
    return;
  }
  send('remote:cmd', payload);
});
ipcMain.on('mini:state', (_e, s) => {
  lastMiniState = s;
  if (miniWin && !miniWin.isDestroyed()) miniWin.webContents.send('mini:state', s);
});

ipcMain.handle('state:get', () => ({
  version: app.getVersion(),
  packaged: app.isPackaged,
  settings: store.settings,
  library: store.library,
  playlists: store.playlists,
  recents: store.recents,
  plays: store.plays,
  onlineMeta: store.onlineMeta,
  interests: store.interests
}));

ipcMain.handle('plays:bump', (_e, id) => {
  if (!id) return { ok: false };
  store.plays[id] = (store.plays[id] || 0) + 1;
  saveStore();
  return { ok: true, plays: store.plays[id] };
});

ipcMain.handle('search:run', (_e, query, kind) => searchMusic(query, kind));
ipcMain.handle('search:more', async (_e, token, kind) => {
  try {
    const r = await ytMusicMore(token, kind === 'albums' ? 'albums' : kind === 'playlists' ? 'playlists' : 'songs');
    return { ok: true, results: r.results, continuation: r.token };
  } catch (_) {
    return { ok: false, results: [] };
  }
});
ipcMain.handle('search:suggest', async (_e, input) => {
  try { return await ytMusicSuggest(String(input || '').slice(0, 80)); } catch (_) { return []; }
});
ipcMain.handle('collection:get', (_e, ref) => getCollection(ref));
ipcMain.handle('artist:get', (_e, browseId) => getArtist(browseId));
ipcMain.handle('artist:byName', (_e, name) => getArtistByName(name));

/* Enregistre un artiste consulté comme "centre d'intérêt" (alimente la page Pour toi). */
ipcMain.handle('interest:add', (_e, a) => {
  if (!a || !a.browseId || !/^UC/.test(a.browseId)) return { ok: false };
  store.interests = (store.interests || []).filter((x) => x.browseId !== a.browseId);
  store.interests.unshift({ browseId: a.browseId, name: a.name || '', photo: a.photo || null, ts: Date.now() });
  store.interests = store.interests.slice(0, 20);
  saveStore();
  return { ok: true, count: store.interests.length };
});

/* ══ Reco "Pour toi" : pondère les artistes consultés (récence + collaborations),
   puis découvre de nouveaux artistes via les "artistes liés". ══ */
ipcMain.handle('discover', async () => {
  const interests = (store.interests || []).slice(0, 4);
  if (!interests.length) return { ok: true, tracks: [], albums: [], from: [] };
  const trackScore = new Map();   // id -> { track, score }
  const albumScore = new Map();   // browseId -> { album, score }
  const relatedPool = new Map();  // browseId -> { name, weight }
  for (let i = 0; i < interests.length; i++) {
    const w = 1 - i * 0.15;       // artiste consulté le plus récemment = poids max
    const r = await getArtist(interests[i].browseId).catch(() => null);
    if (!r || !r.ok) continue;
    const a = r.artist;
    (a.topSongs || []).forEach((t, idx) => {
      if (!t.id) return;
      const sc = (10 - idx) * w;  // top titres ordonnés par popularité
      const e = trackScore.get(t.id);
      if (e) e.score += sc; else trackScore.set(t.id, { track: Object.assign({}, t, { _from: a.name }), score: sc });
    });
    (a.albums || []).forEach((al) => {
      if (!al.browseId) return;
      const sc = w * (al.info === 'Single' ? 0.6 : 1);
      const e = albumScore.get(al.browseId);
      if (e) e.score += sc; else albumScore.set(al.browseId, { album: al, score: sc });
    });
    (a.related || []).forEach((rel, ri) => {
      if (!rel.browseId || interests.some((x) => x.browseId === rel.browseId)) return;
      const rw = w * (1 - ri * 0.1) * 0.5;
      const e = relatedPool.get(rel.browseId);
      if (e) e.weight += rw; else relatedPool.set(rel.browseId, { name: rel.name, weight: rw });
    });
  }
  // Découverte : on étend sur les 3 artistes liés les mieux notés (poids réduit)
  const topRelated = [...relatedPool.entries()].sort((x, y) => y[1].weight - x[1].weight).slice(0, 3);
  for (const [bid, info] of topRelated) {
    const r = await getArtist(bid).catch(() => null);
    if (!r || !r.ok) continue;
    const a = r.artist;
    (a.topSongs || []).slice(0, 5).forEach((t, idx) => {
      if (!t.id || trackScore.has(t.id)) return;
      trackScore.set(t.id, { track: Object.assign({}, t, { _from: a.name, _related: true }), score: (5 - idx) * info.weight });
    });
    (a.albums || []).slice(0, 4).forEach((al) => {
      if (!al.browseId || albumScore.has(al.browseId)) return;
      albumScore.set(al.browseId, { album: al, score: info.weight * 0.5 });
    });
  }
  const tracks = [...trackScore.values()].sort((x, y) => y.score - x.score).map((e) => e.track).slice(0, 40);
  const albums = [...albumScore.values()].sort((x, y) => y.score - x.score).map((e) => e.album).slice(0, 24);
  return { ok: true, tracks, albums, from: interests.map((i) => i.name) };
});
ipcMain.handle('dl:start', (_e, track) => enqueueDownload(track));

/* ── Préécoute (streaming avant téléchargement) ── */
const previewCache = new Map();
ipcMain.handle('preview:get', async (_e, id) => {
  if (previewCache.has(id)) return { ok: true, url: previewCache.get(id) };
  const { code, out, err } = await runYtdlp([trackUrl(id), '-f', 'bestaudio[ext=m4a]/bestaudio/best', '-g', '--no-playlist', '--no-warnings']);
  const url = out.split(/\r?\n/).find((l) => /^https?:\/\//.test(l.trim()));
  if (code !== 0 || !url) return { ok: false, error: cleanErr(err) };
  previewCache.set(id, url.trim());
  if (previewCache.size > 60) previewCache.delete(previewCache.keys().next().value);
  return { ok: true, url: url.trim() };
});

ipcMain.handle('library:delete', (_e, id) => {
  const t = store.library.find((x) => x.id === id);
  if (t) {
    try { if (fs.existsSync(t.file)) fs.unlinkSync(t.file); } catch (_) {}
    try { if (t.cover && fs.existsSync(t.cover)) fs.unlinkSync(t.cover); } catch (_) {}
  }
  store.library = store.library.filter((x) => x.id !== id);
  store.playlists.forEach((p) => { p.tracks = p.tracks.filter((tid) => tid !== id); });
  delete store.plays[id];
  delete store.onlineMeta[id];
  saveStore();
  return { ok: true };
});
ipcMain.handle('library:deleteMany', (_e, ids) => {
  const set = new Set(ids || []);
  store.library.forEach((t) => {
    if (!set.has(t.id)) return;
    try { if (t.file && fs.existsSync(t.file)) fs.unlinkSync(t.file); } catch (_) {}
    try { if (t.cover && fs.existsSync(t.cover)) fs.unlinkSync(t.cover); } catch (_) {}
  });
  store.library = store.library.filter((t) => !set.has(t.id));
  store.playlists.forEach((p) => { p.tracks = p.tracks.filter((id) => !set.has(id)); });
  (ids || []).forEach((id) => { delete store.plays[id]; delete store.onlineMeta[id]; });
  saveStore();
  return { ok: true, deleted: set.size };
});
ipcMain.handle('library:reveal', (_e, id) => {
  const t = store.library.find((x) => x.id === id);
  if (t && fs.existsSync(t.file)) shell.showItemInFolder(t.file);
  return { ok: true };
});
ipcMain.handle('folder:open', () => { ensureDirs(); shell.openPath(store.settings.folder); return { ok: true }; });

ipcMain.handle('fav:set', (_e, { id, on }) => {
  const t = store.library.find((x) => x.id === id);
  if (t) { t.favorite = !!on; saveStore(); }
  return { ok: true };
});

/* Favori d'un titre EN LIGNE (non telecharge) : stocke dans onlineMeta.
   Si le titre est dans la bibliotheque, on bascule simplement son favori. */
ipcMain.handle('online:setFav', (_e, { track, on }) => {
  const id = track && track.id;
  if (!id) return { ok: false };
  const lib = store.library.find((x) => x.id === id);
  if (lib) { lib.favorite = !!on; saveStore(); return { ok: true, where: 'library' }; }
  if (on) {
    const ex = store.onlineMeta[id] || {};
    store.onlineMeta[id] = {
      id, title: track.title || ex.title || '', artist: track.artist || ex.artist || '',
      album: track.album || ex.album || '', duration: track.duration || ex.duration || null,
      thumb: track.thumb || ex.thumb || null, fav: true
    };
  } else if (store.onlineMeta[id]) {
    // Plus favori : on garde la meta si encore dans une playlist, sinon on la retire
    if (store.playlists.some((p) => p.tracks.includes(id))) store.onlineMeta[id].fav = false;
    else delete store.onlineMeta[id];
  }
  saveStore();
  return { ok: true, where: 'online' };
});

/* Enregistre des titres EN LIGNE (album sauvegarde dans l'onglet Albums) sans favori ni playlist. */
ipcMain.handle('online:save', (_e, tracks) => {
  (tracks || []).forEach((m) => {
    if (!m || !m.id || store.library.some((t) => t.id === m.id)) return;
    const ex = store.onlineMeta[m.id] || {};
    store.onlineMeta[m.id] = {
      id: m.id, title: m.title || ex.title || '', artist: m.artist || ex.artist || '',
      album: m.album || ex.album || '', duration: m.duration || ex.duration || null,
      thumb: m.thumb || ex.thumb || null, fav: !!ex.fav, saved: true
    };
  });
  saveStore();
  return { ok: true };
});

/* Oublie completement un titre en ligne (le retire des albums/favoris/playlists). */
ipcMain.handle('online:remove', (_e, id) => {
  delete store.onlineMeta[id];
  store.playlists.forEach((p) => { p.tracks = p.tracks.filter((tid) => tid !== id); });
  saveStore();
  return { ok: true };
});

ipcMain.handle('playlist:create', (_e, name) => {
  const p = { id: uid(), name: String(name).slice(0, 60) || 'Playlist', tracks: [], createdAt: Date.now() };
  store.playlists.push(p);
  saveStore();
  return { ok: true, playlist: p };
});
ipcMain.handle('playlist:delete', (_e, id) => {
  store.playlists = store.playlists.filter((p) => p.id !== id);
  saveStore();
  return { ok: true };
});
ipcMain.handle('playlist:rename', (_e, { id, name }) => {
  const p = store.playlists.find((x) => x.id === id);
  if (p) { p.name = String(name).slice(0, 60) || p.name; saveStore(); }
  return { ok: true };
});
ipcMain.handle('playlist:addTrack', (_e, { playlistId, trackId, meta }) => {
  const p = store.playlists.find((x) => x.id === playlistId);
  if (!p) return { ok: false };
  // Titre EN LIGNE (non telecharge) : memoriser sa meta pour pouvoir l'afficher/le jouer
  if (meta && meta.id && !store.library.some((t) => t.id === meta.id)) {
    const ex = store.onlineMeta[meta.id] || {};
    store.onlineMeta[meta.id] = {
      id: meta.id, title: meta.title || ex.title || '', artist: meta.artist || ex.artist || '',
      album: meta.album || ex.album || '', duration: meta.duration || ex.duration || null,
      thumb: meta.thumb || ex.thumb || null, fav: !!ex.fav
    };
  }
  if (!p.tracks.includes(trackId)) { p.tracks.push(trackId); saveStore(); }
  return { ok: true };
});
ipcMain.handle('playlist:removeTrack', (_e, { playlistId, trackId }) => {
  const p = store.playlists.find((x) => x.id === playlistId);
  if (p) { p.tracks = p.tracks.filter((t) => t !== trackId); }
  // Plus reference par aucune playlist et pas favori -> retirer la meta online
  const om = store.onlineMeta[trackId];
  if (om && !om.fav && !store.playlists.some((pl) => pl.tracks.includes(trackId))) delete store.onlineMeta[trackId];
  saveStore();
  return { ok: true };
});

ipcMain.handle('settings:chooseFolder', async () => {
  const r = await dialog.showOpenDialog(win, {
    title: 'Choisir le dossier de téléchargement',
    defaultPath: store.settings.folder,
    properties: ['openDirectory', 'createDirectory']
  });
  if (r.canceled || !r.filePaths.length) return { ok: false };
  return { ok: true, folder: r.filePaths[0] };
});
ipcMain.handle('settings:save', (_e, s) => {
  if (s && typeof s.folder === 'string' && s.folder.trim()) store.settings.folder = s.folder.trim();
  if (s && ['128', '192', '320'].includes(s.quality)) store.settings.quality = s.quality;
  if (s && ['mp3', 'm4a'].includes(s.format)) store.settings.format = s.format;
  if (s && typeof s.closeToTray === 'boolean') store.settings.closeToTray = s.closeToTray;
  ensureDirs();
  saveStore();
  return { ok: true, settings: store.settings };
});

ipcMain.handle('update:download', () => { autoUpdater.downloadUpdate().catch(() => {}); return { ok: true }; });
ipcMain.handle('update:install', () => { autoUpdater.quitAndInstall(false, true); return { ok: true }; });

/* ══ E2E / Captures d'écran automatisées (dev uniquement) ══ */
async function shot(name) {
  const dir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  fs.mkdirSync(dir, { recursive: true });
  const img = await win.webContents.capturePage();
  fs.writeFileSync(path.join(dir, name + '.png'), img.toPNG());
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function runE2E() {
  const js = (code) => win.webContents.executeJavaScript(code, true);
  const report = { ok: false, steps: [] };
  const shotDir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  const reportFile = path.join(shotDir, 'e2e-report.json');
  try {
    await sleep(2500);
    await shot('01-recherche-vide');
    report.steps.push('shot accueil');

    await js(`MDL_TEST.search(${JSON.stringify(process.env.MUSICDL_E2E_QUERY || 'daft punk get lucky')})`);
    let st = null;
    for (let i = 0; i < 60; i++) { await sleep(1000); st = JSON.parse(await js('MDL_TEST.state()')); if (st.results > 0 || st.searchError) break; }
    if (!st || !st.results) throw new Error('Recherche sans résultat: ' + JSON.stringify(st));
    report.steps.push('recherche ok: ' + st.results + ' résultats');
    await sleep(600);
    await shot('02-resultats');

    await js('MDL_TEST.downloadFirst()');
    let shotMid = false;
    for (let i = 0; i < 240; i++) {
      await sleep(1000);
      st = JSON.parse(await js('MDL_TEST.state()'));
      if (!shotMid && st.queuePct > 5) { await shot('03-telechargement'); shotMid = true; }
      if (st.library > 0 && st.queue === 0) break;
      if (st.lastError) throw new Error('Erreur téléchargement: ' + st.lastError);
    }
    if (!st.library) throw new Error('Téléchargement non terminé');
    report.steps.push('téléchargement ok');

    await js('MDL_TEST.goLibrary()');
    await sleep(700);
    await shot('04-bibliotheque');

    await js('MDL_TEST.playFirst()');
    await sleep(2500);
    st = JSON.parse(await js('MDL_TEST.state()'));
    if (!st.playing) throw new Error('Lecture non démarrée');
    report.steps.push('lecture audio ok');
    await shot('05-lecture');

    await js('MDL_TEST.openGL()');
    await sleep(800);
    await shot('06-grand-lecteur');

    // ── Seek (Range requests) ──
    await js('MDL_TEST.seekTo(0.5)');
    await sleep(1200);
    st = JSON.parse(await js('MDL_TEST.state()'));
    if (!st.seekable || st.position < 5) throw new Error('Seek inopérant: ' + JSON.stringify({ seekable: st.seekable, position: st.position }));
    report.steps.push('seek ok (position ' + st.position + 's, seekable ' + st.seekable + 's)');

    // ── Favori (test idempotent : on verifie que le basculement change l etat dans les deux sens,
    //    quel que soit l etat de depart, puis on laisse le titre en favori pour la capture) ──
    const favStart = JSON.parse(await js('MDL_TEST.state()')).favOn;
    await js('MDL_TEST.toggleFav()');
    await sleep(500);
    const favAfter1 = JSON.parse(await js('MDL_TEST.state()')).favOn;
    if (favAfter1 === favStart) throw new Error('Favori inoperant : 1er basculement sans effet');
    await js('MDL_TEST.toggleFav()');
    await sleep(500);
    const favAfter2 = JSON.parse(await js('MDL_TEST.state()')).favOn;
    if (favAfter2 !== favStart) throw new Error('Favori inoperant : 2e basculement ne revient pas a l etat initial');
    if (!favAfter2) { await js('MDL_TEST.toggleFav()'); await sleep(400); }
    st = JSON.parse(await js('MDL_TEST.state()'));
    report.steps.push('favori ok (bascule on/off verifiee, etat final favori=' + st.favOn + ')');

    // ── Minuteur de sommeil ──
    await js('MDL_TEST.setSleep(15); MDL_TEST.openGL();');
    await sleep(900);
    st = JSON.parse(await js('MDL_TEST.state()'));
    if (!st.sleepArmed) throw new Error('Minuteur inopérant');
    report.steps.push('minuteur de sommeil ok');
    await shot('07-minuteur');
    await js('MDL_TEST.closeGL()');

    // ── Mini-lecteur ──
    createMiniWindow();
    await sleep(1800);
    if (miniWin && !miniWin.isDestroyed()) {
      const mimg = await miniWin.webContents.capturePage();
      const mdir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
      fs.writeFileSync(path.join(mdir, '08-mini-lecteur.png'), mimg.toPNG());
      miniWin.close();
      report.steps.push('mini-lecteur ok');
    } else {
      throw new Error('Mini-lecteur non créé');
    }

    // ── Album entier ──
    await js(`MDL_TEST.setTab('albums'); MDL_TEST.search(${JSON.stringify(process.env.MUSICDL_E2E_ALBUM || 'daft punk get lucky')})`);
    for (let i = 0; i < 40; i++) { await sleep(1000); st = JSON.parse(await js('MDL_TEST.state()')); if (st.collections > 0 || st.searchError) break; }
    if (!st.collections) throw new Error('Recherche albums sans résultat: ' + JSON.stringify(st));
    report.steps.push('recherche albums ok: ' + st.collections);
    await sleep(500);
    await shot('09-albums');

    await js('MDL_TEST.openFirstCollection()');
    for (let i = 0; i < 30; i++) { await sleep(1000); st = JSON.parse(await js('MDL_TEST.state()')); if (st.colTracks > 0) break; }
    if (!st.colTracks) throw new Error('Détail album vide');
    report.steps.push('album ouvert: "' + st.colTitle + '" (' + st.colTracks + ' titres)');
    await sleep(500);
    await shot('10-album-detail');

    const libBefore = st.library;
    await js('MDL_TEST.downloadCollection()');
    let shotAlb = false;
    for (let i = 0; i < 600; i++) {
      await sleep(1000);
      st = JSON.parse(await js('MDL_TEST.state()'));
      if (!shotAlb && st.queue > 0) { await sleep(1500); await shot('11-album-telechargement'); shotAlb = true; }
      if (st.colDone >= st.colTracks && st.queue === 0) break;
    }
    if (st.colDone < st.colTracks) throw new Error('Album incomplet: ' + st.colDone + '/' + st.colTracks);
    report.steps.push('album téléchargé en entier: ' + st.colDone + '/' + st.colTracks + ' titres (bibliothèque ' + libBefore + ' → ' + st.library + ')');
    await shot('12-album-telecharge');

    await js('MDL_TEST.goPlaylists();');
    await sleep(700);

    const t = store.library[0];
    report.fileExists = t && fs.existsSync(t.file);
    report.fileSizeMB = report.fileExists ? +(fs.statSync(t.file).size / 1048576).toFixed(2) : 0;
    report.coverExists = !!(t && t.cover && fs.existsSync(t.cover));
    report.track = t ? { title: t.title, artist: t.artist, album: t.album, year: t.year, duration: t.duration, file: t.file } : null;
    report.ok = report.fileExists && report.coverExists;
  } catch (e) {
    report.error = String(e && e.message || e);
    try { await shot('99-erreur'); } catch (_) {}
  }
  fs.mkdirSync(path.dirname(reportFile), { recursive: true });
  fs.writeFileSync(reportFile, JSON.stringify(report, null, 2));
  app.exit(report.ok ? 0 : 1);
}

/* E2E du système de mise à jour : app en vieille version → doit détecter,
   notifier et télécharger la release GitHub dans l'app (sans installer). */
async function runUpdateE2E() {
  const js = (code) => win.webContents.executeJavaScript(code, true);
  const shotDir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  const report = { ok: false, steps: [] };
  try {
    let st = null;
    for (let i = 0; i < 40; i++) {
      await sleep(1500);
      st = JSON.parse(await js('MDL_TEST.state()'));
      if (st.updateState === 'available') break;
    }
    if (!st || st.updateState !== 'available') throw new Error('update:available non reçu — ' + JSON.stringify(st));
    report.steps.push('notification affichée : v' + st.updateVersion + ' disponible');
    await sleep(400);
    await shot('u1-notification');

    await js('MDL_TEST.clickUpdate()');
    let shotMid = false;
    for (let i = 0; i < 900; i++) {
      await sleep(1000);
      st = JSON.parse(await js('MDL_TEST.state()'));
      if (!shotMid && st.updatePct > 3) { await shot('u2-telechargement'); shotMid = true; report.steps.push('téléchargement en cours dans l\'app (' + st.updatePct + '%)'); }
      if (st.updateState === 'ready') break;
      if (st.updateState === 'available' && i > 10) throw new Error('téléchargement update en échec');
    }
    if (st.updateState !== 'ready') throw new Error('update non téléchargée — ' + JSON.stringify(st));
    report.steps.push('update téléchargée — bouton "Redémarrer pour installer" affiché');
    await sleep(400);
    await shot('u3-prete');
    report.ok = true;
  } catch (e) {
    report.error = String(e && e.message || e);
    try { await shot('u9-erreur'); } catch (_) {}
  }
  fs.mkdirSync(shotDir, { recursive: true });
  fs.writeFileSync(path.join(shotDir, 'update-report.json'), JSON.stringify(report, null, 2));
  app.exit(report.ok ? 0 : 1);
}

/* ══ E2E PAROLES : joue un titre connu, affiche le karaoké, capture ══ */
async function runLyricsE2E() {
  const js = (code) => win.webContents.executeJavaScript(code, true);
  const shotDir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  const report = { ok: false, steps: [] };
  const st = async () => JSON.parse(await js('MDL_TEST.state()'));
  try {
    await sleep(2500);
    const found = await js(`MDL_TEST.playByTitle('blinding')`);
    if (!found) { await js('MDL_TEST.goLibrary(); MDL_TEST.playFirst();'); }
    await sleep(2500);
    await js('MDL_TEST.openGL(); MDL_TEST.showLyrics();');
    let s = null;
    for (let i = 0; i < 20; i++) { await sleep(800); s = await st(); if (s.lyricsLines > 0) break; }
    report.steps.push('paroles: ' + (s ? s.lyricsLines : 0) + ' lignes, trouvées=' + (s && s.lyricsFound));
    // Anti-regression du bug "paroles invisibles" (panneau .gl-lyrics rendu a hauteur 0) :
    // en mode lyrics-on, le panneau doit avoir une hauteur rendue non nulle (CSS = 220px).
    const lyH = await js("(()=>{const p=document.querySelector('.gl-card.lyrics-on .gl-lyrics');return p?Math.round(p.getBoundingClientRect().height):-1})()");
    report.lyricsPanelHeight = lyH;
    report.steps.push('hauteur panneau paroles (lyrics-on): ' + lyH + 'px');
    if (lyH < 100) throw new Error('Regression bug paroles: panneau .gl-lyrics hauteur ' + lyH + 'px (attendu >= 100)');
    // avancer dans le morceau pour activer une ligne
    await js('MDL_TEST.seekTo(0.45)');
    await sleep(2000);
    await shot('lyrics-karaoke');
    s = await st();
    report.lyricsLines = s.lyricsLines;
    report.ok = s.lyricsLines > 0 && lyH >= 100;
  } catch (e) { report.error = String(e && e.message || e); }
  fs.mkdirSync(shotDir, { recursive: true });
  fs.writeFileSync(path.join(shotDir, 'lyrics-report.json'), JSON.stringify(report, null, 2));
  app.exit(report.ok ? 0 : 1);
}

/* ══ E2E MINI : joue un titre, ouvre le mini vertical, capture ══ */
async function runMiniE2E() {
  const js = (code) => win.webContents.executeJavaScript(code, true);
  const shotDir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  try {
    await sleep(2500);
    await js('MDL_TEST.goLibrary(); MDL_TEST.playFirst();');
    await sleep(2500);
    await js("document.getElementById('mini-btn').click()"); // vrai flux (ouvre + envoie l'état)
    await sleep(2500);
    if (miniWin && !miniWin.isDestroyed()) {
      const measure = await miniWin.webContents.executeJavaScript("(()=>{const m=document.querySelector('.mini');const c=document.querySelector('.ctr');const r=c.getBoundingClientRect();return {winH:window.innerHeight,contentH:m.scrollHeight,ctrBottom:Math.round(r.bottom),gapBelowControls:Math.round(window.innerHeight-r.bottom)};})()", true);
      const img = await miniWin.webContents.capturePage();
      fs.mkdirSync(shotDir, { recursive: true });
      fs.writeFileSync(path.join(shotDir, 'mini-vertical.png'), img.toPNG());
      fs.writeFileSync(path.join(shotDir, 'mini-report.json'), JSON.stringify(measure, null, 2));
    }
  } catch (_) {}
  app.exit(0);
}

/* ══ E2E PAGE ARTISTE : ouvre une page artiste, verifie top titres + discographie ══ */
async function runArtistE2E() {
  const js = (code) => win.webContents.executeJavaScript(code, true);
  const shotDir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  const report = { ok: false, steps: [] };
  const st = async () => JSON.parse(await js('MDL_TEST.state()'));
  try {
    await sleep(2500);
    const name = process.env.MUSICDL_E2E_ARTIST_NAME || 'stormy';
    // Reproduire le bug A : une recherche en titres remplit #rc-list de cartes dont
    // certains ids se retrouvent aussi dans les top titres de la page artiste (collision).
    await js(`MDL_TEST.setTab('songs'); MDL_TEST.search(${JSON.stringify(name)})`);
    for (let i = 0; i < 20; i++) { await sleep(1000); const ss = await st(); if (ss.results > 0 || ss.searchError) break; }
    await js(`MDL_TEST.openArtist(${JSON.stringify(name)})`);
    let s = null;
    for (let i = 0; i < 30; i++) { await sleep(1000); s = await st(); if (s.artistOpen && (s.artistTop > 0 || s.artistAlbums > 0)) break; if (s.searchError) break; }
    if (!s || !s.artistOpen) throw new Error('Page artiste non ouverte: ' + JSON.stringify(s));
    report.artistName = s.artistName;
    report.top = s.artistTop;
    report.albums = s.artistAlbums;
    report.steps.push('page ouverte: ' + s.artistName + ' (top ' + s.artistTop + ', albums ' + s.artistAlbums + ')');
    if (s.artistTop < 1 || s.artistAlbums < 1) throw new Error('Top titres ou discographie vide: top=' + s.artistTop + ' albums=' + s.artistAlbums);
    await sleep(2500); // laisser charger les images reseau (photo + pochettes)
    report.photoLoaded = await js("(()=>{const i=document.querySelector('#art-photo img');return i?i.naturalWidth:-1})()");
    report.steps.push('photo artiste: ' + (report.photoLoaded > 0 ? 'chargee (' + report.photoLoaded + 'px)' : (report.photoLoaded === 0 ? 'presente mais non chargee' : 'img absente (photo nulle)')));
    // Bug A : chaque top titre doit avoir un bouton (telecharger / Telechargee), meme en cas de collision d'id
    report.topActsEmpty = await js("[...document.querySelectorAll('#art-top .rcard')].filter(c=>!c.querySelector('.rcard-acts').innerHTML.trim()).length");
    report.steps.push('boutons top titres: ' + (report.topActsEmpty === 0 ? 'tous presents' : report.topActsEmpty + ' ligne(s) SANS bouton'));
    if (report.topActsEmpty > 0) throw new Error('Bug A: ' + report.topActsEmpty + ' top titres sans bouton');
    await shot('artist-1-page');
    // Ouvrir le 1er album de la discographie -> vue album
    await js('MDL_TEST.openArtistAlbum(0)');
    for (let i = 0; i < 20; i++) { await sleep(1000); s = await st(); if (s.colTracks > 0) break; }
    if (s.colTracks > 0) { report.steps.push('album discographie ouvert: ' + (s.colTitle || '?') + ' (' + s.colTracks + ' titres)'); await sleep(400); await shot('artist-2-album'); }
    report.ok = true;
  } catch (e) { report.error = String(e && e.message || e); try { await shot('artist-9-erreur'); } catch (_) {} }
  fs.mkdirSync(shotDir, { recursive: true });
  fs.writeFileSync(path.join(shotDir, 'artist-report.json'), JSON.stringify(report, null, 2));
  app.exit(report.ok ? 0 : 1);
}

/* ══ E2E FILE D'ATTENTE : remplit la file, ouvre le panneau, reordonne, supprime ══ */
async function runQueueE2E() {
  const js = (code) => win.webContents.executeJavaScript(code, true);
  const shotDir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  const report = { ok: false, steps: [] };
  const st = async () => JSON.parse(await js('MDL_TEST.state()'));
  const order = async () => JSON.parse(await js('JSON.stringify(MDL_TEST.queueOrder())'));
  try {
    await sleep(2500);
    await js('MDL_TEST.goLibrary(); MDL_TEST.playFirst();');
    await sleep(2200);
    let s = await st();
    if (s.queueLen < 1) throw new Error('File vide apres lecture (bibliotheque vide ?)');
    // Grossir la file via "Ajouter a la file" pour pouvoir reordonner
    const q0 = await order();
    await js(`MDL_TEST.addQueueId(${JSON.stringify(q0[0])})`);
    await js(`MDL_TEST.addQueueId(${JSON.stringify(q0[q0.length - 1])})`);
    await sleep(400);
    await js('MDL_TEST.openQueue()');
    await sleep(700);
    s = await st();
    if (!s.queuePanelOpen) throw new Error('Panneau file non ouvert');
    report.steps.push('file ouverte: ' + s.queueLen + ' titres');
    await shot('queue-1-panel');
    const before = await order();
    if (before.length < 3) throw new Error('File trop courte pour reordonner: ' + before.length);
    // Reordonner : deplacer le dernier en 2e position (equivalent du drag&drop)
    await js(`MDL_TEST.moveQueue(${before.length - 1}, 1)`);
    await sleep(500);
    const after = await order();
    report.before = before;
    report.after = after;
    if (JSON.stringify(before) === JSON.stringify(after) || after[1] !== before[before.length - 1]) throw new Error('Reordonnancement KO');
    report.steps.push('reordonnancement ok (dernier -> position 2)');
    await shot('queue-2-reordered');
    // Retirer un element
    const lenBefore = after.length;
    await js(`MDL_TEST.removeQueueAt(${after.length - 1})`);
    await sleep(400);
    const afterRm = await order();
    if (afterRm.length !== lenBefore - 1) throw new Error('Suppression KO: ' + afterRm.length + ' au lieu de ' + (lenBefore - 1));
    report.steps.push('suppression file ok (' + lenBefore + ' -> ' + afterRm.length + ')');
    report.ok = true;
  } catch (e) { report.error = String(e && e.message || e); try { await shot('queue-9-erreur'); } catch (_) {} }
  fs.mkdirSync(shotDir, { recursive: true });
  fs.writeFileSync(path.join(shotDir, 'queue-report.json'), JSON.stringify(report, null, 2));
  app.exit(report.ok ? 0 : 1);
}

/* ══ E2E PLAYLISTS INTELLIGENTES : compteur d'ecoute + 3 cartes auto ══ */
async function runSmartE2E() {
  const js = (code) => win.webContents.executeJavaScript(code, true);
  const shotDir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  const report = { ok: false, steps: [] };
  const st = async () => JSON.parse(await js('MDL_TEST.state()'));
  try {
    await sleep(2500);
    await js('MDL_TEST.goLibrary(); MDL_TEST.playFirst();');
    await sleep(2200);
    let s = await st();
    if (!s.playing) throw new Error('Lecture non demarree (bibliotheque vide ?)');
    const before = s.playCount;
    await js('MDL_TEST.seekTo(0.55)'); // au-dela de 50% -> declenche le compteur
    let counted = false;
    for (let i = 0; i < 14; i++) { await sleep(700); s = await st(); if (s.playCount > before) { counted = true; break; } }
    if (!counted) throw new Error('Compteur d ecoute non incremente (' + before + ' -> ' + s.playCount + ')');
    report.steps.push('compteur d ecoute: ' + before + ' -> ' + s.playCount);
    await js('MDL_TEST.goPlaylists()');
    await sleep(800);
    const n = await js('MDL_TEST.smartCardCount()');
    report.smartCards = n;
    report.steps.push('cartes auto presentes: ' + n);
    if (n !== 3) throw new Error('Attendu 3 cartes auto, obtenu ' + n);
    await shot('smart-1-grid');
    await js("MDL_TEST.openSmart('top')");
    await sleep(800);
    s = await st();
    report.steps.push('detail ouvert: ' + s.colTitlePld + ' (' + s.pldTracks + ' titre[s])');
    if (s.colTitlePld !== 'Plus écoutés') throw new Error('Detail "Plus ecoutes" non ouvert: ' + s.colTitlePld);
    if (s.pldTracks < 1) throw new Error('"Plus ecoutes" vide alors qu un titre a ete ecoute');
    await shot('smart-2-top');
    report.ok = true;
  } catch (e) { report.error = String(e && e.message || e); try { await shot('smart-9-erreur'); } catch (_) {} }
  fs.mkdirSync(shotDir, { recursive: true });
  fs.writeFileSync(path.join(shotDir, 'smart-report.json'), JSON.stringify(report, null, 2));
  app.exit(report.ok ? 0 : 1);
}

/* ══ E2E ONLINE/BIBLIO (features session v1.3) : favoris online, playlists online,
   albums sauvegardes, classifieur albums/singles, telechargement par titre + global,
   lecture en streaming, banniere artiste, selection + suppression groupee ══ */
async function runOnlineE2E() {
  const js = (code) => win.webContents.executeJavaScript(code, true);
  const shotDir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  const report = { ok: false, steps: [] };
  const st = async () => JSON.parse(await js('MDL_TEST.state()'));
  const q = process.env.MUSICDL_E2E_QUERY || 'shaw';
  const waitFor = async (pred, tries, ms) => { let s = null; for (let i = 0; i < tries; i++) { await sleep(ms); s = await st(); if (pred(s)) return s; } return s; };
  try {
    await sleep(2500);
    await shot('on-01-accueil');
    report.steps.push('shot accueil');

    // 1) Recherche titres
    await js(`MDL_TEST.setTab('songs'); MDL_TEST.search(${JSON.stringify(q)})`);
    let s = await waitFor((x) => x.results > 0 || x.searchError, 60, 1000);
    if (!s.results) throw new Error('Recherche titres KO: ' + JSON.stringify(s.searchError));
    report.steps.push('recherche titres ok: ' + s.results);
    await sleep(1500); await shot('on-02-resultats');

    // 2) Favori EN LIGNE d'un titre non telecharge
    const onlineId = await js('MDL_TEST.resultId(0)');
    await js('MDL_TEST.favResult(0)');
    s = await waitFor((x) => x.onlineFav >= 1 || x.onlineMeta >= 1, 10, 500);
    const isFav = await js('MDL_TEST.isResultFav(0)');
    if (!isFav || s.onlineFav < 1) throw new Error('Favori online KO: onlineFav=' + s.onlineFav + ' isFav=' + isFav);
    report.steps.push('favori online ok (onlineMeta=' + s.onlineMeta + ', fav=' + s.onlineFav + ')');

    // 3) Banniere artiste cliquable -> page artiste
    const hadBand = await js('MDL_TEST.clickArtistBand()');
    if (hadBand) {
      s = await waitFor((x) => x.artistOpen, 20, 700);
      report.steps.push('banniere artiste -> page artiste: ' + (s.artistOpen ? 'ok (' + s.artistName + ')' : 'NON ouverte'));
      if (!s.artistOpen) throw new Error('Page artiste non ouverte via banniere');
      await sleep(1200); await shot('on-03-artiste');
      // revenir aux titres
      await js(`MDL_TEST.setTab('songs'); MDL_TEST.search(${JSON.stringify(q)})`);
      await waitFor((x) => x.results > 0, 30, 1000);
    } else { report.steps.push('banniere artiste: absente pour cette requete (skip)'); }

    // 4) Ajout d'un titre online a une NOUVELLE playlist
    const before4 = (await st()).onlineMeta;
    await js("MDL_TEST.addResultToNewPl(1, 'E2E Playlist')");
    s = await waitFor((x) => x.onlineMeta >= before4, 10, 500);
    report.steps.push('ajout titre online a une playlist ok (onlineMeta=' + s.onlineMeta + ')');

    // 5) Favoris : le titre online apparait
    await js("MDL_TEST.openFav()");
    s = await waitFor((x) => x.favTotal >= 1, 10, 500);
    if (s.favTotal < 1) throw new Error('Favoris vide alors qu un titre online est favori');
    report.steps.push('favoris affiche le titre online ok (favTotal=' + s.favTotal + ')');
    await sleep(800); await shot('on-04-favoris');

    // 6) Lecture EN STREAMING du titre online (par son id, pas le 1er favori qui peut etre local)
    await js(`MDL_TEST.playId(${JSON.stringify(onlineId)})`);
    s = await waitFor((x) => x.curOnline, 12, 500);
    if (!s.curOnline) throw new Error('Lecture online non demarree (curOnline=false)');
    s = await waitFor((x) => x.playing, 40, 1000);     // stream reseau : marge large
    report.steps.push('lecture streaming online: ' + (s.playing ? 'ok (en lecture)' : 'curOnline ok, audio en chargement'));
    await sleep(800); await shot('on-05-stream');

    // 7) Recherche ALBUMS + enregistrement d'un album dans l'onglet Albums
    await js(`MDL_TEST.setTab('albums'); MDL_TEST.search(${JSON.stringify(q)})`);
    s = await waitFor((x) => x.collections > 0 || x.searchError, 40, 1000);
    if (!s.collections) throw new Error('Recherche albums KO');
    report.steps.push('recherche albums ok: ' + s.collections);
    const savedBefore = s.onlineSaved;
    await js('MDL_TEST.saveAlbum(0)');
    s = await waitFor((x) => x.onlineSaved > savedBefore, 30, 1000);
    if (s.onlineSaved <= savedBefore) throw new Error('Album non enregistre (onlineSaved ' + savedBefore + ' -> ' + s.onlineSaved + ')');
    report.steps.push('album enregistre dans Albums ok (onlineSaved=' + s.onlineSaved + ')');

    // 8) Onglet Albums : l'album sauvegarde est classe comme ALBUM (pas single)
    await js("MDL_TEST.setLibTab('albums')");
    s = await waitFor((x) => x.libAlbumsN >= 1, 10, 500);
    if (s.libAlbumsN < 1) throw new Error('Aucun album classe (libAlbumsN=0)');
    report.steps.push('classifieur: ' + s.libAlbumsN + ' album(s), ' + s.libSinglesN + ' single(s)');
    const albName = await js('MDL_TEST.firstLibAlbumName()');
    await js(`MDL_TEST.openLibAlbum(${JSON.stringify(albName)})`);
    await sleep(1200); await shot('on-06-album-online');

    // 8b) Page "Pour toi" : reco basee sur l'artiste consulte (banniere -> interet enregistre)
    await js('MDL_TEST.goDiscover(true)');
    s = await waitFor((x) => x.discoTracks > 0, 45, 1000);
    report.steps.push('page Pour toi: ' + s.discoTracks + ' titre(s) recommande(s) (' + s.interests + ' interet[s])');
    if (s.interests > 0 && s.discoTracks < 1) throw new Error('Reco vide alors qu un artiste a ete consulte');
    await sleep(800); await shot('on-06b-pourtoi');

    // 9) Telechargement de TOUT l'album online -> les titres deviennent locaux
    const libBefore = (await st()).library;
    const clicked = await js('MDL_TEST.dlOnlineInAlbum()');
    if (clicked) {
      s = await waitFor((x) => x.library > libBefore, 90, 1000);   // telechargement reseau : marge tres large
      report.steps.push('telechargement album online: bibliotheque ' + libBefore + ' -> ' + s.library + (s.library > libBefore ? ' ok' : ' (lent/en cours)'));
    } else { report.steps.push('bouton telecharger album: absent (skip)'); }
    await sleep(800); await shot('on-07-album-dl');

    // 10) Selection + suppression groupee dans Titres
    await js("MDL_TEST.setLibTab('titres')");
    await sleep(600);
    await js('MDL_TEST.selectAllLib()');
    await sleep(500);
    const sel = await js('MDL_TEST.countSelected()');
    report.steps.push('mode selection: ' + sel + ' titre(s) selectionne(s)');
    if (sel > 0) {
      const libB = (await st()).library;
      await js('MDL_TEST.deleteSelection()');
      s = await waitFor((x) => x.library < libB, 15, 700);
      report.steps.push('suppression groupee: ' + libB + ' -> ' + s.library + (s.library < libB ? ' ok' : ' (inchange)'));
      if (s.library >= libB) throw new Error('Suppression groupee sans effet');
    } else { report.steps.push('selection vide (aucun titre telecharge a supprimer) — skip'); }
    await sleep(600); await shot('on-08-fin');

    // 11) Aucune erreur JS
    const errs = JSON.parse(await js('JSON.stringify(MDL_TEST.jsErrors())'));
    report.jsErrors = errs;
    if (errs.length) throw new Error('Erreurs JS detectees: ' + errs.slice(0, 3).join(' | '));
    report.steps.push('aucune erreur JS');

    report.ok = true;
  } catch (e) { report.error = String(e && e.message || e); try { await shot('on-99-erreur'); } catch (_) {} }
  fs.mkdirSync(shotDir, { recursive: true });
  fs.writeFileSync(path.join(shotDir, 'online-report.json'), JSON.stringify(report, null, 2));
  app.exit(report.ok ? 0 : 1);
}

/* ══ E2E TORTURE : clique tout dans tous les états, traque les erreurs JS ══ */
async function runTortureE2E() {
  const js = (code) => win.webContents.executeJavaScript(code, true);
  const shotDir = process.env.MUSICDL_SHOT_DIR || path.join(__dirname, '..', 'shots');
  const report = { ok: false, steps: [], bugs: [] };
  const st = async () => JSON.parse(await js('MDL_TEST.state()'));
  const errs = async () => JSON.parse(await js('JSON.stringify(MDL_TEST.jsErrors())'));
  try {
    await sleep(2500);

    // 1) S'assurer d'avoir au moins 2 titres en bibliothèque
    let s = await st();
    if (s.library < 2) {
      await js(`MDL_TEST.search('daft punk')`);
      for (let i = 0; i < 40; i++) { await sleep(1000); s = await st(); if (s.results > 1) break; }
      await js('MDL_TEST.downloadFirst()');
      // 2e titre
      await js('MDL_TEST.search("the weeknd blinding lights")');
      for (let i = 0; i < 30; i++) { await sleep(1000); s = await st(); if (s.results > 0) break; }
      await js('MDL_TEST.downloadFirst()');
      for (let i = 0; i < 240; i++) { await sleep(1000); s = await st(); if (s.library >= 2 && s.queue === 0) break; }
    }
    if (s.library < 1) throw new Error('Impossible de préparer la bibliothèque');
    report.steps.push('bibliothèque prête: ' + s.library + ' titres');

    // 2) Torture du lecteur : tous les boutons dans tous les états
    await js('MDL_TEST.goLibrary(); MDL_TEST.playFirst();');
    await sleep(2500);
    const seq = [
      'MDL_TEST.togglePlay()', 'MDL_TEST.togglePlay()',           // pause/play
      'MDL_TEST.next()', 'MDL_TEST.next()', 'MDL_TEST.prev()',    // navigation
      'MDL_TEST.toggleShuffle()', 'MDL_TEST.toggleShuffle()',
      'MDL_TEST.cycleRepeat()', 'MDL_TEST.cycleRepeat()', 'MDL_TEST.cycleRepeat()', 'MDL_TEST.cycleRepeat()',
      'MDL_TEST.setVol(0)', 'MDL_TEST.setVol(1)', 'MDL_TEST.toggleMute()', 'MDL_TEST.toggleMute()',
      'MDL_TEST.seekTo(0.92)', 'MDL_TEST.seekTo(0.1)', 'MDL_TEST.seekTo(0.5)',
      'MDL_TEST.openGL()', 'MDL_TEST.closeGL()'
    ];
    for (const cmd of seq) { await js(cmd); await sleep(250); }
    s = await st();
    report.steps.push('torture lecteur ok (repeat=' + s.repeatMode + ' shuffle=' + s.shuffleOn + ')');

    // 3) Torture bibliothèque : tri sur chaque colonne (asc+desc) + filtre
    for (const col of ['title', 'artist', 'album', 'year', 'duration']) {
      await js(`MDL_TEST.sortBy('${col}')`); await sleep(150);
      await js(`MDL_TEST.sortBy('${col}')`); await sleep(150);
    }
    await js(`MDL_TEST.setFilter('a')`); await sleep(300);
    await js(`MDL_TEST.setFilter('')`); await sleep(300);
    report.steps.push('torture bibliothèque ok (tri 5 colonnes + filtre)');
    await shot('t1-apres-torture');

    // 4) TEST CLÉ — fichier introuvable (bug n°1) : on renomme un vrai mp3
    const track = store.library[0];
    const realFile = track.file;
    const bakFile = realFile + '.moved';
    let renamed = false;
    try {
      fs.renameSync(realFile, bakFile);
      renamed = true;
      // forcer la lecture de CE titre cassé (file d'un seul élément)
      await js(`MDL_TEST.playId(${JSON.stringify(track.id)})`);
      let frozen = true;
      for (let i = 0; i < 8; i++) {
        await sleep(1000);
        s = await st();           // si l'app répond encore, elle n'est pas figée
        if (s && s.playing === false) { frozen = false; break; }   // doit s'arrêter proprement
        if (s) frozen = false;
      }
      if (frozen) { report.bugs.push('FIGÉ sur fichier introuvable'); throw new Error('app figée sur fichier introuvable'); }
      report.steps.push('fichier introuvable géré sans blocage (app répond, lecture arrêtée)');
    } finally {
      if (renamed && fs.existsSync(bakFile)) { try { fs.renameSync(bakFile, realFile); } catch (_) {} }
    }
    await shot('t2-fichier-introuvable');

    // 5) Suppression d'un titre puis vérif que la file ne casse pas
    s = await st();
    const libBefore = s.library;
    if (libBefore >= 2) {
      await js('MDL_TEST.playFirst();'); await sleep(1500);
      await js('MDL_TEST.deleteFirstLib();'); await sleep(1500);
      s = await st();
      if (s.library !== libBefore - 1) report.bugs.push('suppression: compte incohérent ' + s.library + '/' + (libBefore - 1));
      else report.steps.push('suppression pendant lecture ok (' + libBefore + ' → ' + s.library + ')');
    }

    // 6) Bilan des erreurs JS
    const errList = await errs();
    s = await st();
    report.jsErrors = errList;
    report.responsive = !!s;
    report.ok = errList.length === 0 && report.bugs.length === 0 && report.responsive;
    if (errList.length) report.bugs.push('erreurs JS: ' + errList.join(' | '));
    report.steps.push('bilan: ' + errList.length + ' erreur(s) JS, ' + report.bugs.length + ' bug(s)');
  } catch (e) {
    report.error = String(e && e.message || e);
    try { await shot('t9-erreur'); } catch (_) {}
  }
  fs.mkdirSync(shotDir, { recursive: true });
  fs.writeFileSync(path.join(shotDir, 'torture-report.json'), JSON.stringify(report, null, 2));
  app.exit(report.ok ? 0 : 1);
}

/* ══ Démarrage ══ */
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
  });

  app.whenReady().then(() => {
    /* Sert MP3/pochettes locaux avec support des Range requests
       (indispensable pour pouvoir naviguer dans un titre en lecture). */
    protocol.handle('mdl', (request) => {
      try {
        const u = new URL(request.url);
        const p = decodeURIComponent(u.searchParams.get('p') || '');
        if (!p || !fs.existsSync(p)) return new Response('', { status: 404 });
        const size = fs.statSync(p).size;
        const ext = path.extname(p).toLowerCase();
        const mime = { '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' }[ext] || 'application/octet-stream';
        const range = request.headers.get('Range') || request.headers.get('range');
        if (range) {
          const m = range.match(/bytes=(\d*)-(\d*)/);
          let start = m && m[1] ? parseInt(m[1], 10) : 0;
          let end = m && m[2] ? parseInt(m[2], 10) : size - 1;
          if (isNaN(start) || start >= size) {
            return new Response('', { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
          }
          end = Math.min(isNaN(end) ? size - 1 : end, size - 1);
          return new Response(Readable.toWeb(fs.createReadStream(p, { start, end })), {
            status: 206,
            headers: {
              'Content-Type': mime,
              'Content-Length': String(end - start + 1),
              'Content-Range': `bytes ${start}-${end}/${size}`,
              'Accept-Ranges': 'bytes'
            }
          });
        }
        return new Response(Readable.toWeb(fs.createReadStream(p)), {
          status: 200,
          headers: { 'Content-Type': mime, 'Content-Length': String(size), 'Accept-Ranges': 'bytes' }
        });
      } catch (_) {
        return new Response('', { status: 404 });
      }
    });
    ensureDirs();
    createWindow();
    createTray();
    setupUpdater();
    app.on('before-quit', () => { quitting = true; });
    if (process.env.MUSICDL_E2E) {
      win.webContents.once('did-finish-load', () => runE2E());
    } else if (process.env.MUSICDL_E2E_UPDATE) {
      win.webContents.once('did-finish-load', () => runUpdateE2E());
    } else if (process.env.MUSICDL_E2E_TORTURE) {
      win.webContents.once('did-finish-load', () => runTortureE2E());
    } else if (process.env.MUSICDL_E2E_MINI) {
      win.webContents.once('did-finish-load', () => runMiniE2E());
    } else if (process.env.MUSICDL_E2E_LYRICS) {
      win.webContents.once('did-finish-load', () => runLyricsE2E());
    } else if (process.env.MUSICDL_E2E_ARTIST) {
      win.webContents.once('did-finish-load', () => runArtistE2E());
    } else if (process.env.MUSICDL_E2E_QUEUE) {
      win.webContents.once('did-finish-load', () => runQueueE2E());
    } else if (process.env.MUSICDL_E2E_SMART) {
      win.webContents.once('did-finish-load', () => runSmartE2E());
    } else if (process.env.MUSICDL_E2E_ONLINE) {
      win.webContents.once('did-finish-load', () => runOnlineE2E());
    }
  });

  app.on('window-all-closed', () => app.quit());
}
