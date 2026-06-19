const { contextBridge, ipcRenderer } = require('electron');

const EVENTS = [
  'dl:queue', 'dl:done', 'dl:error',
  'update:available', 'update:progress', 'update:ready', 'update:error',
  'win:maximized', 'remote:cmd', 'mini:state', 'lyrics:ready'
];

contextBridge.exposeInMainWorld('mdl', {
  // Fenêtre
  minimize: () => ipcRenderer.send('win:minimize'),
  maximize: () => ipcRenderer.send('win:maximize'),
  close: () => ipcRenderer.send('win:close'),

  // État global
  getState: () => ipcRenderer.invoke('state:get'),

  // Recherche + téléchargement
  search: (query, kind) => ipcRenderer.invoke('search:run', query, kind),
  searchMore: (token, kind) => ipcRenderer.invoke('search:more', token, kind),
  suggest: (input) => ipcRenderer.invoke('search:suggest', input),
  getCollection: (ref) => ipcRenderer.invoke('collection:get', ref),
  getArtist: (browseId) => ipcRenderer.invoke('artist:get', browseId),
  getArtistByName: (name) => ipcRenderer.invoke('artist:byName', name),
  addInterest: (a) => ipcRenderer.invoke('interest:add', a),
  discover: () => ipcRenderer.invoke('discover'),
  previewUrl: (id) => ipcRenderer.invoke('preview:get', id),
  getLyrics: (id) => ipcRenderer.invoke('lyrics:get', id),
  refetchLyrics: (id) => ipcRenderer.invoke('lyrics:refetch', id),
  download: (track) => ipcRenderer.invoke('dl:start', track),

  // Bibliothèque
  deleteTrack: (id) => ipcRenderer.invoke('library:delete', id),
  deleteMany: (ids) => ipcRenderer.invoke('library:deleteMany', ids),
  revealTrack: (id) => ipcRenderer.invoke('library:reveal', id),
  openFolder: () => ipcRenderer.invoke('folder:open'),
  setFavorite: (id, on) => ipcRenderer.invoke('fav:set', { id, on }),
  setOnlineFavorite: (track, on) => ipcRenderer.invoke('online:setFav', { track, on }),
  saveOnline: (tracks) => ipcRenderer.invoke('online:save', tracks),
  removeOnline: (id) => ipcRenderer.invoke('online:remove', id),
  bumpPlay: (id) => ipcRenderer.invoke('plays:bump', id),

  // Playlists
  createPlaylist: (name) => ipcRenderer.invoke('playlist:create', name),
  deletePlaylist: (id) => ipcRenderer.invoke('playlist:delete', id),
  renamePlaylist: (id, name) => ipcRenderer.invoke('playlist:rename', { id, name }),
  addToPlaylist: (playlistId, trackId, meta) => ipcRenderer.invoke('playlist:addTrack', { playlistId, trackId, meta }),
  removeFromPlaylist: (playlistId, trackId) => ipcRenderer.invoke('playlist:removeTrack', { playlistId, trackId }),

  // Paramètres
  chooseFolder: () => ipcRenderer.invoke('settings:chooseFolder'),
  saveSettings: (s) => ipcRenderer.invoke('settings:save', s),

  // Mises à jour
  downloadUpdate: () => ipcRenderer.invoke('update:download'),
  installUpdate: () => ipcRenderer.invoke('update:install'),

  // Mini-lecteur
  openMini: () => ipcRenderer.send('mini:open'),
  closeMini: () => ipcRenderer.send('mini:close'),
  miniCmd: (payload) => ipcRenderer.send('mini:cmd', payload),
  sendMiniState: (s) => ipcRenderer.send('mini:state', s),

  // Événements
  on: (channel, cb) => {
    if (!EVENTS.includes(channel)) return;
    ipcRenderer.on(channel, (_e, data) => cb(data));
  }
});
