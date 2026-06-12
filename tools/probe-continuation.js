/* Teste des variantes de params "chansons" pour obtenir un jeton de continuation */
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
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}
function walk(node, fn) {
  if (!node || typeof node !== 'object') return;
  fn(node);
  if (Array.isArray(node)) { node.forEach((n) => walk(n, fn)); return; }
  for (const k of Object.keys(node)) walk(node[k], fn);
}
function count(data) { let c = 0; walk(data, (n) => { if (n.musicResponsiveListItemRenderer) c++; }); return c; }
function token(data) {
  let t = null;
  walk(data, (n) => {
    if (t) return;
    if (n.nextContinuationData && n.nextContinuationData.continuation) t = n.nextContinuationData.continuation;
    if (n.continuationCommand && n.continuationCommand.token) t = n.continuationCommand.token;
  });
  return t;
}
function firstTitle(data) {
  let t = null;
  walk(data, (n) => {
    if (t) return;
    const r = n.musicResponsiveListItemRenderer;
    if (r && r.flexColumns && r.flexColumns[0]) {
      const runs = r.flexColumns[0].musicResponsiveListItemFlexColumnRenderer.text.runs;
      if (runs && runs[0]) t = runs[0].text;
    }
  });
  return t;
}

(async () => {
  const variants = {
    actuel: 'EgWKAQIIAWoQEAMQBBAJEAoQBRAREBAQFQ%3D%3D',
    v_ytmusicapi: 'EgWKAQIIAUICCAFqChAEEAMQCRAFEAo%3D',
    v_sans_suffixe: 'EgWKAQII',
    v_spelling: 'EgWKAQIIAWoMEA4QChADEAQQCRAF'
  };
  for (const [name, params] of Object.entries(variants)) {
    try {
      const d = await api('search', { query: 'stormy', params });
      const tok = token(d);
      console.log(`${name}: ${count(d)} items | 1er="${firstTitle(d)}" | token=${tok ? 'OUI' : 'non'}`);
      if (tok) {
        const d2 = await api(`search?ctoken=${encodeURIComponent(tok)}&continuation=${encodeURIComponent(tok)}`, {});
        console.log(`   page2: ${count(d2)} items | token2=${token(d2) ? 'OUI' : 'non'} | 1er="${firstTitle(d2)}"`);
      }
    } catch (e) { console.log(`${name}: ERREUR ${e.message}`); }
  }
})();
