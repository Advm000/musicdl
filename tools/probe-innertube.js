/* Sonde l'API InnerTube : filtres de recherche albums/playlists + browse d'album.
   Usage: node tools/probe-innertube.js */
const CTX = { client: { clientName: 'WEB_REMIX', clientVersion: '1.20250602.01.00', hl: 'fr', gl: 'FR' } };
const HEADERS = {
  'Content-Type': 'application/json',
  'Origin': 'https://music.youtube.com',
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
};

async function api(endpoint, body) {
  const res = await fetch(`https://music.youtube.com/youtubei/v1/${endpoint}?prettyPrint=false`, {
    method: 'POST', headers: HEADERS, body: JSON.stringify({ context: CTX, ...body })
  });
  if (!res.ok) throw new Error(endpoint + ' HTTP ' + res.status);
  return res.json();
}

function walk(node, fn) {
  if (!node || typeof node !== 'object') return;
  fn(node);
  if (Array.isArray(node)) { node.forEach((n) => walk(n, fn)); return; }
  for (const k of Object.keys(node)) walk(node[k], fn);
}

function items(data) {
  const out = [];
  walk(data, (n) => { if (n.musicResponsiveListItemRenderer) out.push(n.musicResponsiveListItemRenderer); });
  return out;
}
function runsText(col) {
  return ((col && col.musicResponsiveListItemFlexColumnRenderer && col.musicResponsiveListItemFlexColumnRenderer.text && col.musicResponsiveListItemFlexColumnRenderer.text.runs) || []).map((r) => r.text).join('');
}
function describe(r) {
  const vid = r.playlistItemData && r.playlistItemData.videoId;
  const browse = r.navigationEndpoint && r.navigationEndpoint.browseEndpoint;
  const pageType = browse && browse.browseEndpointContextSupportedConfigs && browse.browseEndpointContextSupportedConfigs.browseEndpointContextMusicConfig && browse.browseEndpointContextSupportedConfigs.browseEndpointContextMusicConfig.pageType;
  const cols = (r.flexColumns || []).map(runsText);
  const fixed = ((r.fixedColumns || [])[0] || {});
  const fixedTxt = fixed.musicResponsiveListItemFixedColumnRenderer && fixed.musicResponsiveListItemFixedColumnRenderer.text && (fixed.musicResponsiveListItemFixedColumnRenderer.text.runs || []).map((x) => x.text).join('');
  return { vid: vid || null, browseId: (browse && browse.browseId) || null, pageType: pageType || null, cols, fixed: fixedTxt || null };
}

(async () => {
  const PARAMS = {
    songs: 'EgWKAQIIAWoQEAMQBBAJEAoQBRAREBAQFQ%3D%3D',
    albums: 'EgWKAQIYAWoQEAMQBBAJEAoQBRAREBAQFQ%3D%3D',
    playlists: 'Eg-KAQwIABAAGAAgACgBMABqChAEEAMQCRAFEAo%3D'
  };
  for (const [name, params] of Object.entries(PARAMS)) {
    try {
      const data = await api('search', { query: 'daft punk', params });
      const its = items(data).slice(0, 3).map(describe);
      console.log('=== FILTRE', name, '→', its.length, 'premiers items ===');
      its.forEach((d) => console.log(JSON.stringify(d)));
    } catch (e) {
      console.log('=== FILTRE', name, 'ERREUR:', e.message);
    }
  }

  // Browse d'un album (premier browseId MPREb trouvé via filtre albums)
  try {
    const data = await api('search', { query: 'daft punk discovery', params: PARAMS.albums });
    let albumId = null;
    walk(data, (n) => {
      if (!albumId && n.browseEndpoint && /^MPREb/.test(n.browseEndpoint.browseId || '')) albumId = n.browseEndpoint.browseId;
    });
    console.log('=== BROWSE ALBUM', albumId, '===');
    const alb = await api('browse', { browseId: albumId });
    // Header
    let header = null;
    walk(alb, (n) => {
      if (!header && (n.musicDetailHeaderRenderer || n.musicResponsiveHeaderRenderer)) header = n.musicDetailHeaderRenderer || n.musicResponsiveHeaderRenderer;
    });
    if (header) {
      const title = header.title && header.title.runs && header.title.runs[0].text;
      const sub = (header.subtitle && header.subtitle.runs || []).map((r) => r.text).join('') || (header.straplineTextOne && header.straplineTextOne.runs || []).map((r) => r.text).join('');
      console.log('HEADER:', JSON.stringify({ title, sub }));
    } else console.log('HEADER: introuvable');
    const tracks = items(alb).slice(0, 4).map(describe);
    tracks.forEach((d) => console.log('TRACK:', JSON.stringify(d)));
    // thumbnail album
    let thumb = null;
    walk(alb, (n) => { if (!thumb && n.musicThumbnailRenderer && n.musicThumbnailRenderer.thumbnail) { const t = n.musicThumbnailRenderer.thumbnail.thumbnails; thumb = t[t.length - 1].url; } });
    console.log('THUMB:', thumb);
  } catch (e) {
    console.log('BROWSE ERREUR:', e.message);
  }
})();
