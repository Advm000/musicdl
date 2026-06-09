const { app, BrowserWindow, Menu, shell, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')

let mainWindow = null
let flaskProcess = null
const PORT = 5000

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
  return null // mode dev: lancer MusicDownloader.py manuellement
}

function startFlask() {
  const exe = getBackendExe()
  if (!exe) return

  flaskProcess = spawn(exe, ['--no-browser'], {
    windowsHide: true,
    detached: false,
  })
  flaskProcess.on('error', (err) => console.error('Backend error:', err))
}

function waitForFlask(retries = 40, delay = 400) {
  return new Promise((resolve, reject) => {
    let n = 0
    const try_ = () => {
      const req = http.get(`http://localhost:${PORT}/`, (res) => resolve())
      req.on('error', () => {
        if (++n >= retries) return reject(new Error('Backend timeout'))
        setTimeout(try_, delay)
      })
      req.setTimeout(300, () => req.destroy())
    }
    try_()
  })
}

function createWindow() {
  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, 'icon.ico')
    : path.join(__dirname, '..', 'icon.ico')

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 760,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0b0b1a',
    show: false,
    title: 'Music DL',
    icon: iconPath,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      devTools: !app.isPackaged,
    },
  })

  // Supprime la barre de menu (File, Edit, View...)
  Menu.setApplicationMenu(null)

  mainWindow.loadURL(`http://localhost:${PORT}`)

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
    mainWindow.focus()
  })

  // Desactive le clic droit en production (plus de menu "localhost")
  if (app.isPackaged) {
    mainWindow.webContents.on('context-menu', (e) => e.preventDefault())
  }

  // Liens externes -> navigateur système
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(`http://localhost`)) shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => { mainWindow = null })
}

app.whenReady().then(async () => {
  startFlask()
  try {
    await waitForFlask()
    createWindow()
  } catch (err) {
    dialog.showErrorBox('Music DL', 'Le backend n\'a pas démarré.\nRelancez l\'application.')
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
