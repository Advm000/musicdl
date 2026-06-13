/* Mini-lecteur vertical — reçoit l'état du lecteur principal, renvoie les commandes */
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
  $('#dot').classList.toggle('paused', !s.playing);
  $('#now-lbl').textContent = s.title ? (s.playing ? 'En lecture' : 'En pause') : 'En attente';

  const art = $('#art'), ph = $('#art-ph');
  if (s.cover) {
    if (art.dataset.cover !== s.cover) {
      art.dataset.cover = s.cover;
      art.querySelector('img')?.remove();
      const img = document.createElement('img');
      img.src = s.cover;
      art.insertBefore(img, ph);
      ph.style.display = 'none';
    }
  } else if (art.dataset.cover) {
    delete art.dataset.cover;
    art.querySelector('img')?.remove();
    ph.style.display = '';
  }
});
