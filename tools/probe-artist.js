const CTX = { client: { clientName: 'WEB_REMIX', clientVersion: '1.20250602.01.00', hl: 'fr', gl: 'FR' } };
const H = { 'Content-Type': 'application/json', 'Origin': 'https://music.youtube.com', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36' };
const api = (e, b) => fetch('https://music.youtube.com/youtubei/v1/' + e + '?prettyPrint=false', { method: 'POST', headers: H, body: JSON.stringify({ context: CTX, ...b }) }).then(r => r.json());
const walk = (n, fn) => { if (!n || typeof n !== 'object') return; fn(n); if (Array.isArray(n)) { n.forEach(x => walk(x, fn)); return; } for (const k of Object.keys(n)) walk(n[k], fn); };

(async () => {
  // trouver l'id artiste Stormy
  const s = await api('search', { query: 'stormy', params: 'EgWKAQIgAWoQEAMQBBAJEAoQBRAREBAQFQ%3D%3D' });
  let artistId = null;
  walk(s, (n) => { if (!artistId && n.musicResponsiveListItemRenderer) { const be = n.musicResponsiveListItemRenderer.navigationEndpoint && n.musicResponsiveListItemRenderer.navigationEndpoint.browseEndpoint; if (be && /^UC/.test(be.browseId)) artistId = be.browseId; } });
  console.log('artistId:', artistId);
  const p = await api('browse', { browseId: artistId });

  // header
  let h = null;
  walk(p, (n) => { if (!h && (n.musicImmersiveHeaderRenderer || n.musicVisualHeaderRenderer || n.musicHeaderRenderer)) h = n.musicImmersiveHeaderRenderer || n.musicVisualHeaderRenderer || n.musicHeaderRenderer; });
  if (h) {
    const name = h.title && h.title.runs && h.title.runs[0].text;
    const desc = h.description && h.description.musicDescriptionShelfRenderer;
    let subscribers = null;
    walk(h, (n) => { if (n.subscriberCountText && n.subscriberCountText.runs) subscribers = n.subscriberCountText.runs.map(r => r.text).join(''); });
    let thumb = null;
    walk(h, (n) => { if (!thumb && n.thumbnails && Array.isArray(n.thumbnails)) thumb = n.thumbnails[n.thumbnails.length - 1].url; });
    console.log('HEADER name:', name, '| subs:', subscribers, '| thumb:', thumb && thumb.slice(0, 70));
  } else console.log('header type introuvable — clés racine:', Object.keys(p).join(','));

  // top songs (musicResponsiveListItemRenderer avec videoId)
  const songs = [];
  walk(p, (n) => {
    const r = n.musicResponsiveListItemRenderer;
    if (!r) return;
    const vid = r.playlistItemData && r.playlistItemData.videoId;
    if (!vid) return;
    const cols = (r.flexColumns || []).map(c => { const t = c.musicResponsiveListItemFlexColumnRenderer; return (t && t.text && t.text.runs) || []; });
    const title = cols[0] && cols[0][0] && cols[0][0].text;
    if (title) songs.push({ vid, title, sub: cols.slice(1).flat().map(x => x.text).join('') });
  });
  console.log('TOP SONGS:', songs.length);
  songs.slice(0, 5).forEach(s => console.log('  ', s.title, '|', s.sub));
})();
