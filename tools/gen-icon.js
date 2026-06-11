/* Génère build/icon.ico + build/icon.png depuis le logo SVG officiel */
const sharp = require('sharp');
const pngToIcoMod = require('png-to-ico');
const pngToIco = pngToIcoMod.default || pngToIcoMod;
const fs = require('fs');
const path = require('path');

const SVG = Buffer.from(`<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4f88f8"/>
      <stop offset="1" stop-color="#1dd3b0"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="118" fill="url(#g)"/>
  <g transform="translate(96,96) scale(13.3333)">
    <rect x="1" y="15" width="4" height="8" rx="2" fill="white" opacity=".9"/>
    <rect x="7" y="10" width="4" height="13" rx="2" fill="white"/>
    <rect x="13" y="12" width="4" height="11" rx="2" fill="white" opacity=".9"/>
    <path d="M20 4v9" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>
    <path d="M18 10l2 3 2-3" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  </g>
</svg>`);

(async () => {
  const out = path.join(__dirname, '..', 'build');
  fs.mkdirSync(out, { recursive: true });
  await sharp(SVG).resize(512, 512).png().toFile(path.join(out, 'icon.png'));
  const sizes = [256, 128, 64, 48, 32, 24, 16];
  const bufs = await Promise.all(sizes.map((s) => sharp(SVG).resize(s, s).png().toBuffer()));
  const ico = await pngToIco(bufs);
  fs.writeFileSync(path.join(out, 'icon.ico'), ico);
  console.log('OK — build/icon.ico (' + Math.round(ico.length / 1024) + ' KB) + build/icon.png');
})().catch((e) => { console.error(e); process.exit(1); });
