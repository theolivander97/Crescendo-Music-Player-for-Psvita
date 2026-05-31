#!/usr/bin/env python3
"""
Servidor de sincronizacion para Crescendo.

Uso:
    python sync_server.py <carpeta> [puerto]

Ejemplo:
    python sync_server.py D:\\Sync\\Crescendo 8787

Expone en LAN (HTTP plano, sin auth):
    GET  /list                  -> JSON [{"name": "...", "size": N, "mtime": T}, ...]
    GET  /file?name=<archivo>   -> bytes del archivo
    GET  /ping                  -> "ok"

Solo sirve archivos .mp3 .flac .wav .ogg (case-insensitive) del directorio dado,
sin recursion en subcarpetas.
"""

import json
import os
import sys
import time
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED_EXTS = (".mp3", ".flac", ".wav", ".ogg")

# ---------------------------------------------------------------------------
# Busqueda + descarga online (iTunes -> Spotify fallback -> SpotiFLAC)
# ---------------------------------------------------------------------------
HTTP_UA = "VitaMusic-sync/1.0"

# Credenciales opcionales de Spotify (solo para el fallback de busqueda).
# Se leen de variables de entorno o de spotify.cfg junto a este script.
SPOTIFY_ID = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()


def _load_spotify_cfg():
    """Si no hay env vars, intentar leer spotify.cfg (client_id=, client_secret=)."""
    global SPOTIFY_ID, SPOTIFY_SECRET
    if SPOTIFY_ID and SPOTIFY_SECRET:
        return
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spotify.cfg")
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip().lower(), v.strip()
                if k == "client_id":
                    SPOTIFY_ID = v
                elif k == "client_secret":
                    SPOTIFY_SECRET = v
    except OSError:
        pass


