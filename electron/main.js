const { app, BrowserWindow, Menu, shell, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')
const fs   = require('fs')
const os   = require('os')

let mainWindow   = null
let loadingWin   = null
let flaskProcess = null
const PORT = 5000

// Log file dans %LOCALAPPDATA%\MusicDL\
const LOG_DIR  = path.join(process.env.LOCALAPPDATA || os.homedir(), 'MusicDL')
const LOG_FILE = path.join(LOG_DIR, 'backend.log')

function log(msg) {
  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true })
    fs.appendFileSync(LOG_FILE, `[${new Date().toISOString()}] ${msg}\n`)
  } catch(e) {}
}

// Une seule instance
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) { app.quit() }
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  }
})

function getBackendExe() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend', 'MusicDL.exe')
  }
  return null
}

function showLoading() {
  loadingWin = new BrowserWindow({
    width: 320, height: 200,
    frame: false, resizable: false, center: true,
    backgroundColor: '#0b0b1a', alwaysOnTop: true,
    webPreferences: { nodeIntegration: false }
  })
  Menu.setApplicationMenu(null)
  loadingWin.loadURL('data:text/html,' + encodeURIComponent(`
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>
      body{margin:0;background:#0b0b1a;color:#e2e8f0;font-family:system-ui;
           display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh}
      .logo{width:56px;height:56px;border-radius:16px;
            background:linear-gradient(135deg,#7c3aed,#22d3ee);
            display:flex;align-items:center;justify-content:center;margin-bottom:16px}
      h2{margin:0 0 8px;font-size:1.2rem;font-weight:700}
      p{margin:0;font-size:.85rem;color:#94a3b8}
      .dot{display:inline-block;width:6px;height:6px;border-radius:50%;
           background:#7c3aed;margin:0 3px;animation:pulse 1.2s infinite}
      .dot:nth-child(2){animation-delay:.2s}.dot:nth-child(3){animation-delay:.4s}
      @keyframes pulse{0%,80%,100%{opacity:.3}40%{opacity:1}}
    </style></head><body>
    <div class="logo"><svg width="30" height="30" viewBox="0 0 24 24" fill="white">
      <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
    </svg></div>
    <h2>Music DL</h2>
    <p>Démarrage<span class="dot"></span><span class="dot"></span><span class="dot"></span></p>
    </body></html>
  `))
}

function startFlask() {
  const exe = getBackendExe()
  if (!exe) { log('Dev mode — no backend to start'); return }

  // Verifier que l'exe existe
  if (!fs.existsSync(exe)) {
    log('ERROR: backend exe not found at: ' + exe)
    dialog.showErrorBox('Music DL',
      'Fichier manquant :\n' + exe + '\n\nRéinstallez l\'application.')
    app.quit()
    return
  }

  log('Starting backend: ' + exe)

  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true })
  } catch(e) {}

  const logStream = fs.createWriteStream(LOG_FILE, { flags: 'a' })
  logStream.write('\n--- BACKEND START ' + new Date().toISOString() + ' ---\n')

  flaskProcess = spawn(exe, ['--no-browser'], {
    windowsHide: true,
    detached: false,
    stdio: ['ignore', 'pipe', 'pipe'],
    cwd: path.dirname(exe),  // lancer depuis son propre dossier
  })

  if (flaskProcess.stdout) flaskProcess.stdout.pipe(logStream)
  if (flaskProcess.stderr) flaskProcess.stderr.pipe(logStream)

  flaskProcess.on('error', (err) => {
    log('Spawn error: ' + err.message)
  })

  flaskProcess.on('exit', (code, signal) => {
    log('Backend exited — code=' + code + ' signal=' + signal)
  })
}

function waitForFlask(retries = 90, delay = 666) {
  // 90 * 666ms = ~60 secondes
  return new Promise((resolve, reject) => {
    let n = 0
    const try_ = () => {
      const req = http.get(`http://localhost:${PORT}/`, (res) => {
        log('Backend responded on port ' + PORT)
        resolve()
      })
      req.on('error', () => {
        if (++n >= retries) return reject(new Error('Timeout after ' + (retries * delay / 1000) + 's'))
        setTimeout(try_, delay)
      })
      req.setTimeout(500, () => req.destroy())
    }
    try_()
  })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 760,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0b0b1a',
    show: false,
    title: 'Music DL',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      devTools: !app.isPackaged,
    },
  })

  Menu.setApplicationMenu(null)
  mainWindow.loadURL(`http://localhost:${PORT}`)

  mainWindow.once('ready-to-show', () => {
    if (loadingWin) { loadingWin.close(); loadingWin = null }
    mainWindow.show()
    mainWindow.focus()
  })

  if (app.isPackaged) {
    mainWindow.webContents.on('context-menu', (e) => e.preventDefault())
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith('http://localhost')) shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => { mainWindow = null })
}

app.whenReady().then(async () => {
  showLoading()
  startFlask()

  try {
    await waitForFlask()
    createWindow()
  } catch (err) {
    log('Fatal: ' + err.message)

    let logContent = ''
    try { logContent = '\n\nLog : ' + LOG_FILE } catch(e) {}

    if (loadingWin) { loadingWin.close(); loadingWin = null }

    dialog.showErrorBox('Music DL — Erreur de démarrage',
      'Le backend Flask n\'a pas pu démarrer en 60 secondes.\n\n' +
      'Solutions :\n' +
      '1. Relancez l\'application\n' +
      '2. Vérifiez qu\'aucun antivirus ne bloque MusicDL.exe\n' +
      '3. Désinstallez et réinstallez\n' +
      logContent
    )
    app.quit()
  }
})

app.on('window-all-closed', () => {
  if (flaskProcess) { try { flaskProcess.kill() } catch (e) {} }
  app.quit()
})

app.on('before-quit', () => {
  if (flaskProcess) { try { flaskProcess.kill() } catch (e) {} }
})
