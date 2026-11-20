"""Servicio local del Área de Trabajo: escucha en 127.0.0.1:8799 y ejecuta abrir.ps1 (que ya valida rutas y acciones permitidas).
Solo acepta peticiones sin Origin o desde file:// (Origin 'null'); rechaza cualquier sitio web."""
import subprocess, sys, os, json, time, shutil, glob, datetime, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer
from urllib.parse import urlparse, parse_qs

LOG = open(os.path.join(os.environ.get("TEMP", "."), "abrir-servicio.log"), "ab", buffering=0)
PS1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abrir.ps1")
PROG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "programacion.ps1")  # opcional


HOME = os.path.expanduser("~")
CL = os.path.join(HOME, ".claude")
PUERTOS = {}
_cache = {}
def cached(k, seg, fn):
    t = time.time()
    if k in _cache and t - _cache[k][0] < seg: return _cache[k][1]
    try: v = fn()
    except Exception as e: v = {"ok": False, "txt": str(e)[:80]}
    _cache[k] = (t, v); return v
def ps(cmd, to=20):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=to, creationflags=0x08000000)
    return (r.stdout or "").strip()
def abierto(port):
    import socket
    s = socket.socket(); s.settimeout(0.3)
    try: s.connect(("127.0.0.1", int(port))); return True
    except Exception: return False
    finally: s.close()
def gcloud():
    # El dashboard usa su token OAuth propio (se renueva solo); revisar ese, no la CLI gcloud
    tok = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ReporteEjecutivoAbastecimiento", "bq-token.json")
    if os.path.exists(tok):
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            c = Credentials.from_authorized_user_file(tok, ["https://www.googleapis.com/auth/bigquery"])
            if not c.valid:
                c.refresh(Request()); open(tok, "w", encoding="utf-8").write(c.to_json())
            return {"ok": True, "txt": "sesión activa (token propio, se renueva solo)"}
        except Exception:
            return {"ok": False, "txt": "token propio vencido: hay que reingresar"}
    g = shutil.which("gcloud")
    if not g: return {"ok": None, "txt": "gcloud no instalado"}
    try:
        r = subprocess.run([g, "auth", "print-access-token"], capture_output=True, text=True, timeout=60, creationflags=0x08000000)
    except subprocess.TimeoutExpired:
        return {"ok": None, "txt": "sin respuesta, reintentando"}
    ok = r.returncode == 0 and len(r.stdout.strip()) > 20
    return {"ok": ok, "txt": "sesión activa" if ok else "vencida: hay que reingresar"}
def sync():
    f = os.path.join(CL, "sync-a-drive.log")
    if not os.path.exists(f): return {"ok": None, "txt": "no configurada"}
    ln = [l.strip() for l in open(f, encoding="utf-8", errors="ignore") if l.strip()][-1]
    fe = datetime.datetime.strptime(ln[:16], "%Y-%m-%d %H:%M")
    mins = (datetime.datetime.now() - fe).total_seconds() / 60
    try: run = ps("(Get-ScheduledTask SyncADrive).State") == "Running"
    except Exception: run = False
    if run: return {"ok": mins < 180 and ln.endswith("OK"), "txt": "al dia (copia diaria de Descargas en curso)" if mins < 180 else "copiando Descargas hace %d min" % mins}
    return {"ok": ln.endswith("OK") and mins < 45, "txt": "última copia hace %d min" % mins + ("" if ln.endswith("OK") else ": " + ln[17:70])}
def kb(p):
    return round(os.path.getsize(p) / 1024, 1) if os.path.exists(p) else 0
def contexto():
    mem = glob.glob(os.path.join(CL, "projects", "*", "memory", "MEMORY.md"))
    regl = sum(os.path.getsize(f) for f in glob.glob(os.path.join(CL, "reglas", "*.md")))
    m = max([kb(f) for f in mem] or [0])
    return {"claude_md": kb(os.path.join(CL, "CLAUDE.md")), "memory_md": m, "reglas_kb": round(regl / 1024, 1), "orq_kb": kb(os.path.join(CL, "orquestacion.md"))}
