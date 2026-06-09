const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronUpdater', {
  install: () => ipcRenderer.invoke('upd-install'),
  onUpdate: (cb) => ipcRenderer.on('upd', (_, data) => cb(data)),
})
