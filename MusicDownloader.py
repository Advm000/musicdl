"""
Music Downloader — Flask + HTML/CSS/JS
Interface web professionnelle avec glassmorphism et animations CSS 3D
"""

import os, io, json, uuid, shutil, tempfile, threading, time, webbrowser, socket, struct, zlib, platform
from datetime import datetime
from flask import Flask, Response, request, jsonify, send_file, stream_with_context
import yt_dlp, imageio_ffmpeg
from mutagen.mp3  import MP3
from mutagen.id3  import ID3
from mutagen.easyid3 import EasyID3

# ── FFmpeg ─────────────────────────────────────────────────────────────────────
def _setup_ffmpeg():
    src = imageio_ffmpeg.get_ffmpeg_exe()
    tmp = os.path.join(tempfile.gettempdir(), "ytdl_ff")
    os.makedirs(tmp, exist_ok=True)
    dst = os.path.join(tmp, "ffmpeg.exe")
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
    return tmp

FFMPEG_DIR = _setup_ffmpeg()

# Dossier dédié à l'app dans AppData\Local (caché, comme une vraie appli Windows)
_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
OUT_DIR  = os.path.join(_appdata, "MusicDL")
os.makedirs(OUT_DIR, exist_ok=True)

FAV_FILE    = os.path.join(OUT_DIR, ".favorites.json")
PL_FILE     = os.path.join(OUT_DIR, ".playlists.json")
DEVICE_FILE = os.path.join(OUT_DIR, "device.json")
APP_VERSION = "2.7.3"

app  = Flask(__name__)
jobs = {}   # job_id -> {"progress":0,"status":"...","done":False,"error":"","cancelled":False}