def cascada():
    f = os.path.join(CL, "scripts", "cascada.log"); por = {}
    if os.path.exists(f):
        for ln in open(f, encoding="utf-8", errors="ignore"):
            c = ln.rstrip().split(chr(9))
            if len(c) >= 4:
                d = por.setdefault(c[2], {"n": 0, "ok": 0, "seg": 0.0, "ult": ""})
                d["n"] += 1; d["ok"] += c[3].upper().startswith("OK"); d["ult"] = c[0]
                try: d["seg"] += float(c[4].replace(",", "."))
                except Exception: pass
    return por
def cupo():
    n = datetime.datetime.now(); d = (4 - n.weekday()) % 7
    r = n.replace(hour=3, minute=0, second=0, microsecond=0) + datetime.timedelta(days=d)
    if r <= n: r += datetime.timedelta(days=7)
    o = {"dias": round((r - n).total_seconds() / 86400, 1), "reinicio": r.strftime("%a %d-%m %H:%M")}
    o.update(uso_real())
    return o
_USO = {"t": 0, "v": {}}
def uso_real():
    # Mismo dato que el panel Usage de VS Code (endpoint oauth/usage); el token no se guarda ni se muestra
    if time.time() - _USO["t"] < 60: return _USO["v"]
    _USO["t"] = time.time()
    try:
        import json, urllib.request
        tk = json.load(open(os.path.expanduser("~/.claude/.credentials.json"), encoding="utf-8"))["claudeAiOauth"]["accessToken"]
        rq = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={"Authorization": "Bearer " + tk, "anthropic-beta": "oauth-2025-04-20", "User-Agent": "claude-code/2.0"})
        d = json.loads(urllib.request.urlopen(rq, timeout=10).read().decode())
        v = {}
        for k, c in (("sesion", "five_hour"), ("semana", "seven_day")):
            x = d.get(c)
            if x: v[k] = {"pct": round(x["utilization"]), "reinicio": datetime.datetime.fromisoformat(x["resets_at"]).astimezone().strftime("%d/%m %H:%M")}
        _USO["v"] = v
    except Exception:
        pass
    return _USO["v"]
LENTO = {}
def modelos():
    j = os.path.join(os.path.expanduser("~"), ".claude", "router", "uso-router.json")
    if not os.path.exists(j) or time.time() - os.path.getmtime(j) > 600:
        subprocess.run([sys.executable.replace("pythonw", "python"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "router-uso.py")], capture_output=True, timeout=300, creationflags=0x08000000)
    return json.load(open(j, encoding="utf-8"))
def openrouter():
    ok = bool(os.environ.get("OPENROUTER_API_KEY") or ps("[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User')"))
    return {"ok": ok, "txt": "llave presente" if ok else "llave no encontrada"}
def _uno(k, f):
    while True:
        try: LENTO[k] = f()
        except Exception as e: LENTO[k] = {"ok": None, "txt": "sin respuesta, reintentando"}
        time.sleep(120)
def refresco():
    for k, f in (("gcloud", gcloud), ("sync", sync), ("openrouter", openrouter), ("modelos", modelos)):
        threading.Thread(target=_uno, args=(k, f), daemon=True).start()
    while True: time.sleep(3600)
def estado():
    st = {"servicio": True, "dash": {p: {"n": nm, "arriba": abierto(p)} for p, nm in PUERTOS.items()}}
    for k in ("gcloud", "sync", "openrouter"): st[k] = LENTO.get(k, {"ok": None, "txt": "comprobando…"})
    st["modelos"] = LENTO.get("modelos", {})
    st["contexto"] = contexto(); st["ias"] = cascada(); st["cupo"] = cupo()
    return st