def _http_json(url, headers=None, data=None, timeout=15):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    req.add_header("User-Agent", HTTP_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def itunes_search(query, limit=20):
    """Busca canciones en iTunes. Devuelve lista de dicts uniformes."""
    q = urllib.parse.quote(query)
    url = (f"https://itunes.apple.com/search?term={q}"
           f"&entity=song&limit={limit}&media=music")
    out = []
    try:
        data = _http_json(url)
        for it in data.get("results", []):
            out.append({
                "title":    it.get("trackName", ""),
                "artist":   it.get("artistName", ""),
                "album":    it.get("collectionName", ""),
                "duration": int(it.get("trackTimeMillis", 0) // 1000),
                "url":      it.get("trackViewUrl", ""),
                "source":   "itunes",
            })
    except Exception as e:
        print(f"[search] iTunes fallo: {e}", file=sys.stderr)
    return [r for r in out if r["url"]]


# spotdl usa asyncio internamente, por eso DEBE correr siempre en un unico
# hilo dedicado con su propio event loop. Si se llama desde un hilo del
# servidor HTTP (uno por request), asyncio falla -> el server tira la conexion
# y la Vita ve "HTTP 0". Aqui usamos un worker con cola de pedidos.
import queue as _queue

_search_q = _queue.Queue()
_spotdl_ready = [False]


def _spotdl_worker():
    """Hilo dedicado: inicializa spotdl y atiende busquedas de a una."""
    try:
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass

    sp_client = None
    if SPOTIFY_ID and SPOTIFY_SECRET:
        try:
            from spotdl import Spotdl
            Spotdl(client_id=SPOTIFY_ID, client_secret=SPOTIFY_SECRET)
            # Consultamos el cliente de Spotify directamente (rapido, ~6s y
            # devuelve varios resultados). get_search_results construye objetos
            # pesados y se cuelga en este hilo, por eso NO lo usamos.
            from spotdl.utils.spotify import SpotifyClient
            sp_client = SpotifyClient()
            _spotdl_ready[0] = True
            print("[search] spotdl listo", file=sys.stderr)
        except Exception as e:
            print(f"[search] spotdl init fallo: {e}", file=sys.stderr)

    while True:
        query, holder = _search_q.get()
        out = []
        try:
            if sp_client:
                data = sp_client.search(query, type="track", limit=20)
                for it in data.get("tracks", {}).get("items", []):
                    url = it.get("external_urls", {}).get("spotify", "")
                    if not url:
                        continue
                    artists = ", ".join(a.get("name", "") for a in it.get("artists", []))
                    out.append({
                        "title":    it.get("name", ""),
                        "artist":   artists,
                        "album":    it.get("album", {}).get("name", ""),
                        "duration": int(it.get("duration_ms", 0)) // 1000,
                        "url":      url,
                        "source":   "spotify",
                    })
        except Exception as e:
            print(f"[search] spotdl_search fallo: {e}", file=sys.stderr)
        holder["res"] = out
        holder["ev"].set()


def start_search_worker():
    t = threading.Thread(target=_spotdl_worker, daemon=True)
    t.start()


def spotdl_search(query):
    """Encola la busqueda al worker y espera el resultado (max 60s)."""
    if not (SPOTIFY_ID and SPOTIFY_SECRET):
        return []
    holder = {"ev": threading.Event(), "res": []}
    _search_q.put((query, holder))
    if not holder["ev"].wait(timeout=60):
        print("[search] spotdl timeout", file=sys.stderr)
        return []
    return holder["res"]


def do_search(query):
    """Buscar en Spotify via spotdl (URLs descargables por SpotiFLAC).
    Si spotdl no esta disponible, cae a iTunes (solo para ver resultados;
    la descarga con SpotiFLAC puede fallar con URLs de Apple Music)."""
    res = spotdl_search(query)
    if not res:
        res = itunes_search(query)
    # id estable por posicion para referencia simple
    for i, r in enumerate(res):
        r["id"] = i
    return res


# --- descarga con SpotiFLAC en background -------------------------------
_jobs = {}            # job_id -> {"state","file","msg"}
_jobs_lock = threading.Lock()
_job_counter = [0]


def _set_job(job_id, **kw):
    with _jobs_lock:
        _jobs.setdefault(job_id, {"state": "running", "file": "", "msg": ""})
        _jobs[job_id].update(kw)


def _new_audio_file(folder, before):
    try:
        after = set(os.listdir(folder))
        new = [f for f in (after - before) if f.lower().endswith(ALLOWED_EXTS)]
    except OSError:
        new = []
    return new[0] if new else ""


def _download_flac(job_id, url, folder, before):
    try:
        from SpotiFLAC import SpotiFLAC
    except Exception as e:
        _set_job(job_id, state="error",
                 msg=f"SpotiFLAC no instalado: {e} (pip install SpotiFLAC)")
        return
    try:
        _set_job(job_id, state="running", msg="descargando FLAC...")
        # varios proveedores lossless (Tidal suele estar caido).
        SpotiFLAC(url=url, output_dir=folder, quality="LOSSLESS",
                  services=["qobuz", "amazon", "deezer", "tidal"],
                  allow_fallback=True)
        fname = _new_audio_file(folder, before)
        _set_job(job_id, state="done", file=fname,
                 msg="ok" if fname else "descarga terminada")
    except Exception as e:
        _set_job(job_id, state="error", msg=f"FLAC fallo: {e}")


def _download_mp3(job_id, url, folder, before):
    """MP3 via spotdl (descarga de YouTube Music con metadatos de Spotify).
    Casi siempre disponible; util cuando no hay FLAC lossless."""
    import subprocess
    _set_job(job_id, state="running", msg="descargando MP3 (spotdl)...")
    out_tmpl = os.path.join(folder, "{artists} - {title}.{output-ext}")
    cmd = [sys.executable, "-m", "spotdl", "download", url,
           "--output", out_tmpl, "--format", "mp3", "--bitrate", "320k",
           "--client-id", SPOTIFY_ID, "--client-secret", SPOTIFY_SECRET]
    try:
        env = dict(os.environ, PYTHONUTF8="1")
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=300, env=env)
        fname = _new_audio_file(folder, before)
        if fname:
            _set_job(job_id, state="done", file=fname, msg="ok")
        else:
            tail = (p.stderr or p.stdout or "")[-160:]
            _set_job(job_id, state="error", msg=f"MP3 sin archivo. {tail}")
    except subprocess.TimeoutExpired:
        _set_job(job_id, state="error", msg="MP3: tiempo agotado")
    except Exception as e:
        _set_job(job_id, state="error", msg=f"MP3 fallo: {e}")


def _download_worker(job_id, url, folder, fmt):
    try:
        before = set(os.listdir(folder))
    except OSError:
        before = set()
    if fmt == "mp3":
        _download_mp3(job_id, url, folder, before)
    else:
        _download_flac(job_id, url, folder, before)


def start_download(url, folder, fmt="flac"):
    with _jobs_lock:
        _job_counter[0] += 1
        job_id = _job_counter[0]
    _set_job(job_id, state="running", file="", msg="iniciando...")
    t = threading.Thread(target=_download_worker,
                         args=(job_id, url, folder, fmt), daemon=True)
    t.start()
    return job_id


def list_audio(folder):
    out = []
    try:
        for name in os.listdir(folder):
            if not name.lower().endswith(ALLOWED_EXTS):
                continue
            full = os.path.join(folder, name)
            if not os.path.isfile(full):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            out.append({
                "name": name,
                "size": st.st_size,
                "mtime": int(st.st_mtime),
            })
    except OSError as e:
        print(f"[!] No se pudo listar {folder}: {e}", file=sys.stderr)
    out.sort(key=lambda x: x["name"].lower())
    return out


def make_handler(folder):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            sys.stderr.write("[sync] " + (fmt % args) + "\n")

        def _send_json(self, obj, status=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, text, status=200):
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                self._route_get()
            except Exception as e:
                # nunca tirar la conexion en silencio (causaria "HTTP 0" en la Vita)
                import traceback
                traceback.print_exc()
                try:
                    self._send_text(f"server error: {e}", 500)
                except Exception:
                    pass

        def _route_get(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/ping":
                self._send_text("ok")
                return

            if path == "/list":
                self._send_json(list_audio(folder))
                return

            if path == "/search":
                qs = urllib.parse.parse_qs(parsed.query)
                q = (qs.get("q", [""])[0] or "").strip()
                if not q:
                    self._send_text("missing q", 400)
                    return
                self._send_json(do_search(q))
                return

            if path == "/download":
                qs = urllib.parse.parse_qs(parsed.query)
                url = (qs.get("url", [""])[0] or "").strip()
                fmt = (qs.get("fmt", ["flac"])[0] or "flac").strip().lower()
                if fmt not in ("flac", "mp3"):
                    fmt = "flac"
                if not url:
                    self._send_text("missing url", 400)
                    return
                job_id = start_download(url, folder, fmt)
                self._send_json({"job": job_id})
                return

            if path == "/dlstatus":
                qs = urllib.parse.parse_qs(parsed.query)
                try:
                    job_id = int(qs.get("job", ["0"])[0])
                except ValueError:
                    job_id = 0
                with _jobs_lock:
                    st = dict(_jobs.get(job_id, {"state": "unknown", "file": "", "msg": ""}))
                self._send_json(st)
                return

            if path == "/file":
                qs = urllib.parse.parse_qs(parsed.query)
                names = qs.get("name", [])
                if not names:
                    self._send_text("missing name", 400)
                    return
                name = names[0]
                # sanitize: sin separadores de ruta, debe quedar en folder
                if "/" in name or "\\" in name or name in ("", ".", ".."):
                    self._send_text("bad name", 400)
                    return
                if not name.lower().endswith(ALLOWED_EXTS):
                    self._send_text("not allowed", 403)
                    return
                full = os.path.join(folder, name)
                if not os.path.isfile(full):
                    self._send_text("not found", 404)
                    return
                try:
                    size = os.path.getsize(full)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(size))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    with open(full, "rb") as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            try:
                                self.wfile.write(chunk)
                            except (BrokenPipeError, ConnectionResetError):
                                return
                except OSError as e:
                    self._send_text(f"io error: {e}", 500)
                return

            self._send_text("not found", 404)

    return Handler


def main():
    # En Windows el codec por defecto (cp1252) hace fallar la escritura de
    # metadatos/lyrics con caracteres Unicode. Re-lanzar en modo UTF-8.
    if os.name == "nt" and os.environ.get("PYTHONUTF8") != "1":
        os.environ["PYTHONUTF8"] = "1"
        os.execv(sys.executable, [sys.executable] + sys.argv)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    folder = os.path.abspath(sys.argv[1])
    port = int(sys.argv[2]) if len(sys.argv) >= 3 else 8787

    if not os.path.isdir(folder):
        print(f"[!] La carpeta no existe: {folder}", file=sys.stderr)
        sys.exit(2)

    _load_spotify_cfg()
    spoti = "si" if (SPOTIFY_ID and SPOTIFY_SECRET) else "no (falta spotify.cfg)"
    try:
        import spotdl  # noqa: F401
        sd = "si"
    except Exception:
        sd = "NO (pip install spotdl)"
    try:
        import SpotiFLAC  # noqa: F401
        sf = "si"
    except Exception:
        sf = "NO (pip install SpotiFLAC)"

    print(f"[sync] sirviendo {folder} en http://0.0.0.0:{port}")
    print(f"[sync] formatos servidos: {', '.join(ALLOWED_EXTS)}")
    print(f"[sync] SpotiFLAC: {sf}  |  spotdl (busqueda): {sd}  |  credenciales Spotify: {spoti}")

    # arrancar el worker de busqueda (inicializa spotdl en su propio hilo/loop)
    start_search_worker()
    if SPOTIFY_ID and SPOTIFY_SECRET:
        # esperar a que spotdl termine de inicializar ANTES de atender, asi la
        # primera busqueda es rapida y no se pasa del timeout de la Vita.
        print("[sync] inicializando spotdl (esto tarda unos segundos)...")
        for _ in range(60):           # hasta 30 s
            if _spotdl_ready[0]:
                break
            time.sleep(0.5)
        print("[sync] spotdl listo." if _spotdl_ready[0]
              else "[sync] spotdl tardo demasiado; seguira inicializando en segundo plano.")

    print(f"[sync] endpoints: /ping /list /file /search?q= /download?url= /dlstatus?job=")
    print(f"[sync] LISTO PARA BUSCAR. Ctrl+C para detener")

    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(folder))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[sync] detenido")


if __name__ == "__main__":
    main()
