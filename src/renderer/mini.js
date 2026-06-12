/* Mini-lecteur — reçoit l'état du lecteur principal, renvoie les commandes */
'use strict';
const $ = (s) => document.querySelector(s);

$('#play').addEventListener('click', () => window.mdl.miniCmd({ action: 'toggle' }));
$('#prev').addEventListener('click', () => window.mdl.miniCmd({ action: 'prev' }));
$('#next').addEventListener('click', () => window.mdl.miniCmd({ action: 'next' }));
$('#expand').addEventListener('click', () => window.mdl.miniCmd({ action: 'expand' }));
$('#close').addEventListener('click', () => window.mdl.miniCmd({ action: 'expand' }));
$('#bar').addEventListener('mousedown', (e) => {
  const r = e.currentTarget.getBoundingClientRect();
  window.mdl.miniCmd({ action: 'seek', ratio: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) });
});

window.mdl.on('mini:state', (s) => {
  $('#title').textContent = s.title || 'Aucune lecture';
  $('#artist').textContent = s.artist || '—';
  $('#cur').textContent = s.cur || '0:00';
  $('#tot').textContent = s.tot || '0:00';
  $('#fill').style.width = (s.pct || 0) + '%';
  $('#ico-play').style.display = s.playing ? 'none' : '';
  $('#ico-pause').style.display = s.playing ? '' : 'none';
  const art = $('#art');
  if (s.cover) {
    if (!art.dataset.cover || art.dataset.cover !== s.cover) {
      art.dataset.cover = s.cover;
      art.innerHTML = `<img src="${s.cover.replace(/"/g, '&quot;')}">`;
    }
  } else if (art.dataset.cover) {
    delete art.dataset.cover;
    art.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,.22)" stroke-width="1.5" stroke-linecap="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>';
  }
});
