"""Detecta skills, MCP, scripts y carpetas de proyectos y escribe auto.js.
La infografía suma como "Nuevo" lo que no esté ya en data.js. Corre solo al iniciar cada sesión de Claude."""
import json, os, re, datetime
from pathlib import Path

# BASE = carpeta de proyectos, tomada de "base" en data.js (si está vacía, la carpeta que contiene Infografia)
_b = re.search(r'base:\s*"([^"]*)"', Path(__file__).with_name("data.js").read_text(encoding="utf-8")).group(1)
BASE = Path(_b) if _b else Path(__file__).resolve().parent.parent
WS = BASE
HOME = Path.home() / ".claude"
OUT = Path(__file__).with_name("auto.js")
ESPEJO = BASE / "Claude-config"  # copia en Drive de ~/.claude (sync-a-drive.ps1): los accesos abren desde G:

IGNORAR_RAIZ = {"Infografia", "_archivo", "respaldos"}
SALTAR = {"node_modules", ".git", ".venv", "venv", "__pycache__", "respaldos", "backups", "_archivo", ".next", "dist", "build"}
VER = [".html", ".pdf", ".mp4", ".pptx", ".pbip", ".rbxlx", ".docx", ".xlsx"]


def rel(p):
    return p.relative_to(BASE).as_posix()


def recorrer(carpeta, profundidad, saltar=lambda d: False, nivel=0):
    """Como os.walk pero con scandir: en Google Drive (G:) os.walk tarda segundos por sus islink/stat extra."""
    dirs, archivos = [], []
    try:
        with os.scandir(carpeta) as it:
            for e in it:
                try:
                    (dirs if e.is_dir(follow_symlinks=False) else archivos).append(e.name)
                except OSError:
                    pass
    except OSError:
        return
    yield carpeta, nivel, archivos
    if nivel < profundidad:
        for d in dirs:
            if not saltar(d):
                yield from recorrer(os.path.join(carpeta, d), profundidad, saltar, nivel + 1)


def visibles(carpeta, maximo=3, profundidad=3):
    hallados = []
    for raiz, nivel, archivos in recorrer(str(carpeta), profundidad,
                                          lambda d: d in SALTAR or d.endswith((".SemanticModel", ".Report"))):
        for a in archivos:
            ext = Path(a).suffix.lower()
            if ext in VER and not (ext == ".html" and ("hyperframes.json" in archivos or "Dev-respaldo" in Path(raiz).parts)):
                hallados.append((VER.index(ext), nivel, Path(raiz) / a))
    hallados.sort(key=lambda x: (x[0], x[1], str(x[2])))
    return [{"t": f.stem[:40], "r": rel(f)} for _, _, f in hallados[:maximo]]


CACHE = Path(__file__).with_name("respaldos") / "cache_respaldos.json"


def proyectos():
    carpetas = [d for d in BASE.iterdir() if d.is_dir() and d.name not in IGNORAR_RAIZ and not d.name.startswith(".")]
    # Las carpetas de respaldo son grandes y casi no cambian: se re-escanean 1 vez al día (en Drive tardan segundos)
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
        if datetime.datetime.now().timestamp() - cache.get("_ts", 0) > 86400:
            cache = {}
    except (OSError, ValueError):
        cache = {}
    nuevo = not cache
    out = []
    for d in sorted(carpetas, key=lambda x: x.name.lower()):
        try:
            if "respaldo" in d.name.lower():
                if d.name not in cache:
                    cache[d.name], nuevo = visibles(d), True
                ver = cache[d.name]
            else:
                ver = visibles(d)
            out.append({"n": d.name.replace("-", " "), "ruta": rel(d), "tag": "Detectado",
                        "d": "Carpeta detectada automáticamente.", "ver": ver})
        except OSError:
            pass
    if nuevo:
        try:
            cache["_ts"] = datetime.datetime.now().timestamp()
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return out


def descripcion(skill_md):
    try:
        for linea in skill_md.read_text(encoding="utf-8").splitlines()[:15]:
            if linea.startswith("description:"):
                d = linea.split(":", 1)[1].strip().strip('"')
                return d[:220] + ("…" if len(d) > 220 else "")
    except OSError:
        pass
    return "Skill instalada."


