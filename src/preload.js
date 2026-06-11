const { contextBridge, ipcRenderer } = require('electron');

const EVENTS = [
  'dl:queue', 'dl:done', 'dl:error',
  'update:available', 'update:progress', 'update:ready', 'update:error',
  'win:maximized'
];

contextBridge.exposeInMainWorld('mdl', {
  // Fenêtre
  minimize: () => ipcRenderer.send('win:minimize'),
  maximize: () => ipcRenderer.send('win:maximize'),
  close: () => ipcRenderer.send('win:close'),

  // État global
  getState: () => ipcRenderer.invoke('state:get'),

  // Recherche + téléchargement
  search: (query) => ipcRenderer.invoke('search:run', query),
  download: (track) => ipcRenderer.invoke('dl:start', track),

  // Bibliothèque
  deleteTrack: (id) => ipcRenderer.invoke('library:delete', id),
  revealTrack: (id) => ipcRenderer.invoke('library:reveal', id),
  openFolder: () => ipcRenderer.invoke('folder:open'),
  setFavorite: (id, on) => ipcRenderer.invoke('fav:set', { id, on }),

  // Playlists
  createPlaylist: (name) => ipcRenderer.invoke('playlist:create', name),
  deletePlaylist: (id) => ipcRenderer.invoke('playlist:delete', id),
  renamePlaylist: (id, name) => ipcRenderer.invoke('playlist:rename', { id, name }),
  addToPlaylist: (playlistId, trackId) => ipcRenderer.invoke('playlist:addTrack', { playlistId, trackId }),
  removeFromPlaylist: (playlistId, trackId) => ipcRenderer.invoke('playlist:removeTrack', { playlistId, trackId }),

  // Paramètres
  chooseFolder: () => ipcRenderer.invoke('settings:chooseFolder'),
  saveSettings: (s) => ipcRenderer.invoke('settings:save', s),

  // Mises à jour
  downloadUpdate: () => ipcRenderer.invoke('update:download'),
  installUpdate: () => ipcRenderer.invoke('update:install'),

  // Événements
  on: (channel, cb) => {
    if (!EVENTS.includes(channel)) return;
    ipcRenderer.on(channel, (_e, data) => cb(data));
  }
});