def detener(port):
    ps("Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" % int(port))

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        o = self.headers.get("Origin")
        if o not in (None, "null"):
            self.send_response(403); self.end_headers(); return
        p = urlparse(self.path)
        if p.path == "/ping":
            self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(b"ok"); return
        if p.path == "/estado":
            b = json.dumps(estado(), ensure_ascii=False).encode("utf-8")
            self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(b); return
        if p.path in ("/bqxl", "/bqxl-estado"):
            t = (parse_qs(p.query).get("t") or [""])[0]
            if t.replace("_", "").isalnum() and len(t) < 60:
                st = os.path.join(os.environ.get("TEMP", "."), "bq_excel_%s.json" % t)
                if p.path == "/bqxl":
                    json.dump({"est": "inicio", "msg": "Iniciando…"}, open(st, "w", encoding="utf-8"), ensure_ascii=False)
                    subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bq_excel.py"), t], creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=LOG, stderr=subprocess.STDOUT)
                    b = b'{"est":"inicio"}'
                else:
                    try: b = open(st, "rb").read()
                    except Exception: b = b'{"est":"error","msg":"sin estado"}'
                self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(b); return
        if p.path == "/prog/ultimo":
            import re
            pid = (parse_qs(p.query).get("id") or [""])[0]
            if not re.fullmatch(r"[a-z0-9-]{1,40}", pid):
                self.send_response(400); self.end_headers(); return
            f = os.path.join(os.path.dirname(PROG), "ultimos", pid + ".json")
            try: b = open(f, "rb").read()
            except Exception: b = json.dumps({"auto": pid, "correos": []}).encode("utf-8")
            self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(b); return
        if p.path in ("/prog", "/prog/guardar", "/prog/correr"):
            # Plataforma Programación: script fijo, parámetros validados (id corto, datos base64, modo cerrado)
            import re
            q = parse_qs(p.query); pid = (q.get("id") or [""])[0]; d = (q.get("d") or [""])[0]; m = (q.get("m") or ["config"])[0]
            args = ["-Accion", "estado"]
            if p.path != "/prog":
                if not re.fullmatch(r"[a-z0-9-]{1,40}", pid) or not re.fullmatch(r"[A-Za-z0-9+/=]{0,12000}", d) or m not in ("config", "prueba"):
                    self.send_response(400); self.end_headers(); return
                args = ["-Accion", "guardar", "-Id", pid, "-Datos", d] if p.path.endswith("guardar") else ["-Accion", "correr", "-Id", pid, "-Modo", m]
            try:
                r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PROG] + args, capture_output=True, timeout=60, creationflags=0x08000000)
                b = (r.stdout or b"").strip() or json.dumps({"ok": False, "error": (r.stderr or b"").decode("utf-8", "ignore")[-300:]}).encode("utf-8")
            except subprocess.TimeoutExpired:
                b = b'{"ok":false,"error":"sin respuesta en 60 s"}'
            self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(b); return
        if p.path == "/detener":
            q = (parse_qs(p.query).get("p") or [""])[0]
            if q == "todos" or q in PUERTOS:
                for x in (PUERTOS if q == "todos" else [q]): detener(x)
                self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(b"ok"); return
        if p.path == "/abrir":
            u = (parse_qs(p.query).get("u") or [""])[0]
            if u.startswith("abrir:") and len(u) < 1500 and '"' not in u:
                if o is None:  # navegación directa (enlace en VS Code/.md): lanzar sin esperar y avisar en la pestaña
                    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1, u],
                                     creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=LOG, stderr=subprocess.STDOUT)
                    self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
                    self.wfile.write("<body style='font:16px sans-serif;background:#111;color:#ddd;padding:2em'>Abriendo en tu PC (≈10 s)… puedes cerrar esta pestaña.</body>".encode("utf-8")); return
                try:
                    rc = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1, u],
                                        creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=LOG, stderr=subprocess.STDOUT, timeout=10).returncode
                except subprocess.TimeoutExpired:
                    rc = 3  # Drive colgado o muy lento
                cod, txt = {0: (200, b"ok"), 2: (503, b"drive"), 3: (504, b"lento")}.get(rc, (422, b"fallo"))
                self.send_response(cod); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(txt); return
        self.send_response(404); self.end_headers()

if __name__ == "__main__":
    import threading; threading.Thread(target=refresco, daemon=True).start()
    HTTPServer(("127.0.0.1", 8799), H).serve_forever()