def enlace(p):
    """Ruta para abrir: su copia en el espejo de Drive si existe; si no, la original."""
    p = Path(p)
    e = ESPEJO / "mcp-servers.json" if p == Path.home() / ".claude.json" else None
    if e is None:
        try:
            e = ESPEJO / p.relative_to(HOME)
        except ValueError:
            return p.as_posix()
    return e.as_posix() if e.exists() else p.as_posix()


def skills():
    d = HOME / "skills"
    return [{"id": s.name, "n": s.name, "d": descripcion(s / "SKILL.md"), "r": enlace(s / "SKILL.md")}
            for s in sorted(d.iterdir())
            if s.is_dir() and s.name != "synced" and (s / "SKILL.md").exists()] if d.exists() else []


def mcp():
    servidores = {}
    for f in (WS / ".mcp.json", Path.home() / ".claude.json"):
        try:
            for k in json.loads(f.read_text(encoding="utf-8")).get("mcpServers", {}):
                servidores[k] = f.as_posix()
        except (OSError, ValueError):
            pass
    return [{"id": k, "n": k, "d": "Servidor MCP configurado.", "r": enlace(servidores[k])} for k in sorted(servidores)]


def scripts():
    d = HOME / "scripts"
    return [{"id": f.name, "n": f.name, "d": "Script de orquestación.", "r": enlace(f)}
            for f in sorted(d.glob("*.ps1"))] if d.exists() else []


def conectores():
    """Estado real de los conectores de claude.ai según Claude Code: activo o pendiente (falta autorizar)."""
    est = {}
    try:
        for k in json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8")).get("claudeAiMcpEverConnected", []):
            est[k.replace("claude.ai ", "")] = "activo"
    except (OSError, ValueError):
        pass
    try:
        for k in json.loads((HOME / "mcp-needs-auth-cache.json").read_text(encoding="utf-8")):
            est[k.replace("claude.ai ", "")] = "pendiente"
    except (OSError, ValueError):
        pass
    try:  # REG en data.js: conectores sin uso se muestran como "falta autorizar"
        import re
        m = re.search(r"conectoresSinUso:\s*\[([^\]]*)\]", OUT.with_name("data.js").read_text(encoding="utf-8"))
        for k in re.findall(r'"([^"]+)"', m.group(1) if m else ""):
            est[k] = "pendiente"
    except OSError:
        pass
    return est


datos = {"generado": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
         "skills": skills(), "mcp": mcp(), "scripts": scripts(), "proyectos": proyectos(), "conectores": conectores()}
OUT.write_text("window.AUTO = " + json.dumps(datos, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
import sys
sys.path.insert(0, str(Path(__file__).with_name("generador")))
from chats import chats_js
OUT.with_name("chats.js").write_text(chats_js(OUT.with_name("data.js").read_text(encoding="utf-8")), encoding="utf-8")
print(f"auto.js: {len(datos['skills'])} skills, {len(datos['mcp'])} MCP, {len(datos['scripts'])} scripts, {len(datos['proyectos'])} proyectos")

try:
    import subprocess, time
    _u = Path(__file__).with_name("uso.js")
    if not _u.exists() or time.time() - _u.stat().st_mtime > 120:
        subprocess.Popen(["python", str(Path(__file__).with_name("servicios") / "uso-tokens.py")], creationflags=0x08000000)
except Exception:
    pass

# Versiones: cada cambio de la página o de data.js queda copiado en respaldos/versiones (se guardan las últimas 30 de cada uno)
try:
    import hashlib, shutil
    _v = Path(__file__).with_name("respaldos") / "versiones"
    _v.mkdir(parents=True, exist_ok=True)
    for _n in ("index.html", "app.js", "data.js"):
        _f = Path(__file__).with_name(_n)
        _h = hashlib.md5(_f.read_bytes()).hexdigest()[:8]
        _prev = sorted(_v.glob(_n + ".*"))
        if not _prev or not _prev[-1].name.endswith(_h):
            shutil.copy2(_f, _v / f"{_n}.{datetime.datetime.now():%Y%m%d-%H%M%S}.{_h}")
            for _o in sorted(_v.glob(_n + ".*"))[:-30]:
                _o.unlink()
except Exception:
    pass