def _jload(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except: return default

def _jsave(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def _init_device():
    """Crée un profil unique pour ce PC au premier lancement."""
    if not os.path.exists(DEVICE_FILE):
        data = {
            "device_id":    str(uuid.uuid4()),
            "hostname":     socket.gethostname(),
            "os":           platform.system(),
            "os_version":   platform.version(),
            "os_release":   platform.release(),
            "install_date": datetime.now().isoformat(),
            "app_version":  APP_VERSION,
            "data_folder":  OUT_DIR,
        }
        _jsave(DEVICE_FILE, data)
    info = _jload(DEVICE_FILE, {})
    if info.get("app_version") != APP_VERSION:
        info["app_version"] = APP_VERSION
        _jsave(DEVICE_FILE, info)
    return info

DEVICE_INFO = _init_device()

# ══════════════════════════════════════════════════════════════════════════════
# API ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/device")
def api_device():
    return jsonify(DEVICE_INFO)

@app.route("/api/version")
def api_version():
    return jsonify({"version": APP_VERSION})

@app.route("/api/ping")
def api_ping():
    """Vérifie la connectivité internet réelle (pas juste le réseau local)."""
    import urllib.request
    try:
        urllib.request.urlopen("https://www.google.com", timeout=4)
        return jsonify({"online": True})
    except Exception:
        return jsonify({"online": False})

@app.route("/api/quit", methods=["POST"])
def api_quit():
    """Arrête proprement le serveur (utilisé par l'app packagée)."""
    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()
    else:
        threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify({"ok": True})

@app.route("/api/suggest")
def api_suggest():
    import urllib.request, urllib.parse
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    try:
        url = ("https://suggestqueries.google.com/complete/search"
               "?client=firefox&ds=yt&q=" + urllib.parse.quote(q))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        suggestions = data[1] if len(data) > 1 else []
        return jsonify(suggestions[:8])
    except:
        return jsonify([])


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    n = min(int(request.args.get("n", 20)), 100)
    if not q:
        return jsonify([])
    try:
        with yt_dlp.YoutubeDL({"quiet":True,"no_warnings":True,"extract_flat":True}) as ydl:
            info = ydl.extract_info(f"ytsearch{n}:{q}", download=False)
        entries = (info or {}).get("entries", [])
        results = []
        for e in entries:
            thumb = e.get("thumbnail","")
            if not thumb:
                for t in e.get("thumbnails",[]):
                    if t.get("url"): thumb = t["url"]; break
            results.append({
                "id":       e.get("id",""),
                "title":    e.get("title",""),
                "channel":  e.get("uploader") or e.get("channel",""),
                "duration": _fmt_dur(e.get("duration")),
                "views":    _fmt_views(e.get("view_count")),
                "thumb":    thumb,
                "url":      e.get("url",""),
            })
        return jsonify(results)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


@app.route("/api/download", methods=["POST"])
def api_download():
    data   = request.json
    vid_id = data.get("id","")
    url    = data.get("url") or f"https://www.youtube.com/watch?v={vid_id}"
    title  = data.get("title","track")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"progress":0, "status":"Démarrage…", "done":False, "error":"", "cancelled":False}
    threading.Thread(target=_download, args=(job_id, url), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/cancel/<job_id>", methods=["POST"])
def api_cancel(job_id):
    j = jobs.get(job_id)
    if j and not j.get("done"):
        j["cancelled"] = True
        j["status"]    = "Annulé"
    return jsonify({"ok": True})


@app.route("/api/progress/<job_id>")
def api_progress(job_id):
    def stream():
        while True:
            j = jobs.get(job_id, {})
            yield f"data: {json.dumps(j)}\n\n"
            if j.get("done") or j.get("error"):
                break
            time.sleep(0.4)
    return Response(stream_with_context(stream()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


@app.route("/api/library")
def api_library():
    try:
        files = sorted(
            [f for f in os.listdir(OUT_DIR) if f.lower().endswith(".mp3")],
            key=lambda f: os.path.getmtime(os.path.join(OUT_DIR, f)),
            reverse=True
        )
    except Exception: files = []
    items = []
    for f in files:
        path   = os.path.join(OUT_DIR, f)
        title, artist, album, dur = _read_tags(path)
        size   = round(os.path.getsize(path)/1_048_576, 1)
        mtime  = os.path.getmtime(path)
        items.append({"filename":f,"title":title,"artist":artist,"album":album,
                       "duration":dur,"size":f"{size} MB","mtime":mtime})
    return jsonify(items)


@app.route("/api/cover/<path:filename>")
def api_cover(filename):
    path = os.path.join(OUT_DIR, filename)
    try:
        for tag in ID3(path).values():
            if tag.FrameID == "APIC":
                return send_file(io.BytesIO(tag.data), mimetype="image/jpeg")
    except Exception: pass
    return "", 404


@app.route("/api/delete/<path:filename>", methods=["DELETE"])
def api_delete(filename):
    path = os.path.join(OUT_DIR, filename)
    try:
        os.remove(path)
        favs = _jload(FAV_FILE, [])
        if filename in favs:
            favs.remove(filename)
            _jsave(FAV_FILE, favs)
        pls = _jload(PL_FILE, {})
        changed = False
        for pl_name in pls:
            if filename in pls[pl_name]:
                pls[pl_name].remove(filename)
                changed = True
        if changed:
            _jsave(PL_FILE, pls)
        return jsonify({"ok": True})
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


@app.route("/api/outdir")
def api_outdir():
    return jsonify({"dir": OUT_DIR, "display": "AppData\\Local\\MusicDL"})


@app.route("/api/stream/<path:filename>")
def api_stream(filename):
    path = os.path.join(OUT_DIR, filename)
    if not os.path.exists(path): return "", 404
    return send_file(path, mimetype="audio/mpeg", conditional=True)


@app.route("/api/favorites")
def api_favs():
    return jsonify(_jload(FAV_FILE, []))

@app.route("/api/favorites/toggle/<path:filename>", methods=["POST"])
def api_favs_toggle(filename):
    favs = _jload(FAV_FILE, [])
    if filename in favs: favs.remove(filename); added = False
    else: favs.append(filename); added = True
    _jsave(FAV_FILE, favs)
    return jsonify({"ok": True, "added": added})


@app.route("/api/playlists")
def api_pls():
    return jsonify(_jload(PL_FILE, {}))

@app.route("/api/playlists/create", methods=["POST"])
def api_pl_create():
    name = (request.json or {}).get("name","").strip()
    if not name: return jsonify({"error":"name required"}), 400
    pls = _jload(PL_FILE, {})
    if name not in pls: pls[name] = []
    _jsave(PL_FILE, pls)
    return jsonify({"ok": True})

@app.route("/api/playlists/<path:name>/add", methods=["POST"])
def api_pl_add(name):
    fn  = (request.json or {}).get("filename","")
    pls = _jload(PL_FILE, {})
    if name not in pls: pls[name] = []
    if fn and fn not in pls[name]: pls[name].append(fn)
    _jsave(PL_FILE, pls)
    return jsonify({"ok": True})

@app.route("/api/playlists/<path:name>/remove", methods=["POST"])
def api_pl_remove(name):
    fn  = (request.json or {}).get("filename","")
    pls = _jload(PL_FILE, {})
    if name in pls and fn in pls[name]: pls[name].remove(fn)
    _jsave(PL_FILE, pls)
    return jsonify({"ok": True})

@app.route("/api/playlists/<path:name>", methods=["DELETE"])
def api_pl_delete(name):
    pls = _jload(PL_FILE, {})
    pls.pop(name, None)
    _jsave(PL_FILE, pls)
    return jsonify({"ok": True})

@app.route("/api/playlists/<path:name>/rename", methods=["POST"])
def api_pl_rename(name):
    new_name = (request.json or {}).get("new_name", "").strip()
    if not new_name: return jsonify({"error": "name required"}), 400
    pls = _jload(PL_FILE, {})
    if name not in pls: return jsonify({"error": "not found"}), 404
    if new_name in pls and new_name != name: return jsonify({"error": "exists"}), 409
    pls[new_name] = pls.pop(name)
    _jsave(PL_FILE, pls)
    return jsonify({"ok": True})

@app.route("/api/playlists/<path:name>/reorder", methods=["POST"])
def api_pl_reorder(name):
    order = (request.json or {}).get("order", [])
    pls = _jload(PL_FILE, {})
    if name in pls:
        existing = set(pls[name])
        reordered = [fn for fn in order if fn in existing]
        for fn in pls[name]:
            if fn not in reordered: reordered.append(fn)
        pls[name] = reordered
    _jsave(PL_FILE, pls)
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════════════════════
# LOGIQUE TÉLÉCHARGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def _download(job_id, url):
    def hook(d):
        j = jobs[job_id]
        if j.get("cancelled"):
            raise Exception("__cancelled__")
        if d["status"] == "downloading":
            raw = (d.get("_percent_str","0")
                   .replace("%","").replace("\x1b[0;94m","").replace("\x1b[0m","").strip())
            try:    pct = float(raw)
            except: pct = 0.0
            spd = d.get("_speed_str","").strip()
            eta = d.get("_eta_str","").strip()
            j["progress"] = pct
            j["status"]   = f"{spd} — ETA {eta}" if spd else "Téléchargement…"
        elif d["status"] == "finished":
            j["progress"] = 99
            j["status"]   = "Conversion MP3…"
    try:
        opts = {
            "format":          "bestaudio/best",
            "outtmpl":         os.path.join(OUT_DIR, "%(title)s.%(ext)s"),
            "ffmpeg_location": FFMPEG_DIR,
            "postprocessors":  [
                {"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"320"},
                {"key":"FFmpegMetadata","add_metadata":True},
                {"key":"EmbedThumbnail"},
            ],
            "writethumbnail":True,"embedthumbnail":True,
            "progress_hooks":[hook],"quiet":True,"no_warnings":True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        jobs[job_id].update({"progress":100,"status":"Terminé ✓","done":True})
    except Exception as ex:
        if jobs[job_id].get("cancelled") or "__cancelled__" in str(ex):
            jobs[job_id].update({"cancelled":True,"status":"Annulé","done":True,"error":""})
        else:
            jobs[job_id].update({"error":str(ex),"done":True})


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_dur(s):
    if not s: return "—"
    m, s = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _fmt_views(n):
    if not n: return ""
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M vues"
    if n >= 1_000:     return f"{n/1_000:.0f}K vues"
    return f"{n} vues"

def _read_tags(path):
    title  = os.path.splitext(os.path.basename(path))[0]
    artist = album = dur = ""
    try:
        dur    = _fmt_dur(MP3(path).info.length)
        tags   = EasyID3(path)
        title  = tags.get("title",  [title])[0]
        artist = tags.get("artist", [""])[0]
        album  = tags.get("album",  [""])[0]
    except Exception: pass
    return title, artist, album, dur


# ══════════════════════════════════════════════════════════════════════════════
# INTERFACE HTML  —  Design Premium Violet/Cyan
# ══════════════════════════════════════════════════════════════════════════════

HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1">
<meta name="theme-color" content="#06061a">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Music DL">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<title>Music DL</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap">
<style>
:root{
  --bg:#07071a;--bg2:#0c0c22;--bg3:#10103a;
  --purple:#7c3aed;--cyan:#06b6d4;--pink:#f43f5e;--green:#10b981;
  --text:#f1f5f9;--text2:#94a3b8;--text3:#475569;--text4:#334155;
  --border:rgba(124,58,237,.12);--border2:rgba(124,58,237,.28);
  --grad:linear-gradient(135deg,#7c3aed,#06b6d4);
  --glass:rgba(8,8,26,.82);
  --radius:14px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--text);font:14px/1.5 'Inter',system-ui,sans-serif;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
::selection{background:rgba(124,58,237,.35);color:#fff}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(124,58,237,.45);border-radius:5px}
::-webkit-scrollbar-thumb:hover{background:rgba(124,58,237,.75)}
#app{position:fixed;inset:0;display:flex;flex-direction:column}

/* ══ HEADER ══ */
.hd{flex-shrink:0;height:64px;padding:0 24px;display:flex;align-items:center;justify-content:space-between;background:var(--glass);backdrop-filter:blur(28px);-webkit-backdrop-filter:blur(28px);border-bottom:1px solid var(--border);box-shadow:0 1px 0 rgba(255,255,255,.03),0 8px 32px rgba(0,0,0,.4);position:relative;z-index:10}
.hd::after{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(124,58,237,.5),rgba(6,182,212,.35),transparent)}
.hd-logo{display:flex;align-items:center;gap:13px}
.hd-ico{width:40px;height:40px;border-radius:12px;font-size:18px;background:var(--grad);display:flex;align-items:center;justify-content:center;box-shadow:0 0 0 0 rgba(124,58,237,.5);animation:iconPulse 3.5s ease-in-out infinite;flex-shrink:0}
@keyframes iconPulse{0%,100%{box-shadow:0 0 0 0 rgba(124,58,237,.5),0 4px 16px rgba(124,58,237,.4)}50%{box-shadow:0 0 0 8px rgba(124,58,237,0),0 4px 20px rgba(124,58,237,.6)}}
.hd-name{font-size:18px;font-weight:900;letter-spacing:-.6px;background:linear-gradient(90deg,#c4b5fd 30%,#67e8f9);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hd-sub{font-size:9px;color:var(--text4);margin-top:1px;letter-spacing:.3px;text-transform:uppercase}
#hd-ver{text-transform:none}
.hd-badge{display:flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;font-size:10px;font-weight:700;letter-spacing:.4px;background:rgba(124,58,237,.1);border:1px solid rgba(124,58,237,.3);color:#a78bfa;backdrop-filter:blur(10px)}
.hd-badge::before{content:'';width:6px;height:6px;border-radius:50%;background:#06b6d4;box-shadow:0 0 8px #06b6d4,0 0 14px rgba(6,182,212,.6);flex-shrink:0;animation:dot-pulse 2s ease-in-out infinite}
@keyframes dot-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.6;transform:scale(.8)}}

/* ══ TABS ══ */
.tabs{flex-shrink:0;display:flex;background:rgba(8,8,24,.9);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:0 12px;position:relative;gap:2px}
.tb{padding:0 18px;height:46px;font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--text4);cursor:pointer;border-bottom:2px solid transparent;display:flex;align-items:center;gap:7px;transition:color .3s cubic-bezier(.4,0,.2,1),border-color .3s;user-select:none;position:relative;border-radius:8px 8px 0 0}
.tb:hover{color:var(--text3);background:rgba(124,58,237,.04)}
.tb.on{color:#c4b5fd;border-bottom-color:var(--purple)}
.tb.on::before{content:'';position:absolute;bottom:-1px;left:20%;right:20%;height:2px;background:var(--grad);filter:blur(3px);border-radius:2px;opacity:.7}
.tbdot{width:5px;height:5px;border-radius:50%;background:var(--text4);flex-shrink:0;transition:all .3s cubic-bezier(.4,0,.2,1)}
.tb.on .tbdot{background:var(--purple);box-shadow:0 0 8px var(--purple),0 0 16px rgba(124,58,237,.4);transform:scale(1.2)}

/* PAGES */
.pages{flex:1;overflow:hidden;min-height:0;position:relative}
.page{position:absolute;inset:0;overflow:hidden;display:flex;flex-direction:column;opacity:0;pointer-events:none;transform:translateX(22px) scale(.985);transition:opacity .34s cubic-bezier(.25,.46,.45,.94),transform .34s cubic-bezier(.25,.46,.45,.94)}
.page.on{opacity:1;pointer-events:auto;transform:translateX(0) scale(1)}

/* ══ SEARCH BAR ══ */
.sb{flex-shrink:0;padding:14px 18px 12px;background:rgba(9,9,26,.75);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid var(--border)}
.sb-row{display:flex;gap:8px;align-items:center}
.si-wrap{flex:1;border-radius:12px;padding:2px;background:var(--grad);transition:box-shadow .25s;position:relative}
.si-wrap:focus-within{box-shadow:0 0 0 4px rgba(124,58,237,.18),0 0 20px rgba(124,58,237,.12)}
.si-inner{display:flex;align-items:center;gap:10px;background:rgba(8,8,28,.95);border-radius:10px;padding:0 14px;height:46px}
.si-inner svg{flex-shrink:0;color:var(--purple);transition:color .2s}
.si-wrap:focus-within .si-inner svg{color:#a78bfa}
.si-inner input{flex:1;border:none;outline:none;background:transparent;color:var(--text);font-size:15px;font-family:inherit;font-weight:500}
.si-inner input::placeholder{color:var(--text4)}
#sug-box{display:none;position:absolute;top:calc(100% + 6px);left:0;right:0;z-index:9999;background:rgba(11,11,32,.97);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border:1px solid rgba(124,58,237,.3);border-radius:14px;overflow:hidden;box-shadow:0 16px 48px rgba(0,0,0,.8),0 0 0 1px rgba(255,255,255,.03);animation:sugDrop .18s cubic-bezier(.4,0,.2,1)}
@keyframes sugDrop{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
.sug-item{padding:11px 14px;font-size:13px;font-weight:500;color:#c4b5fd;cursor:pointer;transition:background .15s,color .15s,padding-left .15s;display:flex;align-items:center;gap:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sug-item:hover{background:rgba(124,58,237,.15);color:#e9d5ff;padding-left:18px}
.sug-item::before{content:'';display:inline-block;width:13px;height:13px;flex-shrink:0;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%237c3aed' stroke-width='2.5'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.35-4.35'/%3E%3C/svg%3E") center/contain no-repeat;opacity:.6}
.btn-go{height:46px;padding:0 22px;border-radius:10px;border:none;cursor:pointer;font-size:13px;font-weight:700;font-family:inherit;background:var(--grad);color:#fff;box-shadow:0 4px 20px rgba(124,58,237,.4);display:flex;align-items:center;gap:7px;transition:box-shadow .2s,transform .2s cubic-bezier(.4,0,.2,1),opacity .2s;letter-spacing:.2px}
.btn-go:hover{box-shadow:0 6px 30px rgba(124,58,237,.65);transform:translateY(-2px) scale(1.02)}
.btn-go:active{transform:scale(.96)}
.btn-go:disabled{opacity:.4;transform:none;box-shadow:none;cursor:not-allowed}
.btn-all{height:46px;padding:0 16px;border-radius:10px;border:none;cursor:pointer;font-size:12px;font-weight:700;font-family:inherit;background:linear-gradient(135deg,#059669,#06b6d4);color:#fff;box-shadow:0 4px 16px rgba(5,150,105,.35);display:none;align-items:center;gap:6px;transition:box-shadow .2s,transform .2s}
.btn-all:hover{box-shadow:0 6px 26px rgba(5,150,105,.55);transform:translateY(-1px)}
.dbar{flex-shrink:0;display:flex;align-items:center;gap:8px;padding:5px 18px;background:rgba(5,5,15,.6);border-bottom:1px solid rgba(255,255,255,.025);font-size:10px;color:var(--text4)}

/* ══ RESULTS LIST ══ */
.rl{flex:1;min-height:0;overflow-y:auto;padding:12px 16px 16px;display:flex;flex-direction:column;gap:8px}
.mt{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}
.mt-ico{width:80px;height:80px;border-radius:22px;background:rgba(124,58,237,.06);border:1px solid rgba(124,58,237,.15);display:flex;align-items:center;justify-content:center;font-size:30px;opacity:.45}
.mt p{font-size:13px;color:var(--text4);text-align:center;line-height:1.7;max-width:240px}

/* ══ RESULT CARD ══ */
.rc{flex-shrink:0;display:flex;align-items:center;gap:13px;min-height:86px;background:rgba(13,13,42,.6);border:1px solid rgba(124,58,237,.14);border-radius:14px;padding:12px 14px;position:relative;overflow:hidden;transition:border-color .25s,box-shadow .25s,transform .2s cubic-bezier(.4,0,.2,1),background .25s;animation:up .22s ease both}
.rc::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--grad);border-radius:3px 0 0 3px;opacity:.7;transition:opacity .25s,width .25s}
.rc:hover{border-color:rgba(124,58,237,.32);box-shadow:0 4px 28px rgba(124,58,237,.12),0 1px 0 rgba(255,255,255,.03);transform:translateX(3px);background:rgba(13,13,48,.8)}
.rc:hover::before{opacity:1;width:4px}
.rt{flex-shrink:0;width:108px;height:68px;border-radius:10px;overflow:hidden;background:var(--bg3);position:relative;border:1px solid rgba(124,58,237,.18);transition:box-shadow .25s}
.rc:hover .rt{box-shadow:0 4px 18px rgba(124,58,237,.3)}
.rt img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .35s cubic-bezier(.4,0,.2,1)}
.rc:hover .rt img{transform:scale(1.08)}
.rt-ph{width:108px;height:68px;flex-shrink:0;border-radius:10px;background:linear-gradient(135deg,#1e1e50,#0d0d28);display:flex;align-items:center;justify-content:center;font-size:26px;opacity:.4;border:1px solid rgba(124,58,237,.15)}
.rt-dur{position:absolute;bottom:4px;right:4px;background:rgba(0,0,0,.88);color:var(--text);font-size:9px;font-weight:700;padding:2px 5px;border-radius:4px;letter-spacing:.3px}
.ri{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px}
.ri-title{font-size:13px;font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.35;transition:color .2s}
.rc:hover .ri-title{color:#e2d9ff}
.ri-row{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.ri-ch{font-size:11px;color:var(--purple);font-weight:600;letter-spacing:.1px}
.ri-dot{color:var(--text4);font-size:10px}
.ri-dur{font-size:11px;color:var(--text3)}
.ri-views{display:inline-flex;align-items:center;gap:3px;background:rgba(6,182,212,.08);border:1px solid rgba(6,182,212,.18);color:#22d3ee;padding:1px 7px;border-radius:6px;font-size:10px;font-weight:600;letter-spacing:.2px}
.rp{display:none;margin-top:3px}
.rp-track{height:3px;background:rgba(124,58,237,.1);border-radius:3px;overflow:hidden}
.rp-fill{height:100%;width:0;background:var(--grad);border-radius:3px;transition:width .3s;position:relative;overflow:hidden}
.rp-fill::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.38),transparent);animation:sh 1.4s linear infinite}
@keyframes sh{from{transform:translateX(-100%)}to{transform:translateX(200%)}}
.rp-fill.done{background:linear-gradient(90deg,#059669,#06b6d4)}
.rp-fill.done::after{display:none}
.rp-lbl{font-size:10px;color:var(--text3);margin-top:2px;letter-spacing:.2px}
.ra{flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;gap:6px;padding-right:2px}
.dl-btn{display:inline-flex;align-items:center;gap:6px;padding:10px 18px;border-radius:10px;border:none;cursor:pointer;font-size:12px;font-weight:700;font-family:inherit;background:var(--grad);color:#fff;box-shadow:0 3px 16px rgba(124,58,237,.38);transition:box-shadow .2s,transform .2s cubic-bezier(.4,0,.2,1);white-space:nowrap;letter-spacing:.2px}
.dl-btn:hover{box-shadow:0 5px 26px rgba(124,58,237,.62);transform:translateY(-2px) scale(1.03)}
.dl-btn:active{transform:scale(.95)}
.dl-btn:disabled{opacity:.38;transform:none;box-shadow:none;cursor:not-allowed}
.cancel-btn{display:none;align-items:center;gap:5px;padding:6px 12px;border-radius:8px;border:1px solid rgba(244,63,94,.3);cursor:pointer;font-size:11px;font-weight:700;font-family:inherit;background:rgba(244,63,94,.1);color:#fb7185;transition:background .2s,transform .2s}
.cancel-btn:hover{background:rgba(244,63,94,.25);transform:scale(1.04)}
.ok-badge{display:inline-flex;align-items:center;gap:5px;padding:9px 13px;border-radius:9px;font-size:11px;font-weight:700;background:rgba(5,150,105,.1);color:#34d399;border:1px solid rgba(5,150,105,.28);letter-spacing:.2px}

/* ══ LIBRARY ══ */
.lhd{flex-shrink:0;display:flex;align-items:center;justify-content:space-between;padding:12px 18px;background:rgba(9,9,26,.8);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border-bottom:1px solid var(--border);gap:10px;flex-wrap:wrap}
.lib-search-wrap{flex:1;min-width:180px;max-width:320px;position:relative}
.lib-search{width:100%;height:34px;border-radius:20px;border:1px solid rgba(124,58,237,.22);background:rgba(124,58,237,.06);color:var(--text);font-size:12px;font-family:inherit;padding:0 12px 0 32px;outline:none;transition:border-color .2s,background .2s}
.lib-search:focus{border-color:rgba(124,58,237,.5);background:rgba(124,58,237,.1)}
.lib-search::placeholder{color:var(--text4)}
.lib-search-ico{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text4);pointer-events:none}
.lhd-t{font-size:16px;font-weight:900;display:flex;align-items:center;gap:8px;background:linear-gradient(90deg,#c4b5fd,#67e8f9);-webkit-background-clip:text;-webkit-text-fill-color:transparent;flex-shrink:0;letter-spacing:-.3px}
.lhd-cnt{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:800;background:var(--grad);color:#fff;-webkit-text-fill-color:#fff;box-shadow:0 2px 12px rgba(124,58,237,.4);letter-spacing:.2px}
.lhd-btns{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.lbtn{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:20px;border:none;cursor:pointer;font-size:11px;font-weight:700;font-family:inherit;background:rgba(124,58,237,.1);color:#a78bfa;border:1px solid rgba(124,58,237,.25);transition:all .2s cubic-bezier(.4,0,.2,1);letter-spacing:.2px}
.lbtn:hover{background:rgba(124,58,237,.2);border-color:rgba(124,58,237,.45);transform:translateY(-1px)}
.lbtn.on{background:rgba(124,58,237,.25);border-color:var(--purple);color:#c4b5fd;box-shadow:0 2px 10px rgba(124,58,237,.25)}
.del-sel-btn{display:none;align-items:center;gap:5px;padding:6px 13px;border-radius:20px;border:none;cursor:pointer;font-size:11px;font-weight:700;font-family:inherit;background:linear-gradient(135deg,#dc2626,#f43f5e);color:#fff;box-shadow:0 3px 12px rgba(220,38,38,.35);transition:all .2s}
.del-sel-btn:hover{box-shadow:0 5px 22px rgba(220,38,38,.6);transform:translateY(-1px)}
.fav-btn{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:20px;border:none;cursor:pointer;font-size:11px;font-weight:700;font-family:inherit;background:rgba(244,63,94,.08);color:#fb7185;border:1px solid rgba(244,63,94,.22);transition:all .2s}
.fav-btn:hover{background:rgba(244,63,94,.16);transform:translateY(-1px)}
.fav-btn.on{background:rgba(244,63,94,.2);border-color:var(--pink);color:#fda4af;box-shadow:0 2px 10px rgba(244,63,94,.25)}

/* ══ LIBRARY TABLE — SPOTIFY STYLE ══ */
.lgrid{flex:1;min-height:0;overflow-y:auto;display:flex;flex-direction:column}
/* Table header */
.ltbl-hd{
  display:grid;
  grid-template-columns:48px 1fr 180px 120px 64px 110px;
  align-items:center;padding:0 16px;height:36px;
  border-bottom:1px solid rgba(255,255,255,.06);
  font-size:11px;font-weight:700;letter-spacing:.09em;
  color:#475569;text-transform:uppercase;flex-shrink:0;
  position:sticky;top:0;background:rgba(9,9,26,.96);
  backdrop-filter:blur(14px);z-index:5;
}
.ltbl-hd>span{padding:0 8px}
/* Track row */
.lcard{
  display:grid;
  grid-template-columns:48px 1fr 180px 120px 64px 110px;
  align-items:center;padding:0 16px;height:58px;
  border-radius:6px;cursor:pointer;flex-shrink:0;
  transition:background .15s ease;
  animation:up .22s ease both;position:relative;
}
.lcard:hover{background:rgba(255,255,255,.055)}
.lcard.selected{background:rgba(124,58,237,.12)}
.lcard.now-playing{background:rgba(124,58,237,.1)}
.lcard.now-playing .lrow-t{color:#c4b5fd}
/* Col 1: number / play icon */
.lrow-num{display:flex;align-items:center;justify-content:center;position:relative;padding:0 8px}
.lrow-idx{font-size:13px;color:#475569;font-variant-numeric:tabular-nums;transition:opacity .15s}
.lcard:hover .lrow-idx,.lcard.now-playing .lrow-idx{opacity:0}
.lrow-play-ico{position:absolute;opacity:0;transition:opacity .15s;color:#f1f5f9;display:flex;align-items:center;justify-content:center}
.lcard:hover .lrow-play-ico{opacity:1}
.lcard.now-playing .lrow-play-ico{opacity:1;color:#c4b5fd}
/* Checkbox in select mode */
.lcard-check{display:none;width:20px;height:20px;border-radius:5px;border:2px solid rgba(124,58,237,.5);background:var(--bg3);align-items:center;justify-content:center;font-size:11px;color:#fff;transition:all .18s;flex-shrink:0}
.select-mode .lcard-check{display:flex}
.select-mode .lrow-play-ico{display:none}
.lcard.selected .lcard-check{background:var(--purple);border-color:var(--purple)}
/* Col 2: cover + title + artist */
.lrow-main{display:flex;align-items:center;gap:13px;min-width:0;padding:0 8px}
.la{width:42px;height:42px;flex-shrink:0;border-radius:7px;background:var(--bg3);overflow:hidden}
.la img{width:100%;height:100%;object-fit:cover;display:block}
.la-ph{width:100%;height:100%;background:linear-gradient(135deg,#1e1e50,#0d0d28);display:flex;align-items:center;justify-content:center;color:var(--text4)}
.lrow-title-wrap{min-width:0}
.lrow-t{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#f1f5f9;transition:color .15s;line-height:1.3}
.lcard:hover .lrow-t{color:#ddd6fe}
.lrow-ar{font-size:12px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px;transition:color .15s}
.lcard:hover .lrow-ar{color:#94a3b8}
/* Col 3: album */
.lrow-album{padding:0 8px;font-size:13px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* Col 4: date */
.lrow-date{padding:0 8px;font-size:12px;color:#475569;white-space:nowrap}
/* Col 5: duration */
.lrow-dur{padding:0 8px;font-size:13px;color:#475569;text-align:right;font-variant-numeric:tabular-nums}
/* Col 6: actions (hidden until hover) */
.lrow-act{padding:0 8px;display:flex;align-items:center;justify-content:flex-end;gap:4px;opacity:0;transition:opacity .15s}
.lcard:hover .lrow-act,.lcard.selected .lrow-act{opacity:1}
.lcb{height:30px;border-radius:8px;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-family:inherit;transition:transform .16s cubic-bezier(.4,0,.2,1),background .16s,box-shadow .16s,color .16s;flex-shrink:0}
.lcb:active{transform:scale(.8)!important}
.lcb-pl{width:30px;font-size:15px;font-weight:700;background:rgba(6,182,212,.06);color:#22d3ee;border:1px solid rgba(6,182,212,.15)}
.lcb-pl:hover{background:rgba(6,182,212,.2);transform:scale(1.1)}
.lcb-fav{width:30px;font-size:14px;background:none;color:var(--text4);border:1px solid rgba(255,255,255,.06)}
.lcb-fav:hover{color:var(--pink);background:rgba(244,63,94,.1);border-color:rgba(244,63,94,.2);transform:scale(1.1)}
.lcb-fav.on{color:var(--pink)!important;background:rgba(244,63,94,.1)!important;border-color:rgba(244,63,94,.22)!important}
.lcb-del{width:30px;background:none;color:rgba(100,100,120,.35);border:1px solid rgba(255,255,255,.04)}
.lcb-del:hover{background:rgba(239,68,68,.12);color:#f87171;border-color:rgba(239,68,68,.2);transform:scale(1.1)}
/* Responsive: hide album+date on small screens */
@media(max-width:1100px){
  .ltbl-hd,.lcard{grid-template-columns:48px 1fr 70px 90px}
  .lrow-album,.lrow-date,.lhd-album,.lhd-date{display:none}
}
@media(max-width:700px){
  .ltbl-hd,.lcard{grid-template-columns:40px 1fr 60px 72px}
  .la{width:36px;height:36px}
}
/* CUSTOM CONFIRM DIALOG */
.dlg-overlay{position:fixed;inset:0;z-index:2000;background:rgba(0,0,0,.65);backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .22s cubic-bezier(.4,0,.2,1)}
.dlg-overlay.show{opacity:1;pointer-events:all}
.dlg-box{background:rgba(15,15,35,.97);border:1px solid rgba(124,58,237,.3);border-radius:18px;padding:28px 28px 22px;width:min(360px,90vw);box-shadow:0 24px 72px rgba(0,0,0,.8),0 0 0 1px rgba(255,255,255,.04);transform:scale(.9) translateY(8px);transition:transform .28s cubic-bezier(.34,1.56,.64,1),opacity .22s;opacity:0}
.dlg-overlay.show .dlg-box{transform:scale(1) translateY(0);opacity:1}
.dlg-icon{width:48px;height:48px;border-radius:14px;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.2);display:flex;align-items:center;justify-content:center;margin:0 auto 16px;color:#f87171}
.dlg-title{font-size:16px;font-weight:700;color:#f1f5f9;text-align:center;margin-bottom:8px}
.dlg-msg{font-size:13px;color:#94a3b8;text-align:center;line-height:1.6;margin-bottom:24px}
.dlg-btns{display:flex;gap:10px}
.dlg-cancel{flex:1;padding:11px;border-radius:10px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#94a3b8;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;transition:all .16s}
.dlg-cancel:hover{background:rgba(255,255,255,.08);color:#f1f5f9}
.dlg-confirm{flex:1;padding:11px;border-radius:10px;border:none;background:linear-gradient(135deg,#dc2626,#f43f5e);color:#fff;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;transition:all .16s;box-shadow:0 4px 18px rgba(220,38,38,.35)}
.dlg-confirm:hover{box-shadow:0 6px 28px rgba(220,38,38,.6);transform:translateY(-1px)}
.dlg-confirm:active{transform:scale(.95)}
/* CUSTOM INPUT MODAL */
.inp-overlay{position:fixed;inset:0;z-index:2100;background:rgba(0,0,0,.65);backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .22s cubic-bezier(.4,0,.2,1)}
.inp-overlay.show{opacity:1;pointer-events:all}
.inp-box{background:rgba(15,15,35,.97);border:1px solid rgba(124,58,237,.3);border-radius:18px;padding:28px 28px 22px;width:min(360px,90vw);box-shadow:0 24px 72px rgba(0,0,0,.8),0 0 0 1px rgba(255,255,255,.04);transform:scale(.9) translateY(8px);transition:transform .28s cubic-bezier(.34,1.56,.64,1),opacity .22s;opacity:0}
.inp-overlay.show .inp-box{transform:scale(1) translateY(0);opacity:1}
.inp-title{font-size:15px;font-weight:700;color:#f1f5f9;margin-bottom:16px}
.inp-field{width:100%;height:42px;border-radius:10px;border:1px solid rgba(124,58,237,.3);background:rgba(124,58,237,.06);color:#f1f5f9;font-size:14px;font-family:inherit;padding:0 14px;outline:none;transition:border-color .2s,background .2s;margin-bottom:20px}
.inp-field:focus{border-color:rgba(124,58,237,.6);background:rgba(124,58,237,.1)}
.inp-btns{display:flex;gap:10px}
.inp-cancel{flex:1;padding:11px;border-radius:10px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#94a3b8;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;transition:all .16s}
.inp-cancel:hover{background:rgba(255,255,255,.08);color:#f1f5f9}
.inp-ok{flex:1;padding:11px;border-radius:10px;border:none;background:linear-gradient(135deg,#7c3aed,#06b6d4);color:#fff;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;transition:all .16s;box-shadow:0 4px 18px rgba(124,58,237,.35)}
.inp-ok:hover{box-shadow:0 6px 28px rgba(124,58,237,.6);transform:translateY(-1px)}
/* COMING SOON PAGE */
.cs-wrap{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 24px;text-align:center;position:relative;overflow:hidden}
.cs-glow{position:absolute;width:500px;height:500px;border-radius:50%;background:radial-gradient(circle,rgba(124,58,237,.12) 0%,transparent 70%);top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none}
.cs-ico{width:88px;height:88px;border-radius:26px;background:var(--grad);display:flex;align-items:center;justify-content:center;margin:0 auto 28px;box-shadow:0 0 50px rgba(124,58,237,.4),0 16px 40px rgba(0,0,0,.4);animation:csPulse 3s ease-in-out infinite}
@keyframes csPulse{0%,100%{box-shadow:0 0 50px rgba(124,58,237,.4),0 16px 40px rgba(0,0,0,.4)}50%{box-shadow:0 0 80px rgba(124,58,237,.65),0 16px 40px rgba(0,0,0,.4)}}
.cs-title{font-size:clamp(1.8rem,5vw,2.8rem);font-weight:800;letter-spacing:-.03em;color:#f1f5f9;margin-bottom:12px}
.cs-title span{background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.cs-sub{font-size:15px;color:#64748b;max-width:400px;line-height:1.7;margin-bottom:36px}
.cs-chips{display:flex;gap:10px;flex-wrap:wrap;justify-content:center}
.cs-chip{padding:8px 18px;border-radius:20px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);font-size:13px;color:#94a3b8}
/* Animations boutons lecteur */
@keyframes btnBounce{0%{transform:scale(1)}28%{transform:scale(.78)}62%{transform:scale(1.16)}82%{transform:scale(.95)}100%{transform:scale(1)}}
@keyframes btnRipple{0%{box-shadow:0 0 0 0 rgba(124,58,237,.7),0 0 0 0 rgba(6,182,212,.4)}100%{box-shadow:0 0 0 22px rgba(124,58,237,0),0 0 0 36px rgba(6,182,212,0)}}
.btn-clicked{animation:btnBounce .38s cubic-bezier(.4,0,.2,1)!important;transform-origin:center}
.nc-play.btn-clicked{animation:btnBounce .38s cubic-bezier(.4,0,.2,1),btnRipple .52s ease!important}

/* ══════════ PLAYLISTS ══════════ */
.pl-wrap{flex:1;overflow:hidden;display:flex;min-height:0}
.pl-side{width:240px;flex-shrink:0;background:rgba(6,6,20,.97);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border-right:1px solid rgba(124,58,237,.1);display:flex;flex-direction:column}
.pl-side-hd{padding:15px 13px 11px;border-bottom:1px solid rgba(124,58,237,.07);display:flex;align-items:center;justify-content:space-between}
.pl-side-t{font-size:11px;font-weight:800;letter-spacing:.9px;text-transform:uppercase;background:linear-gradient(90deg,#c4b5fd,#67e8f9);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.new-pl-btn{padding:7px 12px;border-radius:8px;border:none;cursor:pointer;font-size:11px;font-weight:700;font-family:inherit;background:linear-gradient(135deg,#7c3aed,#06b6d4);color:#fff;box-shadow:0 2px 10px rgba(124,58,237,.35);transition:box-shadow .2s cubic-bezier(.4,0,.2,1),transform .2s cubic-bezier(.4,0,.2,1)}
.new-pl-btn:hover{box-shadow:0 4px 20px rgba(124,58,237,.65);transform:translateY(-1px) scale(1.04)}
.new-pl-btn:active{transform:scale(.93)}
.pl-list{flex:1;overflow-y:auto;padding:8px}
/* Playlist items */
.pl-item{display:flex;align-items:center;gap:10px;padding:10px 10px;border-radius:12px;cursor:pointer;transition:background .22s cubic-bezier(.4,0,.2,1),border-color .22s,transform .22s cubic-bezier(.4,0,.2,1),box-shadow .22s;margin-bottom:4px;border:1px solid transparent;animation:plIn .3s cubic-bezier(.4,0,.2,1) both}
@keyframes plIn{from{opacity:0;transform:translateX(-16px)}to{opacity:1;transform:translateX(0)}}
.pl-item:hover{background:rgba(124,58,237,.1);border-color:rgba(124,58,237,.18);transform:translateX(4px)}
.pl-item.on{background:rgba(124,58,237,.17);border-color:rgba(124,58,237,.32);box-shadow:0 2px 16px rgba(124,58,237,.15)}
.pl-item-ico{width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#7c3aed,#06b6d4);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;box-shadow:0 3px 12px rgba(124,58,237,.28);transition:transform .22s cubic-bezier(.4,0,.2,1),box-shadow .22s}
.pl-item:hover .pl-item-ico{transform:scale(1.1) rotate(-4deg);box-shadow:0 5px 20px rgba(124,58,237,.52)}
.pl-item.on .pl-item-ico{box-shadow:0 4px 18px rgba(124,58,237,.5)}
.pl-item-name{font-size:12px;font-weight:700;color:#c4b5fd;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:color .2s}
.pl-item:hover .pl-item-name,.pl-item.on .pl-item-name{color:#e9d5ff}
.pl-item-cnt{font-size:10px;color:#475569;padding:2px 7px;border-radius:10px;background:rgba(124,58,237,.1);flex-shrink:0;transition:background .2s,color .2s}
.pl-item.on .pl-item-cnt{background:rgba(124,58,237,.26);color:#c4b5fd}
.pl-del{width:22px;height:22px;border-radius:50%;border:none;cursor:pointer;background:rgba(244,63,94,.12);color:#fb7185;font-size:11px;display:none;align-items:center;justify-content:center;transition:background .18s,transform .2s cubic-bezier(.4,0,.2,1)}
.pl-item:hover .pl-del{display:flex}
.pl-del:hover{background:rgba(244,63,94,.3);transform:scale(1.18)}
/* Sidebar cover collage */
.pl-item-cov{width:38px;height:38px;border-radius:10px;overflow:hidden;flex-shrink:0;background:linear-gradient(135deg,#1e1e50,#0d0d28);display:grid;grid-template-columns:1fr 1fr;gap:2px;box-shadow:0 3px 12px rgba(124,58,237,.28);transition:transform .22s cubic-bezier(.4,0,.2,1),box-shadow .22s}
.pl-item:hover .pl-item-cov{transform:scale(1.1) rotate(-4deg);box-shadow:0 5px 20px rgba(124,58,237,.52)}
.pl-item.on .pl-item-cov{box-shadow:0 4px 18px rgba(124,58,237,.5)}
.pl-item-cov.c1{display:block}
.pl-item-cov img{width:100%;height:100%;object-fit:cover;display:block}
/* Sidebar meta column */
.pl-item-meta{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
.pl-item-name{font-size:12px;font-weight:700;color:#c4b5fd;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:color .2s}
.pl-item:hover .pl-item-name,.pl-item.on .pl-item-name{color:#e9d5ff}
.pl-item-dur{font-size:9.5px;color:#334155;transition:color .2s;white-space:nowrap}
.pl-item:hover .pl-item-dur,.pl-item.on .pl-item-dur{color:#64748b}
.pl-item-right{display:flex;align-items:center;gap:5px;flex-shrink:0}
/* Now-playing animated bars */
@keyframes bars{0%,100%{transform:scaleY(.35)}50%{transform:scaleY(1)}}
.pl-now-ico{display:flex;align-items:flex-end;gap:2px;height:14px}
.pl-now-ico i{width:3px;border-radius:1.5px;background:#a78bfa;transform-origin:bottom;display:block}
.pl-now-ico.playing i{animation:bars .85s ease-in-out infinite}
.pl-now-ico.playing i:nth-child(1){height:14px;animation-delay:0s}
.pl-now-ico.playing i:nth-child(2){height:10px;animation-delay:.2s}
.pl-now-ico.playing i:nth-child(3){height:12px;animation-delay:.4s}
.pl-now-ico.paused i:nth-child(1){height:10px}
.pl-now-ico.paused i:nth-child(2){height:7px}
.pl-now-ico.paused i:nth-child(3){height:9px}
/* Rename button */
.pl-ren{width:22px;height:22px;border-radius:50%;border:none;cursor:pointer;background:rgba(124,58,237,.1);color:#7c3aed;font-size:10px;display:none;align-items:center;justify-content:center;transition:background .18s;flex-shrink:0;margin-right:2px}
.pl-item:hover .pl-ren{display:flex}
.pl-ren:hover{background:rgba(124,58,237,.3)}
/* Track drag-drop */
.pl-song[draggable=true]{cursor:grab}
.pl-song[draggable=true]:active{cursor:grabbing}
.pl-song.dg-over{background:rgba(124,58,237,.18);box-shadow:0 -2px 0 #7c3aed inset}
/* ══ PLAYLIST DETAIL — SPOTIFY STYLE ══ */
.pl-detail{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;display:flex;flex-direction:column}
/* Back button */
.pl-back-btn{display:none;align-items:center;gap:7px;padding:7px 10px 7px 6px;background:rgba(0,0,0,.35);backdrop-filter:blur(12px);border:none;cursor:pointer;color:rgba(255,255,255,.75);font-size:13px;font-weight:600;font-family:inherit;border-radius:20px;transition:color .18s,background .18s;white-space:nowrap;flex-shrink:0;position:absolute;top:14px;left:14px;z-index:20}
.pl-back-btn:hover{color:#fff;background:rgba(0,0,0,.55)}
.pl-back-btn svg{flex-shrink:0}
/* Hero */
.pl-hero{position:relative;padding:36px 24px 22px;display:flex;align-items:flex-end;gap:22px;min-height:200px;overflow:hidden;flex-shrink:0}
.pl-hero-bg{position:absolute;inset:-20px;background:linear-gradient(135deg,#3d1275 0%,#0e0e2e 100%);transition:background 1.2s ease}
.pl-hero-bg-img{position:absolute;inset:-40px;background-size:cover;background-position:center;filter:blur(70px) brightness(.28) saturate(2.5);opacity:.9;transition:background-image 1s ease}
.pl-hero-fade{position:absolute;bottom:0;left:0;right:0;height:80px;background:linear-gradient(to bottom,transparent,rgba(7,7,26,.95))}
/* Cover collage */
.pl-hero-cov{position:relative;z-index:1;width:156px;height:156px;border-radius:10px;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,.7),0 0 0 1px rgba(255,255,255,.06);flex-shrink:0;background:linear-gradient(135deg,#1e1e50,#0d0d28);display:grid;grid-template-columns:1fr 1fr;gap:2px}
.pl-hero-cov.single{display:block}
.pl-hero-cov img{width:100%;height:100%;object-fit:cover;display:block}
.pl-hero-cov-ph{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:52px;color:rgba(255,255,255,.12);grid-column:span 2}
/* Info */
.pl-hero-info{position:relative;z-index:1;flex:1;min-width:0}
.pl-hero-label{font-size:10px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:rgba(255,255,255,.55);margin-bottom:8px}
.pl-hero-name{font-size:clamp(26px,4.5vw,54px);font-weight:900;color:#fff;line-height:1.04;letter-spacing:-1.5px;margin-bottom:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pl-hero-meta{font-size:13px;color:rgba(255,255,255,.5);display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.pl-hero-meta strong{color:rgba(255,255,255,.85);font-weight:600}
/* Controls */
.pl-ctrl{flex-shrink:0;padding:14px 24px 6px;display:flex;align-items:center;gap:16px;background:linear-gradient(to bottom,rgba(7,7,26,.92),rgba(7,7,26,.75))}
.pl-btn-play{width:54px;height:54px;border-radius:50%;border:none;cursor:pointer;background:var(--grad);color:#fff;font-size:20px;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 28px rgba(124,58,237,.55);transition:transform .2s cubic-bezier(.4,0,.2,1),box-shadow .2s;flex-shrink:0;padding-left:3px}
.pl-btn-play:hover{transform:scale(1.1);box-shadow:0 8px 36px rgba(124,58,237,.75)}
.pl-btn-play:active{transform:scale(.92)}
.pl-ctrl-ico{background:none;border:none;cursor:pointer;color:rgba(255,255,255,.42);font-size:20px;width:40px;height:40px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:color .2s,background .2s,transform .2s;font-family:inherit}
.pl-ctrl-ico:hover{color:#fff;background:rgba(255,255,255,.07);transform:scale(1.12)}
.pl-ctrl-cnt{flex:1;font-size:12px;color:rgba(255,255,255,.35);text-align:right;letter-spacing:.2px}
/* Table header */
.pl-songs{flex:1;padding:6px 8px 24px}
.pl-tbl-hd{display:grid;grid-template-columns:44px minmax(0,1fr) 70px 42px;align-items:center;padding:6px 8px 6px 8px;border-bottom:1px solid rgba(255,255,255,.07);margin-bottom:2px}
.pl-tbl-hd span{font-size:10px;font-weight:700;letter-spacing:.9px;text-transform:uppercase;color:rgba(255,255,255,.28)}
.pl-tbl-hd .ph-dur{text-align:right}
/* Song rows */
@keyframes songIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.pl-song{display:grid;grid-template-columns:44px minmax(0,1fr) 70px 42px;align-items:center;padding:5px 8px;border-radius:6px;cursor:pointer;transition:background .15s;animation:songIn .25s ease both;position:relative}
.pl-song:hover{background:rgba(255,255,255,.065)}
/* # column */
.pl-song-idx{display:flex;align-items:center;justify-content:center;height:40px}
.pl-idx-num{font-size:14px;color:rgba(255,255,255,.38);font-weight:500;transition:opacity .15s}
.pl-song:hover .pl-idx-num{opacity:0}
.pl-idx-ico{display:none;color:#fff;font-size:12px;position:absolute;left:14px}
.pl-song:hover .pl-idx-ico{display:flex;align-items:center;justify-content:center;width:16px}
/* Title cell */
.pl-song-cell{display:flex;align-items:center;gap:12px;min-width:0;padding-right:8px}
.pl-song-art{width:40px;height:40px;border-radius:4px;overflow:hidden;flex-shrink:0;background:var(--bg3);transition:box-shadow .2s}
.pl-song:hover .pl-song-art{box-shadow:0 3px 12px rgba(0,0,0,.5)}
.pl-song-art img{width:100%;height:100%;object-fit:cover;display:block}
.pl-song-info{min-width:0}
.pl-song-t{font-size:13px;font-weight:600;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.3}
.pl-song-m{font-size:11px;color:rgba(255,255,255,.42);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.3;margin-top:1px;transition:color .15s}
.pl-song:hover .pl-song-m{color:rgba(255,255,255,.65)}
/* Duration */
.pl-song-dur{font-size:13px;color:rgba(255,255,255,.35);text-align:right;font-variant-numeric:tabular-nums;padding-right:4px}
/* Remove */
.pl-song-rm{width:28px;height:28px;border-radius:50%;border:none;cursor:pointer;background:none;color:rgba(244,63,94,.0);font-size:15px;display:flex;align-items:center;justify-content:center;transition:background .18s,color .18s,transform .2s;margin:0 auto}
.pl-song:hover .pl-song-rm{color:rgba(244,63,94,.6)}
.pl-song-rm:hover{background:rgba(244,63,94,.18)!important;color:#f43f5e!important;transform:scale(1.18)}
.pl-empty{padding:60px 20px;text-align:center;color:rgba(255,255,255,.18);font-size:13px;line-height:1.8}
/* Unused old classes kept for compat */
.pl-dhd,.pl-dname,.pl-playall,.pl-song-play{display:none}

/* ══ POPUP PLAYLIST ══ */
#pl-popup{display:none;position:fixed;z-index:500;background:rgba(10,10,30,.95);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border:1px solid rgba(124,58,237,.28);border-radius:14px;padding:6px;box-shadow:0 12px 40px rgba(0,0,0,.7),0 0 0 1px rgba(255,255,255,.03);min-width:190px}
#pl-popup.show{display:block;animation:popIn .18s cubic-bezier(.4,0,.2,1)}
@keyframes popIn{from{opacity:0;transform:scale(.94) translateY(-4px)}to{opacity:1;transform:scale(1) translateY(0)}}
.pp-item{padding:9px 12px;border-radius:9px;cursor:pointer;font-size:12px;font-weight:600;color:#a78bfa;display:flex;align-items:center;gap:9px;transition:background .15s,color .15s,padding-left .15s}
.pp-item:hover{background:rgba(124,58,237,.16);color:#e9d5ff;padding-left:16px}
.pp-new{border-top:1px solid rgba(124,58,237,.12);margin-top:4px;padding-top:4px;color:#22d3ee}

/* LECTEUR PRO */
/* ══════════ MINI-PLAYER ══════════ */
#player{
  flex-shrink:0;height:80px;position:relative;overflow:hidden;
  background:rgba(6,6,20,.92);
  backdrop-filter:blur(32px);-webkit-backdrop-filter:blur(32px);
  border-top:1px solid rgba(124,58,237,.18);
  box-shadow:0 -12px 48px rgba(0,0,0,.55),0 -1px 0 rgba(255,255,255,.03);
  display:flex;align-items:center;padding:0 20px;gap:0;
}
/* Barre de progression en haut du player */
#player::before{content:'';display:none}
.ply-prog-top{position:absolute;top:0;left:0;right:0;height:3px;background:rgba(255,255,255,.05);cursor:pointer;z-index:10;transition:height .18s cubic-bezier(.4,0,.2,1)}
.ply-prog-top:hover{height:5px}
.ply-prog-top-f{height:100%;background:linear-gradient(90deg,#7c3aed,#06b6d4);border-radius:0 3px 3px 0;position:relative;pointer-events:none;transition:width .1s linear}
.ply-prog-top-f::after{content:'';position:absolute;right:-7px;top:50%;transform:translateY(-50%) scale(0);width:14px;height:14px;border-radius:50%;background:#fff;box-shadow:0 0 10px rgba(124,58,237,.9),0 0 0 2px rgba(124,58,237,.4);transition:transform .18s cubic-bezier(.4,0,.2,1)}
.ply-prog-top:hover .ply-prog-top-f::after{transform:translateY(-50%) scale(1)}
.ply-idle-msg{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;color:#1e293b;gap:10px;pointer-events:none}
/* Cover */
.ply-left{display:flex;align-items:center;gap:13px;flex:0 0 32%;min-width:0}
.ply-art-wrap{position:relative;flex-shrink:0}
.ply-art{width:54px;height:54px;border-radius:10px;overflow:hidden;background:#10103a;border:1.5px solid rgba(124,58,237,.25);box-shadow:0 0 0 0 rgba(124,58,237,.4);transition:box-shadow .4s cubic-bezier(.4,0,.2,1),border-color .4s,transform .4s}
#player.playing .ply-art{border-color:rgba(124,58,237,.7);box-shadow:0 0 0 3px rgba(124,58,237,.15),0 0 22px rgba(124,58,237,.4),0 6px 20px rgba(0,0,0,.6);transform:scale(1.03)}
.ply-art img{width:100%;height:100%;object-fit:cover;display:block;transition:opacity .3s ease}
.ply-art-ph{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:24px;color:#1e293b}
/* EQ bars */
.eq{display:none;align-items:flex-end;gap:2px;height:18px;flex-shrink:0}
#player.playing .eq{display:flex}
.eq-b{width:3px;background:linear-gradient(to top,#7c3aed,#06b6d4);border-radius:2px}
.eq-b:nth-child(1){animation:eq .9s ease-in-out infinite}
.eq-b:nth-child(2){animation:eq .7s ease-in-out infinite .15s}
.eq-b:nth-child(3){animation:eq 1.1s ease-in-out infinite .05s}
.eq-b:nth-child(4){animation:eq .8s ease-in-out infinite .3s}
@keyframes eq{0%,100%{height:3px}50%{height:18px}}
/* Track info */
.ply-info-wrap{min-width:0;flex:1;display:flex;align-items:center;gap:8px}
.ply-info{min-width:0;flex:1}
.ply-title{font-size:13px;font-weight:700;color:#f1f5f9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px;transition:opacity .25s ease,transform .25s ease}
.ply-artist{font-size:11px;color:#7c3aed;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:.2px}
.ply-title.changing,.ply-artist.changing{opacity:0;transform:translateY(-4px)}
.ply-fav-btn{background:none;border:none;cursor:pointer;font-size:17px;color:#1e293b;flex-shrink:0;transition:color .2s,transform .25s cubic-bezier(.4,0,.2,1);line-height:1}
.ply-fav-btn:hover{transform:scale(1.3)}
.ply-fav-btn.on{color:#f43f5e;text-shadow:0 0 12px rgba(244,63,94,.55)}
/* Controls */
.ply-center{flex:0 0 36%;display:flex;flex-direction:column;align-items:center;gap:8px}
.ply-ctrls{display:flex;align-items:center;gap:6px}
.ply-btn{width:34px;height:34px;border-radius:50%;border:none;cursor:pointer;background:transparent;color:#334155;font-size:15px;display:flex;align-items:center;justify-content:center;transition:color .18s,transform .2s cubic-bezier(.4,0,.2,1),background .18s;flex-shrink:0;font-family:inherit}
.ply-btn:hover{color:#c4b5fd;transform:scale(1.15);background:rgba(124,58,237,.08)}
.ply-btn.active{color:#7c3aed}
.ply-btn-main{width:44px;height:44px;border-radius:50%;border:none;cursor:pointer;background:linear-gradient(135deg,#7c3aed,#06b6d4);color:#fff;font-size:18px;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 18px rgba(124,58,237,.5),0 0 0 0 rgba(124,58,237,.3);transition:box-shadow .2s,transform .2s cubic-bezier(.4,0,.2,1);flex-shrink:0}
.ply-btn-main:hover{box-shadow:0 6px 26px rgba(124,58,237,.75),0 0 0 6px rgba(124,58,237,.12);transform:scale(1.07)}
.ply-btn-main:active{transform:scale(.93)}
/* Progress bar inline */
.ply-prog{display:flex;align-items:center;gap:9px;width:100%}
.ply-time{font-size:10px;color:#334155;flex-shrink:0;font-variant-numeric:tabular-nums;min-width:30px;transition:color .18s}
.ply-time:last-child{text-align:right}
.ply-bar{flex:1;height:3px;background:rgba(255,255,255,.07);border-radius:4px;cursor:pointer;position:relative;transition:height .18s cubic-bezier(.4,0,.2,1)}
.ply-bar:hover{height:5px}
.ply-bar:hover .ply-time{color:#a78bfa}
.ply-bar-f{height:100%;background:linear-gradient(90deg,#7c3aed,#06b6d4);border-radius:4px;position:relative;pointer-events:none}
.ply-bar-f::after{content:'';position:absolute;right:-5px;top:50%;transform:translateY(-50%) scale(0);width:11px;height:11px;border-radius:50%;background:#fff;box-shadow:0 0 8px rgba(124,58,237,.8);transition:transform .18s cubic-bezier(.4,0,.2,1)}
.ply-bar:hover .ply-bar-f::after{transform:translateY(-50%) scale(1)}
/* Volume */
.ply-right{flex:0 0 32%;display:flex;align-items:center;justify-content:flex-end;gap:10px}
.ply-vol-btn{background:none;border:none;cursor:pointer;font-size:15px;color:#334155;transition:color .18s,transform .2s;flex-shrink:0;font-family:inherit}
.ply-vol-btn:hover{color:#a78bfa;transform:scale(1.15)}
.ply-vol-track{width:80px;height:3px;background:rgba(255,255,255,.07);border-radius:4px;cursor:pointer;position:relative;transition:height .18s}
.ply-vol-track:hover{height:5px}
.ply-vol-f{height:100%;background:linear-gradient(90deg,#7c3aed,#06b6d4);border-radius:4px;pointer-events:none}
/* Expand */
.ply-expand{background:none;border:none;cursor:pointer;color:#1e293b;display:flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:8px;transition:color .18s,background .18s,transform .2s;flex-shrink:0;margin-left:4px}
.ply-expand:hover{color:#7c3aed;background:rgba(124,58,237,.1);transform:scale(1.1)}

/* NOW PLAYING FULL VIEW - SPOTIFY STYLE */
#np-view{position:fixed;inset:0;z-index:300;display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:hidden;background:linear-gradient(160deg,#0e0929 0%,#090920 45%,#061525 100%);opacity:0;transform:translateY(5%);pointer-events:none;transition:opacity .42s cubic-bezier(.4,0,.2,1),transform .42s cubic-bezier(.4,0,.2,1)}
#np-view.open{opacity:1;transform:translateY(0);pointer-events:all}
#np-bg{position:absolute;inset:-20px;background-size:cover;background-position:center;filter:blur(80px) brightness(0.1) saturate(2.5);transition:background-image 1.2s ease;opacity:.8}
.np-over{position:absolute;inset:0;background:linear-gradient(180deg,rgba(8,8,28,.75) 0%,rgba(9,9,28,.05) 45%,rgba(8,8,28,.75) 100%)}
.np-chevron{position:absolute;top:12px;left:50%;transform:translateX(-50%);background:none;border:none;cursor:pointer;color:rgba(255,255,255,.3);width:50px;height:38px;display:flex;align-items:center;justify-content:center;z-index:10;font-family:inherit;transition:color .18s}
.np-chevron:hover{color:rgba(255,255,255,.75)}
.np-chevron svg{transition:transform .2s cubic-bezier(.4,0,.2,1)}
.np-chevron:hover svg{transform:translateY(4px)}
.np-close{position:absolute;top:18px;right:18px;width:36px;height:36px;border-radius:50%;border:1px solid rgba(255,255,255,.08);cursor:pointer;background:rgba(255,255,255,.05);color:rgba(255,255,255,.45);display:flex;align-items:center;justify-content:center;z-index:10;backdrop-filter:blur(14px);transition:all .18s;font-family:inherit}
.np-close:hover{background:rgba(255,255,255,.12);color:#fff;border-color:rgba(255,255,255,.22);transform:scale(1.08)}
/* Main column */
.np-col{position:relative;display:flex;flex-direction:column;align-items:center;gap:24px;width:min(460px,88vw);padding:10px 0 28px}
/* Art */
.np-art-wrap{position:relative;width:min(290px,52vw);height:min(290px,52vw);flex-shrink:0}
.np-art-glow{position:absolute;inset:-16px;border-radius:28px;background:linear-gradient(135deg,rgba(124,58,237,.7),rgba(6,182,212,.5));filter:blur(28px);opacity:0;transition:opacity .5s}
#np-view.open .np-art-glow{opacity:.55;animation:npGlow 4s ease-in-out infinite}
@keyframes npGlow{0%,100%{opacity:.35;transform:scale(.98)}50%{opacity:.65;transform:scale(1.03)}}
.np-art-sq{position:absolute;inset:0;border-radius:18px;overflow:hidden;box-shadow:0 28px 72px rgba(0,0,0,.8),0 0 0 1px rgba(255,255,255,.07);z-index:1}
.np-art-sq img{width:100%;height:100%;object-fit:cover;display:block}
.np-art-ph{width:100%;height:100%;background:rgba(255,255,255,.04);display:flex;align-items:center;justify-content:center;font-size:80px;color:rgba(255,255,255,.08)}
/* Info */
.np-info{width:100%;text-align:center}
.np-row{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:5px}
.np-song{font-size:23px;font-weight:800;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:360px;letter-spacing:-.3px}
.np-auth{font-size:14px;color:rgba(255,255,255,.42);letter-spacing:.2px}
.np-fav{background:none;border:none;cursor:pointer;font-size:22px;color:rgba(255,255,255,.28);transition:color .15s,transform .2s;flex-shrink:0;line-height:1;font-family:inherit}
.np-fav:hover{color:rgba(255,255,255,.65);transform:scale(1.25)}
.np-fav.on{color:#f43f5e;text-shadow:0 0 18px rgba(244,63,94,.55)}
/* Progress */
.np-prog{width:100%}
.np-prog-row{display:flex;align-items:center;gap:11px}
.np-pt{font-size:11px;color:rgba(255,255,255,.35);font-variant-numeric:tabular-nums;min-width:34px}
.np-pt:last-child{text-align:right}
.np-track{flex:1;height:4px;background:rgba(255,255,255,.12);border-radius:4px;cursor:pointer;position:relative;transition:height .12s}
.np-track:hover{height:6px}
.np-fill{height:100%;background:linear-gradient(90deg,#a78bfa,#67e8f9);border-radius:4px;position:relative;pointer-events:none}
.np-fill::after{content:'';position:absolute;right:-7px;top:50%;transform:translateY(-50%);width:14px;height:14px;border-radius:50%;background:#fff;box-shadow:0 0 10px rgba(167,139,250,.9);opacity:0;transition:opacity .12s}
.np-track:hover .np-fill::after{opacity:1}
/* Controls */
.np-ctrls{display:flex;align-items:center;gap:8px}
.nc-btn{background:none;border:none;cursor:pointer;color:rgba(255,255,255,.48);display:flex;align-items:center;justify-content:center;width:52px;height:52px;border-radius:50%;transition:all .15s;font-family:inherit}
.nc-btn:hover{color:#fff;background:rgba(255,255,255,.06)}
.nc-btn.active{color:#c4b5fd}
.nc-play{width:72px;height:72px;border-radius:50%;border:none;background:linear-gradient(135deg,#7c3aed,#06b6d4);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 32px rgba(124,58,237,.65);transition:all .2s;flex-shrink:0}
.nc-play:hover{box-shadow:0 8px 42px rgba(124,58,237,.85);transform:scale(1.07)}
.nc-play:active{transform:scale(.93)}
/* Volume */
.np-vol{display:flex;align-items:center;gap:10px}
.nv-ico{background:none;border:none;cursor:pointer;color:rgba(255,255,255,.38);display:flex;align-items:center;transition:color .15s;font-family:inherit}
.nv-ico:hover{color:rgba(255,255,255,.75)}
.nv-track{width:100px;height:4px;background:rgba(255,255,255,.1);border-radius:4px;cursor:pointer;transition:height .12s}
.nv-track:hover{height:6px}
.nv-fill{height:100%;background:rgba(255,255,255,.38);border-radius:4px;pointer-events:none}

/* ══ STATUS BAR ══ */
#stb{flex-shrink:0;height:22px;background:rgba(4,4,14,.85);border-top:1px solid rgba(255,255,255,.03);display:flex;align-items:center;justify-content:space-between;padding:0 18px;font-size:10px;color:var(--text4);letter-spacing:.2px}
.stb-dot{width:5px;height:5px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);display:inline-block;margin-right:5px;animation:dot-pulse 2.5s ease-in-out infinite}

/* ══ UTILS ══ */
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;width:12px;height:12px;border:2px solid rgba(255,255,255,.15);border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle}
@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}

/* ══ TOAST ══ */
#toast{
  position:fixed;bottom:108px;left:50%;
  transform:translateX(-50%) translateY(16px) scale(.94);
  background:rgba(14,14,38,.95);
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border:1px solid rgba(124,58,237,.4);
  padding:10px 22px;border-radius:30px;
  font-size:12px;font-weight:700;letter-spacing:.3px;
  color:#c4b5fd;
  box-shadow:0 8px 32px rgba(124,58,237,.3),0 0 0 1px rgba(255,255,255,.04);
  opacity:0;pointer-events:none;
  transition:opacity .3s cubic-bezier(.4,0,.2,1),transform .3s cubic-bezier(.34,1.56,.64,1);
  z-index:999;white-space:nowrap;
}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0) scale(1)}

/* ── SAFE AREA (iOS) ─────────────────────────────────────────── */
#player{padding-bottom:max(0px,env(safe-area-inset-bottom))}
.np-col{padding-bottom:max(20px,calc(env(safe-area-inset-bottom)+10px))}

/* ═════════════════════════════════════════════
   MOBILE  ≤ 640px
   ═════════════════════════════════════════════ */
@media(max-width:640px){

  /* ─ HEADER ─ */
  .hd{height:54px;padding:0 14px}
  .hd-sub,.hd-badge{display:none}
  .hd-name{font-size:16px;letter-spacing:-.4px}
  .hd-ico{width:32px;height:32px;font-size:14px;border-radius:9px}

  /* ─ BOTTOM NAV ─ */
  .tabs{order:10;flex-shrink:0;border-top:1px solid rgba(124,58,237,.2);border-bottom:none;background:rgba(5,5,18,.96);backdrop-filter:blur(28px);-webkit-backdrop-filter:blur(28px);justify-content:space-around;padding:0;padding-bottom:env(safe-area-inset-bottom);gap:0}
  .tb{flex:1;flex-direction:column;align-items:center;gap:3px;padding:9px 6px 7px;font-size:9px;letter-spacing:.3px;border-bottom:none;border-top:2px solid transparent;border-radius:0;justify-content:center;color:var(--text4)}
  .tb.on{border-top-color:var(--purple);color:#c4b5fd;background:transparent}
  .tbdot{display:none}
  .tb-ico{display:block;margin:0 auto 3px;opacity:.65}
  .tb.on .tb-ico{display:none}

  /* ─ MINI PLAYER ─ */
  #player{order:9;height:70px;padding:0 14px;gap:12px}
  #player::before{height:1px}
  .ply-art{width:46px;height:46px;border-radius:7px}
  .ply-left{flex:0 0 auto;gap:10px}
  .ply-info{flex:1;min-width:0}
  .ply-title{font-size:13px}.ply-artist{font-size:11px}
  .ply-center{flex:0 0 auto;gap:6px}
  .ply-prog{display:none}
  .ply-btn{width:28px;height:28px}
  .ply-btn-main{width:40px;height:40px;font-size:16px}
  .ply-right{flex:0 0 auto}
  .ply-vol-btn,.ply-vol-track{display:none}
  .ply-expand{display:flex;color:#475569;width:34px;height:34px}
  .ply-fav-btn{display:none}
  #stb{display:none}

  /* ─ RECHERCHE ─ */
  .sb{padding:10px 12px 9px}.sb-row{gap:7px}
  .btn-all,.dbar{display:none!important}
  .si-inner{height:44px}.btn-go{height:44px;padding:0 18px;font-size:13px}

  /* ─ RÉSULTATS ─ */
  .rl{padding:10px 12px 20px;gap:9px}
  .rc{min-height:78px;padding:10px 12px 10px 14px;gap:12px}
  .rc::before{width:3px}
  .rt{width:78px;height:50px;border-radius:7px}.rt-ph{width:78px;height:50px}
  .ri-title{font-size:13px;margin-bottom:3px}.ri-views{display:none}
  .ra{gap:5px}
  .dl-btn{padding:9px 14px;font-size:12px;border-radius:8px}.dl-btn svg{display:none}
  .ok-badge{padding:7px 11px;font-size:11px}.cancel-btn{padding:5px 10px;font-size:11px}

  /* ─ BIBLIOTHÈQUE mobile ─ */
  .lhd{padding:11px 14px;gap:8px;flex-wrap:wrap}
  .lhd-t{font-size:15px}.lhd-btns{gap:6px}
  .lib-search-wrap{min-width:140px;max-width:100%}
  .lbtn,.del-sel-btn,.fav-btn{padding:6px 11px;font-size:10px}

  .lgrid{gap:0;padding:2px 0}
  .lgrid>.mt{padding:40px 20px}
  .lcard{padding:9px 12px;gap:10px}
  .lcard:hover{transform:none}
  .la{width:48px!important;height:48px!important}
  .linfo-t{font-size:13px}
  .linfo-m{font-size:10px;margin-bottom:5px}
  /* Tous les boutons visibles sur mobile — compacts, icônes seules */
  .lcb-play-t{display:none}
  .lcb{height:30px;border-radius:7px}
  .lcb-play{width:30px;padding:0;font-size:14px}
  .lcb-pl{width:30px;font-size:15px}
  .lcb-fav{width:30px;font-size:14px}
  .lcb-del{width:30px;font-size:12px}
  .lcb-fav.on{color:#f43f5e!important;background:rgba(244,63,94,.12)!important;border-color:rgba(244,63,94,.25)!important}

  /* ─ PLAYLISTS — NAVIGATION PLEIN ÉCRAN ─ */
  .pl-wrap{position:relative;overflow:hidden;flex-direction:row}
  .pl-side{
    position:absolute;inset:0;width:100%;border:none;
    background:rgba(7,7,28,.98);z-index:2;max-height:none;
    overflow-y:auto;flex-shrink:0;
    transition:transform .34s cubic-bezier(.4,0,.2,1),opacity .34s;
    transform:translateX(0);opacity:1;
  }
  .pl-detail{
    position:absolute;inset:0;width:100%;
    transform:translateX(100%);opacity:.7;
    transition:transform .34s cubic-bezier(.4,0,.2,1),opacity .34s;
    z-index:1;display:flex;flex-direction:column;
    background:rgba(7,7,28,.98);overflow:hidden;
  }
  .pl-wrap.in-detail .pl-side{transform:translateX(-100%);opacity:.6}
  .pl-wrap.in-detail .pl-detail{transform:translateX(0);opacity:1;z-index:3}

  .pl-side-hd{padding:14px 16px;position:sticky;top:0;background:rgba(7,7,28,.98);z-index:1;border-bottom:1px solid rgba(124,58,237,.1);backdrop-filter:blur(10px)}
  .pl-item{padding:13px 16px;gap:12px;border-radius:0;border-bottom:1px solid rgba(255,255,255,.04);transform:none!important}
  .pl-item-ico,.pl-item-cov{width:44px;height:44px;border-radius:10px;font-size:18px}
  .pl-item-name{font-size:14px}
  .pl-item-cnt{font-size:11px;padding:2px 8px}

  /* Back button visible sur mobile */
  .pl-back-btn{display:flex!important}
  .pl-dhd{padding:12px 14px 10px;gap:10px;flex-wrap:wrap}
  .pl-dname{font-size:16px}
  .pl-songs{flex:1;overflow-y:auto;padding:6px 10px 10px}
  .pl-song{padding:11px 12px;gap:13px;margin-bottom:6px;border-radius:10px}
  .pl-song-art{width:46px;height:46px;border-radius:8px}
  .pl-song-t{font-size:14px}.pl-song-m{display:none}
  .pl-song-play{width:36px;height:36px;font-size:14px}
  .pl-song-rm{width:30px;height:30px;font-size:13px}

  /* ─ POPUP → BOTTOM SHEET ─ */
  #pl-popup.show{
    position:fixed!important;
    bottom:0!important;top:auto!important;
    left:0!important;right:0!important;
    width:100%!important;
    border-radius:20px 20px 0 0;
    border:1px solid rgba(124,58,237,.25);border-bottom:none;
    background:#0f0f32;
    padding:0 0 env(safe-area-inset-bottom);
    box-shadow:0 -8px 40px rgba(0,0,0,.65);
    animation:sheetUp .28s cubic-bezier(.4,0,.2,1);
    min-width:auto!important;z-index:600;
  }
  @keyframes sheetUp{from{transform:translateY(110%)}to{transform:translateY(0)}}
  .pp-item{padding:15px 20px;font-size:15px;gap:12px;border-radius:0}

  /* Backdrop pour bottom sheet et np */
  #pl-backdrop{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:499;-webkit-tap-highlight-color:transparent}
  #pl-backdrop.show{display:block}

  /* ─ NOW PLAYING (slide depuis le bas sur mobile) ─ */
  #np-view{transform:translateY(100%)}
  #np-view.open{transform:translateY(0)}
  .np-close{display:none}
  .np-chevron{color:rgba(255,255,255,.4);width:56px;height:44px;top:8px}
  .np-col{width:92vw;gap:20px;padding:4px 0 16px}
  .np-art-wrap{width:72vw;height:72vw}
  .np-art-sq{border-radius:14px}
  .np-song{font-size:20px;max-width:84vw}.np-auth{font-size:14px}
  .np-prog-row{gap:10px}.np-pt{font-size:11px;min-width:32px}.np-track{height:5px}
  .np-ctrls{gap:6px}.nc-btn{width:50px;height:50px}.nc-play{width:68px;height:68px}
  .np-fav{font-size:24px}.np-vol{gap:8px}.nv-track{width:110px}

  /* ─ TOAST ─ */
  #toast{bottom:130px;font-size:12px;padding:9px 20px}
}

/* ── TRÈS PETIT (≤ 380px) ─────────────────────────────────────── */
@media(max-width:380px){
  .hd-name{font-size:13px}
  .tb{font-size:9px;padding:7px 4px 6px}
  .tb-ico{width:16px;height:16px}
  .rc{gap:9px}.rt{width:66px;height:44px}
  .la{width:52px!important;height:52px!important}
  .linfo-t{font-size:13px}
  .lgrid>.mt{padding:30px 16px}
  .np-art-wrap{width:68vw;height:68vw}
  .np-song{font-size:17px}
  .nc-play{width:60px;height:60px}.nc-btn{width:44px;height:44px}
  #player{height:66px;padding:0 12px;gap:10px}
  .ply-art{width:42px;height:42px}
  .pp-item{padding:13px 18px;font-size:14px}
}
/* ─ ONLINE / OFFLINE ─ */
.net-badge{display:flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.3px;border:1px solid;transition:background .4s,border-color .4s,color .4s;white-space:nowrap}
.net-badge.on{background:rgba(16,185,129,.1);border-color:rgba(16,185,129,.25);color:#10b981}
.net-badge.off{background:rgba(244,63,94,.12);border-color:rgba(244,63,94,.28);color:#f43f5e}
.net-dot{width:6px;height:6px;border-radius:50%;background:currentColor;flex-shrink:0;animation:netPls 2s ease-in-out infinite}
.net-badge.off .net-dot{animation:none}
@keyframes netPls{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.25;transform:scale(.6)}}
/* Offline wall — clean swap, no overlay */
.offl-wall{display:none;flex-direction:column;align-items:center;justify-content:center;flex:1;padding:24px 20px 48px;text-align:center}
body.is-offline .offl-wall{display:flex;animation:spUp .35s ease both}
body.is-offline .sb{display:none}
body.is-offline #rl{display:none}
body.is-offline .dl-btn,body.is-offline #alldl{opacity:.3;pointer-events:none}
.offl-card{background:rgba(12,12,34,.75);border:1px solid rgba(244,63,94,.16);border-radius:22px;padding:32px 28px 26px;display:flex;flex-direction:column;align-items:center;gap:14px;max-width:360px;width:100%;box-shadow:0 16px 56px rgba(0,0,0,.4),0 0 0 1px rgba(255,255,255,.03) inset}
.offl-ico{width:72px;height:72px;border-radius:20px;background:rgba(244,63,94,.09);border:1px solid rgba(244,63,94,.2);display:flex;align-items:center;justify-content:center;color:#f43f5e}
.offl-ttl{font-size:21px;font-weight:800;color:#f1f5f9;letter-spacing:-.5px}
.offl-desc{font-size:13px;color:#475569;line-height:1.75;max-width:250px}
.offl-sep{width:100%;height:1px;background:rgba(255,255,255,.06)}
.offl-avail{width:100%;display:flex;flex-direction:column;gap:9px;text-align:left}
.offl-row{display:flex;align-items:center;gap:10px;font-size:12px;font-weight:500;color:#475569}
.offl-row svg{color:#10b981;flex-shrink:0}
.offl-retry{margin-top:4px;padding:11px 22px;border-radius:13px;border:1px solid rgba(124,58,237,.3);background:rgba(124,58,237,.1);color:#a78bfa;font-size:13px;font-weight:600;font-family:inherit;cursor:pointer;display:flex;align-items:center;gap:9px;transition:background .2s,border-color .2s,transform .18s}
.offl-retry:hover{background:rgba(124,58,237,.2);border-color:rgba(124,58,237,.5);transform:translateY(-1px)}
.offl-retry:active{transform:scale(.95)}
.offl-retry.spin svg{animation:spinIco .7s linear infinite}
@keyframes spinIco{to{transform:rotate(360deg)}}
/* ══ SPLASH ══ */
#splash{position:fixed;inset:0;z-index:99999;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:hidden}
.sp-halo{position:absolute;width:340px;height:340px;border-radius:50%;background:radial-gradient(circle,rgba(124,58,237,.2) 0%,transparent 65%);top:50%;left:50%;transform:translate(-50%,-50%);animation:spHalo 3.2s ease-in-out infinite;pointer-events:none}
@keyframes spHalo{0%,100%{transform:translate(-50%,-50%) scale(1);opacity:.55}50%{transform:translate(-50%,-50%) scale(1.35);opacity:1}}
.sp-inner{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center}
.sp-logo{width:82px;height:82px;border-radius:24px;background:var(--grad);display:flex;align-items:center;justify-content:center;box-shadow:0 18px 52px rgba(124,58,237,.48),0 4px 18px rgba(0,0,0,.55);animation:spLogoIn .6s cubic-bezier(.34,1.56,.64,1) .04s both;margin-bottom:26px}
@keyframes spLogoIn{from{opacity:0;transform:scale(.55) translateY(8px)}to{opacity:1;transform:scale(1) translateY(0)}}
.sp-name{font-size:30px;font-weight:700;letter-spacing:-.6px;color:#fff;animation:spUp .42s cubic-bezier(.4,0,.2,1) .22s both;margin-bottom:7px;line-height:1}
.sp-name em{font-style:normal;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.sp-tag{font-size:10px;letter-spacing:2.8px;text-transform:uppercase;color:rgba(255,255,255,.28);animation:spUp .42s cubic-bezier(.4,0,.2,1) .32s both}
@keyframes spUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.sp-dots{display:flex;gap:7px;margin-top:48px;animation:spUp .42s cubic-bezier(.4,0,.2,1) .44s both}
.sp-dot{width:5px;height:5px;border-radius:50%;background:rgba(255,255,255,.18);animation:spDot 1.4s ease-in-out infinite}
.sp-dot:nth-child(1){animation-delay:0s}.sp-dot:nth-child(2){animation-delay:.2s}.sp-dot:nth-child(3){animation-delay:.4s}
@keyframes spDot{0%,100%{transform:scale(1);background:rgba(255,255,255,.15)}50%{transform:scale(1.6);background:rgba(124,58,237,.95)}}
/* Exit — content rushes forward into screen */
#splash.sp-exit{animation:spFadeBg .52s ease forwards}
#splash.sp-exit .sp-inner{animation:spRushIn .52s cubic-bezier(.4,0,1,1) forwards}
#splash.sp-exit .sp-halo{animation:spFadeBg .38s ease forwards}
@keyframes spFadeBg{to{opacity:0}}
@keyframes spRushIn{to{opacity:0;transform:scale(1.55);filter:blur(20px)}}
/* Bottom loader line */
.sp-line{position:absolute;bottom:0;left:0;height:2px;background:var(--grad);width:0%;animation:spLine 3.3s cubic-bezier(.05,.85,.2,1) .12s both}
@keyframes spLine{from{width:0%}to{width:100%}}
/* UPDATE BANNER */
#upd-banner{display:none;align-items:center;gap:10px;padding:9px 20px;background:linear-gradient(90deg,rgba(124,58,237,.15),rgba(8,145,178,.15));border-bottom:1px solid rgba(124,58,237,.3);font-size:.88rem;flex-shrink:0}
#upd-msg{flex:1;color:#e2e8f0}
#upd-banner strong{color:#a855f7}
#upd-prog{display:none;align-items:center;gap:7px;flex:1;max-width:180px}
#upd-ptrack{flex:1;height:3px;background:rgba(255,255,255,.1);border-radius:2px;overflow:hidden}
#upd-pfill{height:100%;background:linear-gradient(90deg,#7c3aed,#06b6d4);width:0%;transition:width .4s ease}
#upd-plbl{font-size:.75rem;color:#94a3b8;min-width:28px;text-align:right}
.upd-btn{padding:6px 16px;background:var(--grad);color:#fff;border:none;border-radius:8px;font-size:.82rem;font-weight:600;cursor:pointer;white-space:nowrap;font-family:inherit}
.upd-close{background:none;border:none;color:#64748b;cursor:pointer;font-size:1rem;padding:0 4px;line-height:1;flex-shrink:0}
.upd-close:hover{color:#e2e8f0}
</style>
</head>
<body>
<div id="app">

<!-- SPLASH SCREEN -->
<div id="splash">
  <div class="sp-halo"></div>
  <div class="sp-inner">
    <div class="sp-logo">
      <svg width="44" height="44" viewBox="0 0 24 24" fill="none">
        <rect x="1" y="15" width="4" height="8" rx="2" fill="white" opacity=".9"/>
        <rect x="7" y="10" width="4" height="13" rx="2" fill="white"/>
        <rect x="13" y="12" width="4" height="11" rx="2" fill="white" opacity=".9"/>
        <path d="M20 4v9" stroke="white" stroke-width="2" stroke-linecap="round"/>
        <path d="M18 10l2 3 2-3" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <div class="sp-name">Music <em>DL</em></div>
    <div class="sp-tag">YouTube &middot; MP3 &middot; 320 kbps</div>
    <div class="sp-dots">
      <div class="sp-dot"></div>
      <div class="sp-dot"></div>
      <div class="sp-dot"></div>
    </div>
  </div>
  <div class="sp-line"></div>
</div>

<!-- HEADER -->
<div class="hd">
  <div class="hd-logo">
    <div class="hd-ico">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="1" y="15" width="4" height="8" rx="2" fill="white" opacity=".9"/>
        <rect x="7" y="10" width="4" height="13" rx="2" fill="white"/>
        <rect x="13" y="12" width="4" height="11" rx="2" fill="white" opacity=".9"/>
        <path d="M20 4v9" stroke="white" stroke-width="2" stroke-linecap="round"/>
        <path d="M18 10l2 3 2-3" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <div>
      <div class="hd-name">Music DL</div>
      <div class="hd-sub">YouTube &rarr; MP3 &middot; 320 kbps &middot; <span id="hd-ver">v__VER__</span></div>
    </div>
  </div>
  <div class="net-badge on" id="net-badge"><div class="net-dot"></div><span id="net-lbl">En ligne</span></div>
</div>

<!-- UPDATE BANNER -->
<div id="upd-banner">
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
  <span id="upd-msg">Mise à jour disponible&nbsp;: <strong id="upd-ver"></strong></span>
  <div id="upd-prog"><div id="upd-ptrack"><div id="upd-pfill"></div></div><span id="upd-plbl">0%</span></div>
  <button id="upd-btn" class="upd-btn" onclick="updAction()">Installer</button>
  <button class="upd-close" onclick="document.getElementById('upd-banner').style.display='none'" title="Fermer">✕</button>
</div>

<!-- TABS -->
<div class="tabs">
  <div class="tb on" id="tab0" onclick="goTab(0)"><svg class="tb-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg><div class="tbdot"></div>RECHERCHE</div>
  <div class="tb" id="tab1" onclick="goTab(1)"><svg class="tb-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg><div class="tbdot"></div>Bibliothèque</div>
  <div class="tb" id="tab2" onclick="goTab(2)"><svg class="tb-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg><div class="tbdot"></div>PLAYLISTS</div>
  <div class="tb" id="tab3" onclick="goTab(3)"><svg class="tb-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg><div class="tbdot"></div>BIENTÔT</div>
</div>

<div class="pages">
<!-- PAGE 0: RECHERCHE -->
<div class="page on" id="page0">
  <div class="offl-wall" id="offl-wall">
    <div class="offl-card">
      <div class="offl-ico">
        <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <line x1="1" y1="1" x2="23" y2="23"/>
          <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/>
          <path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/>
          <path d="M10.71 5.05A16 16 0 0 1 22.56 9"/>
          <path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/>
          <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
          <line x1="12" y1="20" x2="12.01" y2="20"/>
        </svg>
      </div>
      <div class="offl-ttl">Mode Hors-ligne</div>
      <div class="offl-desc">La recherche et le t&eacute;l&eacute;chargement n&eacute;cessitent une connexion internet.</div>
      <div class="offl-sep"></div>
      <div class="offl-avail">
        <div class="offl-row">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20,6 9,17 4,12"/></svg>
          Biblioth&egrave;que locale disponible
        </div>
        <div class="offl-row">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20,6 9,17 4,12"/></svg>
          Playlists disponibles
        </div>
        <div class="offl-row">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20,6 9,17 4,12"/></svg>
          Lecture de musique normale
        </div>
      </div>
      <button class="offl-retry" id="offl-retry" onclick="checkConnection()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23,4 23,10 17,10"/><polyline points="1,20 1,14 7,14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
        V&eacute;rifier la connexion
      </button>
    </div>
  </div>
  <div class="sb">
    <div class="sb-row">
      <div class="si-wrap">
        <div class="si-inner">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          <input id="q" type="text" placeholder="Artiste, titre, album..." autocomplete="off" onkeydown="if(event.key==='Enter'){doSearch();hideSugBox();}">
        </div>
        <div id="sug-box"></div>
      </div>
      <button class="btn-go" id="sbtn" onclick="doSearch()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        Chercher
      </button>
      <button class="btn-all" id="alldl" onclick="dlAll()">&#8659; Tout</button>
    </div>
  </div>
  <div class="rl" id="rl">
    <div class="mt" id="mt0">
      <div class="mt-ico"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" opacity=".22"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg></div>
      <p>Tape un artiste ou un titre pour chercher</p>
    </div>
  </div>
</div>

<!-- PAGE 1: BIBLIOTHEQUE -->
<div class="page" id="page1">
  <div class="lhd">
    <div class="lhd-t">Bibliothèque <span class="lhd-cnt" id="lcnt" style="display:none">0</span></div>
    <div class="lib-search-wrap">
      <svg class="lib-search-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input class="lib-search" id="lib-search" type="text" placeholder="Rechercher dans la bibliothèque..." oninput="libSearchInput(this.value)" autocomplete="off">
    </div>
    <div class="lhd-btns">
      <button class="fav-btn" id="favBtn" onclick="toggleFavFilter()"><svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:-2px;margin-right:5px"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>Favoris</button>
      <button class="lbtn" id="selbtn" onclick="toggleSelectMode()"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:5px"><rect x="3" y="3" width="18" height="18" rx="2.5"/></svg>Sélectionner</button>
      <button class="del-sel-btn" id="delSelBtn" onclick="deleteSelected()"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:5px"><polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>Supprimer (<span id="selCount">0</span>)</button>
      <button class="lbtn" onclick="loadLib()" title="Rafraichir"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px"><polyline points="23,4 23,10 17,10"/><polyline points="1,20 1,14 7,14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg></button>
    </div>
  </div>
  <div class="lgrid" id="lgrid">
    <div class="mt" id="mt1" style="grid-column:1/-1">
      <div class="mt-ico"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" opacity=".22"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3z"/><path d="M3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg></div>
      <p>Aucune musique téléchargée</p>
    </div>
  </div>
</div>

<!-- PAGE 2: PLAYLISTS -->
<div class="page" id="page2">
  <div class="pl-wrap">
    <div class="pl-side">
      <div class="pl-side-hd">
        <div class="pl-side-t">Mes Playlists</div>
        <button class="new-pl-btn" onclick="createPlaylist()">+ Nouvelle</button>
      </div>
      <div class="pl-list" id="pl-list"></div>
    </div>
    <div class="pl-detail" id="pl-detail">
      <div class="pl-empty">Sélectionnez ou créez une playlist</div>
    </div>
  </div>
</div>
<!-- PAGE 3: COMING SOON -->
<div class="page" id="page3">
  <div class="cs-wrap">
    <div class="cs-glow"></div>
    <div class="cs-ico">
      <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/>
      </svg>
    </div>
    <div class="cs-title">Bientôt <span>disponible</span></div>
    <p class="cs-sub">De nouvelles fonctionnalités arrivent prochainement. Restez connecté pour les découvrir en premier.</p>
    <div class="cs-chips">
      <span class="cs-chip">Paroles synchronisées</span>
      <span class="cs-chip">Égaliseur</span>
      <span class="cs-chip">Recherche dans la bibliothèque</span>
      <span class="cs-chip">Sync cloud</span>
    </div>
  </div>
</div>
</div><!-- /.pages -->

<!-- CUSTOM CONFIRM DIALOG -->
<div class="dlg-overlay" id="dlg-overlay" onclick="dlgClose(event)">
  <div class="dlg-box" id="dlg-box">
    <div class="dlg-icon">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
    </div>
    <div class="dlg-title" id="dlg-title">Confirmer la suppression</div>
    <div class="dlg-msg" id="dlg-msg"></div>
    <div class="dlg-btns">
      <button class="dlg-cancel" onclick="dlgReject()">Annuler</button>
      <button class="dlg-confirm" id="dlg-confirm-btn">Supprimer</button>
    </div>
  </div>
</div>

<!-- LECTEUR PRO -->
<div id="player">
  <!-- barre de progression en haut -->
  <div class="ply-prog-top" id="ply-prog-top" onclick="seekFromTop(event)" style="display:none">
    <div class="ply-prog-top-f" id="ply-prog-top-f" style="width:0%"></div>
  </div>
  <div class="ply-idle-msg" id="ply-idle">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="opacity:.25;flex-shrink:0"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
    <span>Aucune musique en lecture &mdash; appuyez sur lecture dans la biblioth&egrave;que</span>
  </div>
  <!-- GAUCHE : pochette + infos -->
  <div class="ply-left" id="ply-left" style="visibility:hidden">
    <div class="ply-art-wrap">
      <div class="ply-art" id="ply-art" onclick="toggleNowPlaying()" style="cursor:pointer"><div class="ply-art-ph"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity=".3"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg></div></div>
    </div>
    <div class="eq">
      <div class="eq-b"></div><div class="eq-b"></div><div class="eq-b"></div><div class="eq-b"></div>
    </div>
    <div class="ply-info-wrap">
      <div class="ply-info" onclick="toggleNowPlaying()" style="cursor:pointer">
        <div class="ply-title" id="ply-title">—</div>
        <div class="ply-artist" id="ply-artist">—</div>
      </div>
      <button class="ply-fav-btn" id="ply-fav-btn" onclick="plyToggleFav()" title="Favoris"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg></button>
    </div>
  </div>
  <!-- CENTRE : controles + barre -->
  <div class="ply-center" id="ply-center" style="visibility:hidden">
    <div class="ply-ctrls">
      <button class="ply-btn" id="ply-shuf" onclick="plyToggleShuffle()" title="Al&eacute;atoire">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M16 3h5v5"/><path d="m21 3-7 7"/><path d="M16 21h5v-5"/><path d="m21 21-7-7"/><path d="M3 3l4 4"/><path d="M3 21l4-4"/></svg>
      </button>
      <button class="ply-btn" onclick="plyPrev()" title="Pr&eacute;c&eacute;dent">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/></svg>
      </button>
      <button class="ply-btn-main" id="ply-playbtn" onclick="plyToggle()">
        <svg id="ply-play-ico" width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
      </button>
      <button class="ply-btn" onclick="plyNext()" title="Suivant">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zm9-12v12h2V6h-2z"/></svg>
      </button>
      <button class="ply-btn" id="ply-rep" onclick="plyToggleRepeat()" title="R&eacute;p&eacute;ter">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
      </button>
    </div>
    <div class="ply-prog">
      <span class="ply-time" id="ply-cur">0:00</span>
      <div class="ply-bar" id="ply-bar">
        <div class="ply-bar-f" id="ply-bar-f" style="width:0%"></div>
      </div>
      <span class="ply-time" id="ply-dur">0:00</span>
    </div>
  </div>
  <!-- DROITE : volume -->
  <div class="ply-right" id="ply-right" style="visibility:hidden">
    <button class="ply-vol-btn" id="ply-vol-ico" onclick="plyMute()">
      <svg id="ply-vol-svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/><path d="M14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
    </button>
    <div class="ply-vol-track" id="ply-vol-track">
      <div class="ply-vol-f" id="ply-vol-f" style="width:80%"></div>
    </div>
    <button class="ply-expand" onclick="toggleNowPlaying()" title="Vue compl&egrave;te">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
    </button>
  </div>
</div>

<!-- STATUS BAR -->
<div id="stb">
  <span><span class="stb-dot"></span><span id="smsg">Prêt</span></span>
  <span id="srt"></span>
</div>
</div>
<!-- NOW PLAYING FULL VIEW -->
<div id="np-view">
  <div id="np-bg"></div>
  <div class="np-over"></div>
  <button class="np-chevron" onclick="closeNp()" title="Fermer">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
  </button>
  <button class="np-close" onclick="closeNp()">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
  </button>
  <div class="np-col">
    <!-- Pochette -->
    <div class="np-art-wrap">
      <div class="np-art-glow"></div>
      <div class="np-art-sq" id="np-art"><div class="np-art-ph"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity=".25"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg></div></div>
    </div>
    <!-- Info -->
    <div class="np-info">
      <div class="np-row">
        <div class="np-song" id="np-song">—</div>
        <button class="np-fav" id="np-fav-btn" onclick="plyToggleFav()"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg></button>
      </div>
      <div class="np-auth" id="np-auth">—</div>
    </div>
    <!-- Barre de progression -->
    <div class="np-prog">
      <div class="np-prog-row">
        <span class="np-pt" id="np-cur">0:00</span>
        <div class="np-track" id="np-track"><div class="np-fill" id="np-fill" style="width:0%"></div></div>
        <span class="np-pt" id="np-dur">0:00</span>
      </div>
    </div>
    <!-- Controles -->
    <div class="np-ctrls">
      <button class="nc-btn" id="np-shuf" onclick="plyToggleShuffle()" title="Al&eacute;atoire">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M16 3h5v5"/><path d="m21 3-7 7"/><path d="M16 21h5v-5"/><path d="m21 21-7-7"/><path d="M3 3l4 4"/><path d="M3 21l4-4"/></svg>
      </button>
      <button class="nc-btn" onclick="plyPrev()">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/></svg>
      </button>
      <button class="nc-play" onclick="plyToggle()">
        <svg id="np-play-ico" width="30" height="30" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
      </button>
      <button class="nc-btn" onclick="plyNext()">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zm9-12v12h2V6h-2z"/></svg>
      </button>
      <button class="nc-btn" id="np-rep" onclick="plyToggleRepeat()" title="R&eacute;p&eacute;ter">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
      </button>
    </div>
    <!-- Volume -->
    <div class="np-vol">
      <button class="nv-ico" onclick="plyMute()">
        <svg id="np-vol-svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/><path d="M14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
      </button>
      <div class="nv-track" id="np-vol-track"><div class="nv-fill" id="np-vol-fill" style="width:80%"></div></div>
    </div>
  </div>
</div>
<div id="pl-backdrop" onclick="document.getElementById('pl-popup').classList.remove('show');this.classList.remove('show')"></div>
<div id="toast"></div>
<div id="pl-popup"></div>
<div class="inp-overlay" id="inp-overlay" onclick="if(event.target===this)inpReject()">
  <div class="inp-box">
    <div class="inp-title" id="inp-title">Nouvelle playlist</div>
    <input class="inp-field" id="inp-field" type="text" maxlength="60" onkeydown="if(event.key==='Enter')inpAccept();if(event.key==='Escape')inpReject()">
    <div class="inp-btns">
      <button class="inp-cancel" onclick="inpReject()">Annuler</button>
      <button class="inp-ok" onclick="inpAccept()">Créer</button>
    </div>
  </div>
</div>
<audio id="aud"></audio>

<script>
var results=[],selectMode=false,selectedFiles=new Set();
var allLibFiles=[],favSet=new Set(),favOn=false,libQuery='';
var playlists={},curPl=null;
/* ── SVG ICON SYSTEM ── */
var _ip={
  note:'<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  play:'<polygon points="5,3 19,12 5,21"/>',
  'heart-e':'<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
  'heart-f':'<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
  mic:'<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>',
  clock:'<circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/>',
  trash:'<polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  refresh:'<polyline points="23,4 23,10 17,10"/><polyline points="1,20 1,14 7,14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  headphones:'<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3z"/><path d="M3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/>',
  x:'<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  shuffle:'<path d="M16 3h5v5"/><path d="m21 3-7 7"/><path d="M16 21h5v-5"/><path d="m21 21-7-7"/><path d="M3 3l4 4"/><path d="M3 21l4-4"/>',
  plus:'<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  eye:'<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  box:'<rect x="3" y="3" width="18" height="18" rx="2.5"/>',
  'box-check':'<rect x="3" y="3" width="18" height="18" rx="2.5"/><polyline points="9,12 11,14 15,10"/>',
};
var _ipFill={note:1,play:1,'heart-f':1,eye:1};
function ico(name,s){
  s=s||14;var p=_ip[name]||'';
  var f=_ipFill[name]?'fill="currentColor"':'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
  return '<svg width="'+s+'" height="'+s+'" viewBox="0 0 24 24" '+f+' style="display:inline-block;vertical-align:middle;flex-shrink:0">'+p+'</svg>';
}
var ICO_HEART_E=ico('heart-e',16),ICO_HEART_F='<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle;flex-shrink:0">'+_ip['heart-f']+'</svg>';
var plyQueue=[],plyIdx=0;
var aud=document.getElementById('aud');
function setVolUI(v){
  v=Math.max(0,Math.min(1,v));
  aud.volume=v;
  var pf=document.getElementById('ply-vol-f');if(pf)pf.style.width=(v*100)+'%';
  var nf=document.getElementById('np-vol-fill');if(nf)nf.style.width=(v*100)+'%';
  try{localStorage.setItem('mdl_vol',v);}catch(e){}
}
(function(){try{var sv=parseFloat(localStorage.getItem('mdl_vol'));if(!isNaN(sv))setVolUI(sv);else setVolUI(.8);}catch(e){setVolUI(.8);}})();

/* ── MEDIA SESSION API (notification + contrôles OS) ─────────── */
function setupMediaSession(){
  if(!('mediaSession' in navigator))return;
  var ms=navigator.mediaSession;
  ms.setActionHandler('play',    function(){aud.play();});
  ms.setActionHandler('pause',   function(){aud.pause();});
  ms.setActionHandler('previoustrack', function(){plyPrev();});
  ms.setActionHandler('nexttrack',     function(){plyNext();});
  try{ms.setActionHandler('seekbackward',function(d){aud.currentTime=Math.max(0,aud.currentTime-(d&&d.seekOffset||10));});}catch(e){}
  try{ms.setActionHandler('seekforward', function(d){aud.currentTime=Math.min(aud.duration||0,aud.currentTime+(d&&d.seekOffset||10));});}catch(e){}
}
function updateMediaMeta(fn,title,artist){
  if(!('mediaSession' in navigator)||!window.MediaMetadata)return;
  var base=window.location.origin;
  var art=base+'/api/cover/'+encodeURIComponent(fn);
  navigator.mediaSession.metadata=new MediaMetadata({
    title:title||fn, artist:artist||'', album:'Music DL',
    artwork:[{src:art,sizes:'512x512',type:'image/jpeg'},{src:art,sizes:'96x96',type:'image/jpeg'}]
  });
}
setupMediaSession();

/* AUTOCOMPLETE RECHERCHE */
(function(){
  var inp=document.getElementById('q');
  var box=document.getElementById('sug-box');
  var timer=null;
  function hideSug(){if(box)box.style.display='none';}
  window.hideSugBox=hideSug;
  if(!inp||!box)return;
  inp.addEventListener('input',function(){
    clearTimeout(timer);
    var v=inp.value.trim();
    if(!v){hideSug();return;}
    timer=setTimeout(function(){
      fetch('/api/suggest?q='+encodeURIComponent(v))
        .then(function(r){return r.json()})
        .then(function(items){
          if(!items||!items.length){hideSug();return;}
          box.innerHTML=items.map(function(s){
            var esc=s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            var safe=s.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
            return '<div class="sug-item" onmousedown="event.preventDefault();document.getElementById(\'q\').value=\''+safe+'\';doSearch();">'+esc+'</div>';
          }).join('');
          box.style.display='block';
        }).catch(function(){});
    },180);
  });
  document.addEventListener('click',function(e){if(!e.target.closest('.si-wrap'))hideSug();});
  inp.addEventListener('keydown',function(e){if(e.key==='Escape')hideSug();});
})();

/* TABS */
var _curTab=0;
function goTab(i){
  var dir=i>_curTab?1:-1;
  [0,1,2,3].forEach(function(n){
    var p=document.getElementById('page'+n);
    if(!p)return;
    if(n===i){
      p.style.transform=dir>0?'translateX(28px) scale(.982)':'translateX(-28px) scale(.982)';
      p.classList.remove('on');
      void p.offsetWidth;
      p.style.transform='';
      p.classList.add('on');
    } else {
      p.classList.remove('on');
    }
    var t=document.getElementById('tab'+n);
    if(t)t.classList.toggle('on',n===i);
  });
  _curTab=i;
  if(i===1){var ls=document.getElementById('lib-search');if(ls&&libQuery){libQuery='';ls.value='';} loadLib();}
  if(i===2) loadPlaylists();
}

/* INIT */
fetch('/api/favorites').then(function(r){return r.json()}).then(function(f){f.forEach(function(fn){favSet.add(fn)})});
document.getElementById('q').focus();

/* RECHERCHE */
var _searchCtrl=null;
function doSearch(){
  var q=document.getElementById('q').value.trim();if(!q)return;
  hideSugBox();
  if(_searchCtrl){try{_searchCtrl.abort();}catch(e){}_searchCtrl=null;}
  var n=50;
  var btn=document.getElementById('sbtn'),lst=document.getElementById('rl'),emp=document.getElementById('mt0');
  btn.disabled=true;btn.innerHTML='<span class="spin"></span> Recherche...';
  emp.style.display='none';
  Array.from(lst.children).filter(function(c){return c.id!=='mt0'}).forEach(function(c){c.remove()});
  document.getElementById('alldl').style.display='none';setStat('Recherche: '+q);
  _searchCtrl=typeof AbortController!=='undefined'?new AbortController():null;
  var opts=_searchCtrl?{signal:_searchCtrl.signal}:{};
  fetch('/api/search?q='+encodeURIComponent(q)+'&n='+n,opts).then(function(r){return r.json()}).then(function(data){
    _searchCtrl=null;
    if(data.error)throw new Error(data.error);
    results=data;
    if(!data.length){emp.querySelector('p').textContent='Aucun resultat.';emp.style.display='flex';}
    else{data.forEach(function(item,i){lst.appendChild(mkCard(item,i))});document.getElementById('alldl').style.display='inline-flex';setStat(data.length+' resultats');setRight(data.length+' titres');}
    btn.disabled=false;btn.innerHTML='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg> Chercher';
  }).catch(function(e){
    if(e.name==='AbortError')return;
    emp.querySelector('p').textContent='Erreur: '+e.message;emp.style.display='flex';btn.disabled=false;btn.innerHTML='Chercher';setStat('Erreur.');
  });
}

function mkCard(item,i){
  var d=document.createElement('div');d.className='rc';d.style.animationDelay=(i*18)+'ms';
  var th=item.thumb?'<div class="rt"><img src="'+item.thumb+'" loading="lazy" onerror="this.parentNode.className=\'rt-ph\';this.remove()">'+(item.duration?'<span class="rt-dur">'+item.duration+'</span>':'')+'</div>':'<div class="rt-ph">'+ico('note',28)+'</div>';
  var meta='';
  if(item.channel)meta+='<span class="ri-ch">'+esc(item.channel)+'</span>';
  if(item.channel&&item.duration)meta+='<span class="ri-dot">&bull;</span>';
  if(item.duration)meta+='<span class="ri-dur">'+item.duration+'</span>';
  if(item.views)meta+='<span class="ri-dot">&bull;</span><span class="ri-views">'+ico('eye',12)+' '+item.views+'</span>';
  d.innerHTML=th+'<div class="ri"><div class="ri-title" title="'+esc(item.title)+'">'+esc(item.title)+'</div><div class="ri-row">'+meta+'</div><div class="rp" id="pg-'+item.id+'"><div class="rp-track"><div class="rp-fill" id="pf-'+item.id+'"></div></div><div class="rp-lbl" id="pl-'+item.id+'"></div></div></div>'
    +'<div class="ra"><button class="dl-btn" id="db-'+item.id+'" onclick="startDl(\''+item.id+'\',\''+esc(item.url)+'\',\''+esc(item.title)+'\')">&#8659; MP3</button><button class="cancel-btn" id="cb-'+item.id+'" onclick="cancelDl(\''+item.id+'\')">&#215; Annuler</button></div>';
  return d;
}

/* TELECHARGEMENT */
function startDl(id,url,title){
  var btn=document.getElementById('db-'+id),cbtn=document.getElementById('cb-'+id);
  var pg=document.getElementById('pg-'+id),fill=document.getElementById('pf-'+id),lbl=document.getElementById('pl-'+id);
  if(!btn||btn.dataset.go)return;
  btn.dataset.go='1';btn.disabled=true;btn.innerHTML='<span class="spin"></span>';
  cbtn.style.display='inline-flex';pg.style.display='block';
  var entry=null;for(var i=0;i<results.length;i++){if(results[i].id===id){entry=results[i];break;}}
  if(!entry)entry={id:id,url:url,title:title};
  fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(entry)})
    .then(function(r){return r.json();})
    .then(function(res){
      var jid=res.job_id;btn.dataset.jobid=jid;setStat('Téléchargement : '+title);
      var es=new EventSource('/api/progress/'+jid);
      es.onerror=function(){es.close();btn.dataset.go='';btn.disabled=false;btn.innerHTML=ico('refresh',13)+' Réessayer';cbtn.style.display='none';setStat('Erreur réseau.');toast('⚠ Erreur réseau');};
      es.onmessage=function(e){
        var d=JSON.parse(e.data);fill.style.width=d.progress+'%';lbl.textContent=d.status;
        if(d.done){
          es.close();cbtn.style.display='none';
          if(d.cancelled){
            fill.style.width='0%';fill.style.background='rgba(100,116,139,.3)';
            lbl.textContent='Annulé — cliquez pour réessayer';
            btn.dataset.go='';btn.disabled=false;btn.innerHTML='&#8659; Réessayer';
            setStat('Annulé : '+title);
          } else if(!d.error){
            fill.classList.add('done');btn.outerHTML='<div class="ok-badge">&#10003; Téléchargée</div>';
            setStat('OK : '+title);toast('&#10003; '+title);loadLib();
          } else {
            btn.dataset.go='';btn.disabled=false;btn.innerHTML=ico('refresh',13)+' Réessayer';
            setStat('Erreur.');toast('⚠ Échec : '+title);
          }
        }
      };
    })
    .catch(function(){
      btn.dataset.go='';btn.disabled=false;btn.innerHTML='&#8659; MP3';
      cbtn.style.display='none';pg.style.display='none';
      setStat('Erreur réseau.');toast('⚠ Impossible de lancer le téléchargement');
    });
}
function cancelDl(id){
  var btn=document.getElementById('db-'+id),jid=btn&&btn.dataset.jobid;if(!jid)return;
  fetch('/api/cancel/'+jid,{method:'POST'});
  var cb=document.getElementById('cb-'+id);if(cb){cb.disabled=true;cb.textContent='...';}
}
function dlAll(){results.forEach(function(item){var b=document.getElementById('db-'+item.id);if(b&&!b.dataset.go)startDl(item.id,item.url,item.title);})}

/* BIBLIOTHEQUE */
function fmtDate(mtime){
  if(!mtime)return '';
  var d=new Date(mtime*1000);
  var months=['janv','févr','mars','avr','mai','juin','juil','août','sept','oct','nov','déc'];
  return d.getDate()+' '+months[d.getMonth()]+' '+d.getFullYear();
}
function libSearchInput(v){libQuery=v.trim().toLowerCase();renderLib();}
function loadLib(){
  var grid=document.getElementById('lgrid'),emp=document.getElementById('mt1'),cnt=document.getElementById('lcnt');
  emp.style.display='none';
  Array.from(grid.children).filter(function(c){return c.id!=='mt1'}).forEach(function(c){c.remove()});
  cnt.style.display='none';selectedFiles.clear();updateSelUI();
  fetch('/api/library').then(function(r){return r.json()}).then(function(files){allLibFiles=files;renderLib();});
}
function renderLib(){
  var grid=document.getElementById('lgrid'),emp=document.getElementById('mt1');
  Array.from(grid.children).filter(function(c){return c.id!=='mt1'}).forEach(function(c){c.remove()});
  var show=allLibFiles;
  if(favOn) show=show.filter(function(f){return favSet.has(f.filename);});
  if(libQuery) show=show.filter(function(f){
    var q=libQuery;
    return (f.title||'').toLowerCase().indexOf(q)>-1||(f.artist||'').toLowerCase().indexOf(q)>-1||(f.album||'').toLowerCase().indexOf(q)>-1||(f.filename||'').toLowerCase().indexOf(q)>-1;
  });
  document.getElementById('lcnt').textContent=show.length;
  document.getElementById('lcnt').style.display=show.length?'inline-flex':'none';
  if(!show.length){emp.style.display='flex';return;}
  emp.style.display='none';setStat('Bibliothèque: '+show.length+' MP3');setRight(show.length+' fichiers');
  /* table header */
  var hd=document.createElement('div');
  hd.className='ltbl-hd';
  hd.innerHTML='<span></span><span>TITRE</span><span class="lhd-album">ALBUM</span><span class="lhd-date">AJOUTÉ LE</span><span style="text-align:right">DURÉE</span><span></span>';
  grid.insertBefore(hd,emp);
  show.forEach(function(f,i){grid.appendChild(mkLib(f,i))});
  if(selectMode)grid.classList.add('select-mode');
}
function mkLib(f,i){
  var d=document.createElement('div');
  d.className='lcard';d.style.animationDelay=(i*12)+'ms';
  d.id='lc-'+f.filename;d.dataset.fn=f.filename;
  d.onclick=function(){if(selectMode){toggleSelect(f.filename);}else{plyFromLib(f.filename,f.title||f.filename,f.artist||'');}};
  var isFav=favSet.has(f.filename);
  var art='/api/cover/'+encodeURIComponent(f.filename);
  var fn=esc(f.filename),tt=esc(f.title||f.filename),ar=esc(f.artist||''),al=esc(f.album||'');
  var dateStr=fmtDate(f.mtime);
  d.innerHTML=
    /* col 1 — number + play icon + checkbox */
    '<div class="lrow-num">'
      +'<div class="lcard-check">&#10003;</div>'
      +'<span class="lrow-idx">'+(i+1)+'</span>'
      +'<span class="lrow-play-ico">'+ico('play',13)+'</span>'
    +'</div>'
    /* col 2 — cover + title + artist */
    +'<div class="lrow-main">'
      +'<div class="la"><img src="'+art+'" onerror="this.parentNode.innerHTML=\'<div class=la-ph>\'+ico(\'note\',16)+\'</div>\'"></div>'
      +'<div class="lrow-title-wrap">'
        +'<div class="lrow-t" title="'+tt+'">'+tt+'</div>'
        +(f.artist?'<div class="lrow-ar">'+ar+'</div>':'')
      +'</div>'
    +'</div>'
    /* col 3 — album */
    +'<div class="lrow-album">'+al+'</div>'
    /* col 4 — date */
    +'<div class="lrow-date">'+dateStr+'</div>'
    /* col 5 — duration */
    +'<div class="lrow-dur">'+esc(f.duration||'—')+'</div>'
    /* col 6 — actions */
    +'<div class="lrow-act">'
      +'<button class="lcb lcb-pl" title="Ajouter à une playlist" onclick="event.stopPropagation();showPopup(event,\''+fn+'\')">'+ico('plus',13)+'</button>'
      +'<button class="lcb lcb-fav'+(isFav?' on':'')+'" title="Favori" onclick="event.stopPropagation();toggleFav(\''+fn+'\',this)">'+(isFav?ICO_HEART_F:ICO_HEART_E)+'</button>'
      +'<button class="lcb lcb-del" title="Supprimer" onclick="event.stopPropagation();delFile(\''+fn+'\')">'+ico('trash',13)+'</button>'
    +'</div>';
  return d;
}

/* FAVORIS */
function toggleFav(fn,ico){
  fetch('/api/favorites/toggle/'+encodeURIComponent(fn),{method:'POST'}).then(function(r){return r.json()}).then(function(r){
    if(r.added){favSet.add(fn);ico.innerHTML=ICO_HEART_F;ico.classList.add('on');}
    else{favSet.delete(fn);ico.innerHTML=ICO_HEART_E;ico.classList.remove('on');}
    if(favOn)renderLib();
  });
}
function toggleFavFilter(){favOn=!favOn;document.getElementById('favBtn').classList.toggle('on',favOn);renderLib();}

/* SELECTION MULTIPLE */
function toggleSelectMode(){
  selectMode=!selectMode;selectedFiles.clear();
  var grid=document.getElementById('lgrid');
  grid.classList.toggle('select-mode',selectMode);
  Array.from(grid.querySelectorAll('.lcard')).forEach(function(c){c.classList.remove('selected')});
  var btn=document.getElementById('selbtn');btn.classList.toggle('on',selectMode);
  btn.innerHTML=selectMode?ico('x',13)+' Quitter':ico('box',13)+' Selectionner';
  updateSelUI();
}
function toggleSelect(fn){
  if(selectedFiles.has(fn))selectedFiles.delete(fn);else selectedFiles.add(fn);
  var c=document.getElementById('lc-'+fn);if(c)c.classList.toggle('selected',selectedFiles.has(fn));
  updateSelUI();
}
function updateSelUI(){
  var n=selectedFiles.size;document.getElementById('selCount').textContent=n;
  document.getElementById('delSelBtn').style.display=(selectMode&&n>0)?'inline-flex':'none';
}
function deleteSelected(){
  if(!selectedFiles.size)return;var n=selectedFiles.size;
  showConfirm(
    n+' musique'+(n>1?'s':'')+' '+(n>1?'seront':'sera')+' supprimée'+(n>1?'s':'')+'.',
    function(){
      var fns=Array.from(selectedFiles),done=0;
      fns.forEach(function(fn){
        fetch('/api/delete/'+encodeURIComponent(fn),{method:'DELETE'}).then(function(r){return r.json()}).then(function(r){
          if(r.ok){var c=document.getElementById('lc-'+fn);if(c)c.remove();}
          if(++done===fns.length){
            selectedFiles.clear();
            if(selectMode)toggleSelectMode();
            loadLib();toast(n+' supprimé'+(n>1?'s':''));
          }
        });
      });
    }
  );
}
function openFolder(){fetch('/api/openfolder')}
function delFile(fn){
  if(selectMode)return;
  var title=fn.replace(/\.mp3$/i,'');
  showConfirm('"'+title+'" sera définitivement supprimé.',function(){
    fetch('/api/delete/'+encodeURIComponent(fn),{method:'DELETE'}).then(function(r){return r.json()}).then(function(r){if(r.ok){var c=document.getElementById('lc-'+fn);if(c)c.remove();toast('Supprimé.');loadLib();}});
  });
}

/* PLAYLISTS */
function loadPlaylists(){
  fetch('/api/playlists').then(function(r){return r.json()}).then(function(pls){
    playlists=pls;renderPlSide();
    if(curPl&&playlists[curPl])renderPlDetail(curPl);
    else document.getElementById('pl-detail').innerHTML='<div class="pl-empty">Sélectionnez ou créez une playlist</div>';
  });
}
function mkPlCov(files){
  if(!files.length)return '<div class="pl-item-ico">'+ico('note',15)+'</div>';
  if(files.length===1)return '<div class="pl-item-cov c1"><img src="/api/cover/'+encodeURIComponent(files[0])+'" onerror="this.style.display=\'none\'"></div>';
  /* 2+ tracks : grille 2×2 avec toutes les covers disponibles (max 4) */
  return '<div class="pl-item-cov">'+files.slice(0,4).map(function(fn){return '<img src="/api/cover/'+encodeURIComponent(fn)+'" onerror="this.style.display=\'none\'">';}).join('')+'</div>';
}
function renderPlSide(){
  var list=document.getElementById('pl-list');list.innerHTML='';
  var names=Object.keys(playlists);
  if(!names.length){list.innerHTML='<div style="padding:16px 12px;font-size:12px;color:#334155">Aucune playlist</div>';return;}
  var durMap={};allLibFiles.forEach(function(f){durMap[f.filename]=f.duration||'';});
  names.forEach(function(name){
    var files=playlists[name];
    var el=document.createElement('div');el.className='pl-item'+(curPl===name?' on':'');
    /* duration sum */
    var totalSec=0;
    files.forEach(function(fn){var d=durMap[fn]||'';if(!d)return;var p=d.split(':').map(Number);if(p.length===2)totalSec+=p[0]*60+p[1];else if(p.length===3)totalSec+=p[0]*3600+p[1]*60+p[2];});
    var durStr='';
    if(totalSec>0){var h=Math.floor(totalSec/3600),mn=Math.floor((totalSec%3600)/60);durStr=h>0?(h+' h '+mn+' min'):(mn>0?mn+' min':(totalSec+' s'));}
    /* now-playing bars */
    var isActive=curPl===name&&plyFavFn&&files.indexOf(plyFavFn)>=0;
    var isPlaying=isActive&&!aud.paused;
    var nowHtml='';
    if(isActive)nowHtml='<div class="pl-now-ico'+(isPlaying?' playing':' paused')+'"><i></i><i></i><i></i></div>';
    el.innerHTML=mkPlCov(files)
      +'<div class="pl-item-meta"><div class="pl-item-name">'+esc(name)+'</div>'+(durStr?'<div class="pl-item-dur">'+durStr+'</div>':'')+'</div>'
      +'<div class="pl-item-right">'+nowHtml+'<span class="pl-item-cnt">'+files.length+'</span></div>'
      +'<button class="pl-ren" onclick="event.stopPropagation();renamePlaylist(\''+esc(name)+'\')" title="Renommer">&#9998;</button>'
      +'<button class="pl-del" onclick="event.stopPropagation();delPl(\''+esc(name)+'\')">'+ico('x',12)+'</button>';
    el.onclick=function(){curPl=name;renderPlSide();renderPlDetail(name);};
    list.appendChild(el);
  });
}
function renderPlDetail(name){
  var files=playlists[name]||[];
  var det=document.getElementById('pl-detail');
  /* metadata lookup */
  var libMap={};
  allLibFiles.forEach(function(f){libMap[f.filename]=f;});
  /* total duration */
  var totalSec=0;
  files.forEach(function(fn){
    var m=libMap[fn];
    if(m&&m.duration){var p=m.duration.split(':');if(p.length===2)totalSec+=parseInt(p[0]||0)*60+parseInt(p[1]||0);}
  });
  var durStr='';
  if(totalSec>0){var h=Math.floor(totalSec/3600),mn=Math.floor((totalSec%3600)/60);durStr=h>0?h+' hr '+mn+' min':mn+' min';}
  /* cover collage */
  var covHtml='';
  var n=files.length;
  if(!n){
    covHtml='<div class="pl-hero-cov" style="display:flex;align-items:center;justify-content:center">'+ico('note',40)+'</div>';
  }else if(n===1){
    covHtml='<div class="pl-hero-cov single"><img src="/api/cover/'+encodeURIComponent(files[0])+'" onerror="this.parentNode.style.background=\'#1e1e50\'"></div>';
  }else{
    var show=files.slice(0,4);
    covHtml='<div class="pl-hero-cov">'
      +show.map(function(fn,i){
        /* 3 tracks : le 3e span 2 colonnes pour remplir la rangée du bas */
        var extra=(n===3&&i===2)?' style="grid-column:span 2"':'';
        return '<img src="/api/cover/'+encodeURIComponent(fn)+'"'+extra+' onerror="this.style.display=\'none\'">';
      }).join('')
      +'</div>';
  }
  /* back button */
  var backBtn='<button class="pl-back-btn" id="pl-back-btn" onclick="plGoBack()">'
    +'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5"/><path d="m12 5-7 7 7 7"/></svg>'
    +' Playlists</button>';
  /* hero */
  var firstCov=files.length?'/api/cover/'+encodeURIComponent(files[0]):'';
  var heroHtml='<div class="pl-hero">'
    +'<div class="pl-hero-bg"></div>'
    +(firstCov?'<div class="pl-hero-bg-img" style="background-image:url(\''+firstCov+'\')"></div>':'')
    +'<div class="pl-hero-fade"></div>'
    +backBtn
    +covHtml
    +'<div class="pl-hero-info">'
    +  '<div class="pl-hero-label">Playlist</div>'
    +  '<div class="pl-hero-name">'+esc(name)+'</div>'
    +  '<div class="pl-hero-meta">'
    +    (files.length?'<strong>'+files.length+'</strong> titre'+(files.length>1?'s':''):'<em style="font-style:normal;opacity:.5">Vide</em>')
    +    (durStr?' &nbsp;·&nbsp; '+durStr:'')
    +  '</div>'
    +'</div>'
    +'</div>';
  /* controls */
  var ctrlHtml=files.length?(
    '<div class="pl-ctrl">'
    +'<button class="pl-btn-play" onclick="plyFromPl(\''+esc(name)+'\',0)" title="Tout lire">'+ico('play',22)+'</button>'
    +'<button class="pl-ctrl-ico" onclick="plyFromPlShuffle(\''+esc(name)+'\')" title="Aleatoire">'+ico('shuffle',18)+'</button>'
    +'<div class="pl-ctrl-cnt">'+files.length+' titre'+(files.length>1?'s':'')+(durStr?' &nbsp;·&nbsp; '+durStr:'')+'</div>'
    +'</div>'
  ):'';
  /* table header */
  var tblHd=files.length?(
    '<div class="pl-tbl-hd">'
    +'<span style="text-align:center">#</span>'
    +'<span>TITRE</span>'
    +'<span style="text-align:right">DURÉE</span>'
    +'<span></span>'
    +'</div>'
  ):'';
  /* song rows */
  var rows=files.map(function(fn,i){
    var meta=libMap[fn]||{};
    var t=meta.title||fn.replace(/\.mp3$/i,'');
    var ar=meta.artist||'';
    var dur=meta.duration||'';
    var delay=Math.min(i*.028,.5);
    return '<div class="pl-song" draggable="true" ondragstart="plDrgS('+i+',event)" ondragover="plDrgO(this,event)" ondrop="plDrpD(this,\''+esc(name)+'\','+i+',event)" ondragleave="this.classList.remove(\'dg-over\')" onclick="plyFromPl(\''+esc(name)+'\','+i+')" style="animation-delay:'+delay+'s">'
      +'<div class="pl-song-idx">'
      +  '<span class="pl-idx-num">'+(i+1)+'</span>'
      +  '<span class="pl-idx-ico">'+ico('play',11)+'</span>'
      +'</div>'
      +'<div class="pl-song-cell">'
      +  '<div class="pl-song-art"><img src="/api/cover/'+encodeURIComponent(fn)+'" onerror="this.style.display=\'none\'"></div>'
      +  '<div class="pl-song-info">'
      +    '<div class="pl-song-t">'+esc(t)+'</div>'
      +    (ar?'<div class="pl-song-m">'+esc(ar)+'</div>':'')
      +  '</div>'
      +'</div>'
      +'<div class="pl-song-dur">'+esc(dur)+'</div>'
      +'<div style="display:flex;align-items:center;justify-content:center">'
      +  '<button class="pl-song-rm" onclick="event.stopPropagation();rmPlSong(\''+esc(name)+'\',\''+esc(fn)+'\')" title="Retirer">&#215;</button>'
      +'</div>'
      +'</div>';
  }).join('');
  det.innerHTML=heroHtml+ctrlHtml
    +'<div class="pl-songs">'+tblHd
    +(rows||'<div class="pl-empty">Playlist vide — ajoutez des musiques depuis la Bibliothèque</div>')
    +'</div>';
  /* show back btn on mobile, keep on desktop too for convenience */
  var bb=document.getElementById('pl-back-btn');
  if(bb)bb.style.display='flex';
  if(window.innerWidth<=640){
    document.querySelector('.pl-wrap').classList.add('in-detail');
  }
}
function plyFromPlShuffle(name){
  var files=playlists[name]||[];
  if(!files.length)return;
  plyFromPl(name,Math.floor(Math.random()*files.length));
}
function plGoBack(){
  document.querySelector('.pl-wrap').classList.remove('in-detail');
}
function createPlaylist(){
  showInput('Nouvelle playlist','Nom de la playlist…','Créer',function(name){
    fetch('/api/playlists/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})}).then(function(){loadPlaylists();toast('Playlist créée !');});
  });
}
function delPl(name){
  showConfirm('Supprimer la playlist "'+name+'" ?',function(){
    fetch('/api/playlists/'+encodeURIComponent(name),{method:'DELETE'}).then(function(){
      if(curPl===name){
        curPl=null;
        document.querySelector('.pl-wrap').classList.remove('in-detail');
        document.getElementById('pl-detail').innerHTML='<div class="pl-empty">Sélectionnez ou créez une playlist</div>';
      }
      loadPlaylists();toast('Playlist supprimée');
    });
  });
}
function renamePlaylist(name){
  showInput('Renommer la playlist','Nouveau nom…','Renommer',function(newName){
    if(!newName||newName===name)return;
    fetch('/api/playlists/'+encodeURIComponent(name)+'/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_name:newName})})
      .then(function(r){return r.json();}).then(function(d){
        if(d.error){toast('Erreur : '+d.error);return;}
        if(curPl===name)curPl=newName;
        loadPlaylists();toast('Playlist renommée !');
      });
  });
}
/* Drag-and-drop track reorder */
var _dragIdx=null;
function plDrgS(i,ev){_dragIdx=i;ev.dataTransfer.effectAllowed='move';}
function plDrgO(el,ev){ev.preventDefault();ev.dataTransfer.dropEffect='move';document.querySelectorAll('.pl-song.dg-over').forEach(function(e){e.classList.remove('dg-over');});el.classList.add('dg-over');}
function plDrpD(el,plName,toIdx,ev){
  ev.preventDefault();el.classList.remove('dg-over');
  if(_dragIdx===null||_dragIdx===toIdx){_dragIdx=null;return;}
  var arr=playlists[plName].slice();
  arr.splice(toIdx,0,arr.splice(_dragIdx,1)[0]);
  playlists[plName]=arr;_dragIdx=null;
  renderPlDetail(plName);
  fetch('/api/playlists/'+encodeURIComponent(plName)+'/reorder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order:arr})});
}
function rmPlSong(plName,fn){
  fetch('/api/playlists/'+encodeURIComponent(plName)+'/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:fn})}).then(function(){loadPlaylists();if(curPl===plName)renderPlDetail(plName);});
}

/* POPUP AJOUT PLAYLIST */
var popupFn='';
function showPopup(e,fn){
  popupFn=fn;
  var pop=document.getElementById('pl-popup');
  var bd=document.getElementById('pl-backdrop');
  fetch('/api/playlists').then(function(r){return r.json()}).then(function(pls){
    var isMobile=window.innerWidth<=640;
    var handle=isMobile?'<div style="width:36px;height:4px;background:rgba(255,255,255,.14);border-radius:4px;margin:12px auto 14px"></div>':'';
    var html=handle;
    html+=Object.keys(pls).map(function(n){return '<div class="pp-item" onclick="addToPl(\''+esc(n)+'\')">'+ico('note',13)+' '+esc(n)+'</div>';}).join('');
    html+='<div class="pp-item pp-new" onclick="newAndAdd()">+ Nouvelle playlist</div>';
    pop.innerHTML=html;pop.classList.add('show');
    if(isMobile){
      pop.style.left='';pop.style.top='';
      if(bd)bd.classList.add('show');
    } else {
      var rect=e.currentTarget.getBoundingClientRect();
      pop.style.left=Math.min(rect.left,window.innerWidth-200)+'px';
      pop.style.top=rect.bottom+'px';
    }
    e.stopPropagation();
  });
}
document.addEventListener('click',function(){
  document.getElementById('pl-popup').classList.remove('show');
  var bd=document.getElementById('pl-backdrop');if(bd)bd.classList.remove('show');
});
function addToPl(name){
  if(!popupFn)return;
  fetch('/api/playlists/'+encodeURIComponent(name)+'/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:popupFn})}).then(function(){toast('Ajoute a : '+name);loadPlaylists();});
  document.getElementById('pl-popup').classList.remove('show');
}
function newAndAdd(){
  document.getElementById('pl-popup').classList.remove('show');
  var bd=document.getElementById('pl-backdrop');if(bd)bd.classList.remove('show');
  showInput('Nouvelle playlist','Nom de la playlist…','Créer',function(name){
    fetch('/api/playlists/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})})
      .then(function(){return fetch('/api/playlists/'+encodeURIComponent(name)+'/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:popupFn})});})
      .then(function(){toast('Ajouté à : '+name);loadPlaylists();});
  });
}

/* LECTEUR PRO */
var plyShuffle=false,plyRepeat=false,plyFavFn='',npOpen=false;
var plyDragging=false,plyVolDragging=false,npDragging=false;
var PLY_PLAY_ICO='<path d="M8 5v14l11-7z"/>',PLY_PAUSE_ICO='<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
var VOL_ON='<path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/><path d="M14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>';
var VOL_OFF='<path d="M16.5 12A4.5 4.5 0 0 0 14 7.97v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.796 8.796 0 0 0 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06A8.99 8.99 0 0 0 17.73 18L19 19.27 20.27 18 5.27 3 4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>';

function plyFromLib(fn,title,artist){
  var grid=document.getElementById('lgrid');
  plyQueue=Array.from(grid.querySelectorAll('.lcard')).map(function(c){return{fn:c.dataset.fn,title:(c.querySelector('.lrow-t')||{}).textContent||c.dataset.fn,artist:(c.querySelector('.lrow-ar')||{}).textContent||''};}).filter(function(x){return x.fn});
  plyIdx=plyQueue.findIndex(function(x){return x.fn===fn});
  if(plyIdx<0){plyQueue=[{fn:fn,title:title,artist:artist}];plyIdx=0;}
  plyLoad(fn,title,artist);
}
function plyFromPl(plName,idx){
  var files=playlists[plName]||[];if(!files.length)return;
  var libMap={};allLibFiles.forEach(function(f){libMap[f.filename]=f;});
  plyQueue=files.map(function(fn){var m=libMap[fn]||{};return{fn:fn,title:m.title||fn.replace(/\.mp3$/i,''),artist:m.artist||''};});
  plyIdx=idx;plyLoad(plyQueue[idx].fn,plyQueue[idx].title,plyQueue[idx].artist);
}
function plyLoad(fn,title,artist){
  plyFavFn=fn;
  /* highlight now-playing card */
  document.querySelectorAll('.lcard.now-playing').forEach(function(c){c.classList.remove('now-playing')});
  var nc=document.querySelector('.lcard[data-fn="'+fn.replace(/"/g,'&quot;')+'"]');
  if(nc)nc.classList.add('now-playing');
  aud.src='/api/stream/'+encodeURIComponent(fn);aud.play();
  var covUrl='/api/cover/'+encodeURIComponent(fn);
  var artHtml='<img src="'+covUrl+'" style="width:100%;height:100%;object-fit:cover;display:block" onerror="this.parentNode.innerHTML=\'<div class=ply-art-ph>&#9835;</div>\'">';
  /* animated title change */
  var tEl=document.getElementById('ply-title'),aEl=document.getElementById('ply-artist');
  if(tEl.textContent){tEl.classList.add('changing');aEl.classList.add('changing');setTimeout(function(){tEl.textContent=title||fn;aEl.textContent=artist||'';tEl.classList.remove('changing');aEl.classList.remove('changing');},180);}
  else{tEl.textContent=title||fn;aEl.textContent=artist||'';}
  document.getElementById('ply-art').innerHTML=artHtml;
  document.getElementById('ply-idle').style.display='none';
  var pt=document.getElementById('ply-prog-top');if(pt)pt.style.display='block';
  ['ply-left','ply-center','ply-right'].forEach(function(id){document.getElementById(id).style.visibility='visible';});
  var fb=document.getElementById('ply-fav-btn');
  if(fb){fb.className='ply-fav-btn'+(favSet.has(fn)?' on':'');fb.innerHTML=favSet.has(fn)?ICO_HEART_F:ICO_HEART_E;}
  /* update now-playing view */
  var npbg=document.getElementById('np-bg');if(npbg)npbg.style.backgroundImage='url('+covUrl+')';
  var npArt=document.getElementById('np-art');if(npArt)npArt.innerHTML=artHtml;
  var ns=document.getElementById('np-song');if(ns)ns.textContent=title||fn;
  var na=document.getElementById('np-auth');if(na)na.textContent=artist||'';
  var nfb=document.getElementById('np-fav-btn');
  if(nfb){nfb.className='np-fav'+(favSet.has(fn)?' on':'');nfb.innerHTML=favSet.has(fn)?ICO_HEART_F:ICO_HEART_E;}
  setStat('Lecture: '+title);
  updateMediaMeta(fn,title,artist);
  if(curPl)setTimeout(renderPlSide,0);
  /* Sur mobile, ouvrir directement le grand lecteur */
  if(window.innerWidth<=640 && !npOpen){
    npOpen=true;
    document.getElementById('np-view').classList.add('open');
  }
}
function plyToggle(){if(aud.paused)aud.play();else{aud.pause();if(curPl)setTimeout(renderPlSide,0);}}
function plyPrev(){
  if(aud.currentTime>5){
    /* Plus de 5s → retour au début de la track courante */
    aud.currentTime=0;return;
  }
  /* Moins de 5s → track précédente */
  if(plyShuffle&&plyQueue.length>1)plyIdx=Math.floor(Math.random()*plyQueue.length);
  else if(plyIdx>0)plyIdx--;
  else{aud.currentTime=0;return;}
  var t=plyQueue[plyIdx];plyLoad(t.fn,t.title,t.artist);
}
function plyNext(){
  if(plyRepeat){aud.currentTime=0;aud.play();return;}
  if(plyShuffle&&plyQueue.length>1)plyIdx=Math.floor(Math.random()*plyQueue.length);
  else if(plyIdx<plyQueue.length-1)plyIdx++;else return;
  var t=plyQueue[plyIdx];plyLoad(t.fn,t.title,t.artist);
}
function plyToggleShuffle(){
  plyShuffle=!plyShuffle;
  document.getElementById('ply-shuf').classList.toggle('active',plyShuffle);
  var nb=document.getElementById('np-shuf');if(nb)nb.classList.toggle('active',plyShuffle);
}
function plyToggleRepeat(){
  plyRepeat=!plyRepeat;
  document.getElementById('ply-rep').classList.toggle('active',plyRepeat);
  var nb=document.getElementById('np-rep');if(nb)nb.classList.toggle('active',plyRepeat);
}
function plyToggleFav(){
  if(!plyFavFn)return;
  fetch('/api/favorites/toggle/'+encodeURIComponent(plyFavFn),{method:'POST'}).then(function(r){return r.json();}).then(function(r){
    if(r.added)favSet.add(plyFavFn);else favSet.delete(plyFavFn);
    [['ply-fav-btn','ply-fav-btn'],['np-fav-btn','np-fav']].forEach(function(pair){
      var b=document.getElementById(pair[0]);if(!b)return;
      b.className=pair[1]+(r.added?' on':'');b.innerHTML=r.added?ICO_HEART_F:ICO_HEART_E;
    });
    var lc=document.getElementById('lc-'+plyFavFn);
    if(lc){var favIco=lc.querySelector('.lcb-fav')||lc.querySelector('.fav-ico');if(favIco){favIco.className=(favIco.classList.contains('lcb-fav')?'lcb lcb-fav':'fav-ico')+(r.added?' on':'');favIco.innerHTML=r.added?ICO_HEART_F:ICO_HEART_E;}}
    toast(r.added?'Ajouté aux favoris':'Retiré des favoris');
  });
}
function plyMute(){aud.muted=!aud.muted;var ico=aud.muted?VOL_OFF:VOL_ON;document.getElementById('ply-vol-svg').innerHTML=ico;var ns=document.getElementById('np-vol-svg');if(ns)ns.innerHTML=ico;var pf=document.getElementById('ply-vol-f');if(pf)pf.style.width=aud.muted?'0%':(aud.volume*100)+'%';var nf=document.getElementById('np-vol-fill');if(nf)nf.style.width=aud.muted?'0%':(aud.volume*100)+'%';}
function fmtT(s){s=Math.floor(s||0);var m=Math.floor(s/60),sec=s%60;return m+':'+(sec<10?'0':'')+sec;}
/* NOW PLAYING VIEW */
function toggleNowPlaying(){if(!plyFavFn)return;npOpen=!npOpen;document.getElementById('np-view').classList.toggle('open',npOpen);}
function closeNp(){npOpen=false;document.getElementById('np-view').classList.remove('open');}
/* Drag — combined handler */
var plyBar=document.getElementById('ply-bar');
var plyVolTrack=document.getElementById('ply-vol-track');
var npVolTrack=document.getElementById('np-vol-track');
var _activeVolTrack=null;
function posIn(e,el){var r=el.getBoundingClientRect();return Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));}
if(plyBar)plyBar.addEventListener('mousedown',function(e){plyDragging=true;if(aud.duration)aud.currentTime=posIn(e,plyBar)*aud.duration;e.preventDefault();});
if(plyVolTrack)plyVolTrack.addEventListener('mousedown',function(e){
  plyVolDragging=true;_activeVolTrack=plyVolTrack;setVolUI(posIn(e,plyVolTrack));e.preventDefault();
});
if(npVolTrack)npVolTrack.addEventListener('mousedown',function(e){
  plyVolDragging=true;_activeVolTrack=npVolTrack;setVolUI(posIn(e,npVolTrack));e.preventDefault();
});
document.addEventListener('mousedown',function(e){
  var nt=document.getElementById('np-track');
  if(nt&&nt.contains(e.target)){npDragging=true;var p=posIn(e,nt);document.getElementById('np-fill').style.width=(p*100)+'%';if(aud.duration)aud.currentTime=p*aud.duration;e.preventDefault();}
});
document.addEventListener('mousemove',function(e){
  if(plyDragging&&plyBar){var p=posIn(e,plyBar);document.getElementById('ply-bar-f').style.width=(p*100)+'%';if(aud.duration)aud.currentTime=p*aud.duration;}
  if(npDragging){var nt=document.getElementById('np-track');if(nt){var p=posIn(e,nt);document.getElementById('np-fill').style.width=(p*100)+'%';if(aud.duration)aud.currentTime=p*aud.duration;}}
  if(plyVolDragging&&_activeVolTrack){setVolUI(posIn(e,_activeVolTrack));}
});
document.addEventListener('mouseup',function(){plyDragging=false;npDragging=false;plyVolDragging=false;});
aud.addEventListener('timeupdate',function(){
  if(!aud.duration)return;
  var p=(aud.currentTime/aud.duration)*100,tc=fmtT(aud.currentTime),td=fmtT(aud.duration);
  if(!plyDragging){document.getElementById('ply-bar-f').style.width=p+'%';document.getElementById('ply-cur').textContent=tc;document.getElementById('ply-dur').textContent=td;}
  if(!npDragging){var nf=document.getElementById('np-fill');if(nf)nf.style.width=p+'%';var nc=document.getElementById('np-cur');if(nc)nc.textContent=tc;var nd=document.getElementById('np-dur');if(nd)nd.textContent=td;}
  var ptf=document.getElementById('ply-prog-top-f');if(ptf)ptf.style.width=p+'%';
  if('mediaSession' in navigator&&navigator.setPositionState){try{navigator.mediaSession.setPositionState({duration:aud.duration,playbackRate:aud.playbackRate||1,position:aud.currentTime});}catch(e){}}
});
function seekFromTop(e){
  var bar=document.getElementById('ply-prog-top');
  if(!bar||!aud.duration)return;
  var r=bar.getBoundingClientRect();
  var p=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
  aud.currentTime=p*aud.duration;
  document.getElementById('ply-prog-top-f').style.width=(p*100)+'%';
}
aud.addEventListener('ended',function(){plyNext();});
aud.addEventListener('pause',function(){
  document.getElementById('ply-play-ico').innerHTML=PLY_PLAY_ICO;
  document.getElementById('player').classList.remove('playing');
  var np=document.getElementById('np-play-ico');if(np)np.innerHTML=PLY_PLAY_ICO;
  if('mediaSession' in navigator)navigator.mediaSession.playbackState='paused';
});
aud.addEventListener('play',function(){
  document.getElementById('ply-play-ico').innerHTML=PLY_PAUSE_ICO;
  document.getElementById('player').classList.add('playing');
  var np=document.getElementById('np-play-ico');if(np)np.innerHTML=PLY_PAUSE_ICO;
  if('mediaSession' in navigator)navigator.mediaSession.playbackState='playing';
});

/* TOUCH SUPPORT */
function addTouchBar(el,cb){
  if(!el)return;
  function handle(e){var t=e.touches[0];var r=el.getBoundingClientRect();cb(Math.max(0,Math.min(1,(t.clientX-r.left)/r.width)));e.preventDefault();}
  el.addEventListener('touchstart',handle,{passive:false});
  el.addEventListener('touchmove',handle,{passive:false});
}
addTouchBar(document.getElementById('ply-bar'),function(p){document.getElementById('ply-bar-f').style.width=(p*100)+'%';if(aud.duration)aud.currentTime=p*aud.duration;});
addTouchBar(document.getElementById('ply-vol-track'),function(p){setVolUI(p);});
addTouchBar(document.getElementById('np-track'),function(p){document.getElementById('np-fill').style.width=(p*100)+'%';if(aud.duration)aud.currentTime=p*aud.duration;});
addTouchBar(document.getElementById('np-vol-track'),function(p){setVolUI(p);});
/* swipe down sur np-view → ferme le lecteur */
(function(){
  var sy=0,sx=0;
  var nv=document.getElementById('np-view');
  if(!nv)return;
  nv.addEventListener('touchstart',function(e){sy=e.touches[0].clientY;sx=e.touches[0].clientX;},{passive:true});
  nv.addEventListener('touchend',function(e){
    var dy=e.changedTouches[0].clientY-sy;
    var dx=Math.abs(e.changedTouches[0].clientX-sx);
    if(dy>75&&dx<60)closeNp();
  },{passive:true});
})();

/* Effet rebond sur les boutons du lecteur */
(function(){
  var sel='.ply-btn,.ply-btn-main,.nc-btn,.nc-play,.nv-ico,.np-chevron,.np-close';
  document.addEventListener('click',function(e){
    var b=e.target.closest(sel);
    if(!b)return;
    b.classList.remove('btn-clicked');
    void b.offsetWidth;
    b.classList.add('btn-clicked');
  });
  document.addEventListener('animationend',function(e){
    if(e.animationName==='btnBounce')e.target.classList.remove('btn-clicked');
  });
})();

/* swipe horizontal → changer d'onglet (mobile) */
(function(){
  var pages=document.querySelector('.pages');
  if(!pages)return;
  var sx=0,sy=0,dx=0,dragging=false,locked=false;

  function getCurTab(){
    for(var i=0;i<4;i++){if(document.getElementById('tab'+i).classList.contains('on'))return i;}
    return 0;
  }

  pages.addEventListener('touchstart',function(e){
    sx=e.touches[0].clientX;sy=e.touches[0].clientY;
    dx=0;dragging=false;locked=false;
  },{passive:true});

  pages.addEventListener('touchmove',function(e){
    var cx=e.touches[0].clientX,cy=e.touches[0].clientY;
    dx=cx-sx;
    if(!locked){
      if(Math.abs(dx)>Math.abs(cy-sy)+6){dragging=true;locked=true;}
      else if(Math.abs(cy-sy)>Math.abs(dx)+6){locked=true;}
    }
  },{passive:true});

  pages.addEventListener('touchend',function(){
    if(!dragging||Math.abs(dx)<58){dx=0;dragging=false;return;}
    var cur=getCurTab();
    if(dx<0&&cur<3)goTab(cur+1);
    else if(dx>0&&cur>0)goTab(cur-1);
    dx=0;dragging=false;
  },{passive:true});
})();

/* UTILS */
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
function setStat(m){document.getElementById('smsg').textContent=m;}
function setRight(m){document.getElementById('srt').textContent=m;}
var _tt;
function toast(msg){var el=document.getElementById('toast');el.innerHTML=msg;el.classList.add('show');clearTimeout(_tt);_tt=setTimeout(function(){el.classList.remove('show');},3500);}

/* ── ONLINE / OFFLINE ── */
function updateNetStatus(forceOnline){
  var online = forceOnline !== undefined ? forceOnline : navigator.onLine;
  document.body.classList.toggle('is-offline', !online);
  var b=document.getElementById('net-badge'), l=document.getElementById('net-lbl');
  if(b) b.className='net-badge '+(online?'on':'off');
  if(l) l.textContent=online?'En ligne':'Hors-ligne';
}
function checkConnection(){
  var btn=document.getElementById('offl-retry');
  if(btn){btn.classList.add('spin');btn.disabled=true;}
  fetch('/api/ping').then(function(r){return r.json();}).then(function(d){
    if(btn){btn.classList.remove('spin');btn.disabled=false;}
    if(d.online){updateNetStatus(true);toast('Connexion rétablie');}
    else{toast('Toujours hors-ligne');}
  }).catch(function(){
    if(btn){btn.classList.remove('spin');btn.disabled=false;}
    toast('Toujours hors-ligne');
  });
}
window.addEventListener('online', function(){updateNetStatus(true); toast('Connexion rétablie');});
window.addEventListener('offline',function(){updateNetStatus(false);toast('Mode hors-ligne — lecture locale disponible');});
updateNetStatus();

/* ── SPLASH ── */
(function(){
  setTimeout(function(){
    var sp=document.getElementById('splash');
    if(!sp)return;
    sp.classList.add('sp-exit');
    setTimeout(function(){if(sp.parentNode)sp.parentNode.removeChild(sp);},540);
  },3500);
})();

/* CUSTOM INPUT MODAL */
var _inpResolve=null;
function showInput(title,placeholder,okLabel,onOk){
  document.getElementById('inp-title').textContent=title;
  var f=document.getElementById('inp-field');f.value='';f.placeholder=placeholder||'';
  document.getElementById('inp-overlay').classList.add('show');
  var okBtn=document.querySelector('.inp-ok');okBtn.textContent=okLabel||'OK';
  _inpResolve=onOk;
  setTimeout(function(){f.focus();},120);
}
function inpAccept(){
  var val=document.getElementById('inp-field').value.trim();
  document.getElementById('inp-overlay').classList.remove('show');
  if(_inpResolve&&val){var fn=_inpResolve;_inpResolve=null;fn(val);}
  else _inpResolve=null;
}
function inpReject(){document.getElementById('inp-overlay').classList.remove('show');_inpResolve=null;}

/* CUSTOM CONFIRM DIALOG */
var _dlgResolve=null;
function showConfirm(msg,onYes){
  document.getElementById('dlg-msg').textContent=msg;
  var ov=document.getElementById('dlg-overlay');
  ov.classList.add('show');
  _dlgResolve=onYes;
  document.getElementById('dlg-confirm-btn').onclick=function(){dlgAccept();};
}
function dlgAccept(){
  document.getElementById('dlg-overlay').classList.remove('show');
  if(_dlgResolve){var fn=_dlgResolve;_dlgResolve=null;fn();}
}
function dlgReject(){document.getElementById('dlg-overlay').classList.remove('show');_dlgResolve=null;}
function dlgClose(e){if(e.target===document.getElementById('dlg-overlay'))dlgReject();}

/* KEYBOARD SHORTCUTS */
document.addEventListener('keydown',function(e){
  var tag=document.activeElement.tagName;
  if(tag==='INPUT'||tag==='TEXTAREA')return;
  if(e.key===' '||e.code==='Space'){e.preventDefault();if(plyFavFn)plyToggle();}
  else if(e.key==='ArrowLeft' &&!e.shiftKey){e.preventDefault();if(plyFavFn)plyPrev();}
  else if(e.key==='ArrowRight'&&!e.shiftKey){e.preventDefault();if(plyFavFn)plyNext();}
  else if(e.key==='m'||e.key==='M'){if(plyFavFn)plyMute();}
  else if(e.key==='f'||e.key==='F'){if(plyFavFn)plyToggleFav();}
  else if(e.key==='ArrowUp'){e.preventDefault();aud.volume=Math.min(1,aud.volume+.05);setVolUI(aud.volume);}
  else if(e.key==='ArrowDown'){e.preventDefault();aud.volume=Math.max(0,aud.volume-.05);setVolUI(aud.volume);}
});

/* CHECK FOR UPDATE */
(function(){
  var CURRENT='__VER__';
  var _ready=false;
  function parseVer(v){return v.replace(/^v/,'').split('.').map(Number);}
  function isNewer(a,b){for(var i=0;i<3;i++){if((a[i]||0)>(b[i]||0))return true;if((a[i]||0)<(b[i]||0))return false;}return false;}
  function showBanner(ver){
    document.getElementById('upd-ver').textContent=ver;
    document.getElementById('upd-banner').style.display='flex';
  }
  function showProgress(pct){
    document.getElementById('upd-prog').style.display='flex';
    document.getElementById('upd-pfill').style.width=pct+'%';
    document.getElementById('upd-plbl').textContent=pct+'%';
    document.getElementById('upd-btn').style.display='none';
    document.getElementById('upd-msg').innerHTML='Téléchargement en cours…';
  }
  function showReady(ver){
    _ready=true;
    document.getElementById('upd-prog').style.display='none';
    document.getElementById('upd-msg').innerHTML='Prêt à installer : <strong>'+ver+'</strong>';
    var btn=document.getElementById('upd-btn');
    btn.style.display='';btn.textContent='Redémarrer et installer';
    document.getElementById('upd-banner').style.display='flex';
  }
  window.updAction=function(){
    if(!window.electronUpdater){window.open('https://github.com/Advm000/musicdl/releases/latest','_blank');return;}
    if(_ready)window.electronUpdater.install();
    /* sinon téléchargement en cours — bouton caché, rien à faire */
  };
  /* Electron path — electron-updater envoie les événements via IPC */
  if(window.electronUpdater){
    window.electronUpdater.onUpdate(function(d){
      if(d.type==='available'){showBanner(d.version);}
      else if(d.type==='progress'){showProgress(d.percent);}
      else if(d.type==='ready'){showReady(d.version);}
    });
    return; /* main.js lance checkForUpdates() au démarrage */
  }
  /* Fallback navigateur — GitHub API */
  setTimeout(function(){
    fetch('https://api.github.com/repos/Advm000/musicdl/releases/latest',{headers:{'Accept':'application/vnd.github.v3+json'}})
      .then(function(r){return r.json();})
      .then(function(d){
        if(!d||!d.tag_name)return;
        if(isNewer(parseVer(d.tag_name),parseVer(CURRENT)))showBanner(d.tag_name);
      }).catch(function(){});
  },4000);
})();
</script>
</body>
</html>"""
# ── MARQUEUR FIN HTML ──────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES SUPPLÉMENTAIRES
# ══════════════════════════════════════════════════════════════════════════════

def _make_icon_png(size=192):
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)
    ihdr = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    rows = []
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(0x7c + (0x06 - 0x7c) * t)
        g = int(0x3a + (0xb6 - 0x3a) * t)
        b = int(0xed + (0xd4 - 0xed) * t)
        rows.append(bytes([0] + [r, g, b] * size))
    idat = zlib.compress(b''.join(rows), 9)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')

@app.route("/icon-192.png")
def icon_192():
    return Response(_make_icon_png(192), mimetype='image/png',
                    headers={'Cache-Control': 'public,max-age=86400'})

@app.route("/icon-512.png")
def icon_512():
    return Response(_make_icon_png(512), mimetype='image/png',
                    headers={'Cache-Control': 'public,max-age=86400'})

@app.route("/icon.svg")
def app_icon():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="512" y2="512" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#7c3aed"/><stop offset="100%" stop-color="#0891b2"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="112" fill="url(#g)"/>
  <rect x="60" y="292" width="80" height="160" rx="40" fill="white" opacity=".92"/>
  <rect x="182" y="196" width="80" height="256" rx="40" fill="white"/>
  <rect x="304" y="242" width="80" height="210" rx="40" fill="white" opacity=".88"/>
  <rect x="394" y="78" width="56" height="185" rx="28" fill="white"/>
  <polygon points="364,238 420,318 476,238" fill="white"/>
</svg>'''
    from flask import Response
    return Response(svg, mimetype='image/svg+xml', headers={'Cache-Control':'public,max-age=86400'})

@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "Music DL",
        "short_name": "Music DL",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#06061a",
        "theme_color": "#7c3aed",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon.svg",     "sizes": "any",     "type": "image/svg+xml", "purpose": "any"}
        ]
    })

@app.route("/")
def index():
    return HTML.replace("__VER__", APP_VERSION)

@app.route("/api/open/<path:filename>")
def api_open(filename):
    try:   os.startfile(os.path.join(OUT_DIR, filename))
    except Exception: pass
    return "", 204

@app.route("/api/openfolder")
def api_openfolder():
    try:   os.startfile(OUT_DIR)
    except Exception: pass
    return "", 204


# ══════════════════════════════════════════════════════════════════════════════
# LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    IS_FROZEN = getattr(sys, 'frozen', False)   # True quand lancé via PyInstaller
    PORT = 5000
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "127.0.0.1"
    if not IS_FROZEN:
        print(f"\n  Music Downloader v{APP_VERSION}")
        print(f"  Device  : {DEVICE_INFO.get('hostname','?')}  [{DEVICE_INFO.get('device_id','?')[:8]}...]")
        print(f"  PC      -> http://localhost:{PORT}")
        print(f"  Reseau  -> http://{local_ip}:{PORT}  (telephone sur le meme WiFi)\n")
    NO_BROWSER = '--no-browser' in sys.argv
    delay = 1.5 if IS_FROZEN else 1.0
    if not NO_BROWSER:
        threading.Timer(delay, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True, use_reloader=False)
