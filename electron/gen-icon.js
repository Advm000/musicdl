const fs   = require('fs')
const path = require('path')

async function main() {
  const sharp = require('sharp')
  const svgBuf = fs.readFileSync(path.join(__dirname, '..', 'icon.svg'))
  await sharp(svgBuf, { density: 300 })
    .resize(512, 512)
    .png()
    .toFile(path.join(__dirname, 'icon.png'))
  console.log('icon.png generated (512x512)')
}

main().catch(e => { console.error('gen-icon failed:', e.message); process.exit(1) })
