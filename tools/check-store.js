const fs = require('fs');
const path = require('path');
const p = path.join(process.env.APPDATA, 'Music DL', 'store.json');
if (!fs.existsSync(p)) { console.log('ABSENT:', p); process.exit(0); }
const raw = fs.readFileSync(p, 'utf8');
console.log('store.json taille:', raw.length);
let nulls = 0;
for (let i = 0; i < raw.length; i++) if (raw.charCodeAt(i) === 0) nulls++;
console.log('octets nuls:', nulls);
try {
  const s = JSON.parse(raw);
  console.log('JSON valide. library:', (s.library || []).length, 'titres | playlists:', (s.playlists || []).length);
} catch (e) {
  console.log('JSON INVALIDE:', e.message);
  console.log('premiers 120 car:', JSON.stringify(raw.slice(0, 120)));
}
