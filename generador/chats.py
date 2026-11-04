"""Historial de chats de Claude Code por proyecto: lee ~/.claude/projects/*/*.jsonl y los asocia a cada ruta de proyecto de data.js."""
import glob, json, os, re

ALIAS = {"Umbra-videochat": ["dev/videochat", "callumbra"], "Creador de Videos Remotion y HyperFrames": ["videos-remotion"]}

def proyectos(data_txt):
    out = []
    for m in re.finditer(r'ruta:"([^"]+)"', data_txt):
        n = re.findall(r'\{n:"([^"]+)"', data_txt[:m.start()])
        base = m.group(1).rstrip("/").split("/")[-1]
        al = {"/" + a.strip("/") + "/" for a in {base.lower(), base.lower().replace(" ", "-")} | set(ALIAS.get(base, []))}
        out.append((n[-1] if n else base, sorted(al)))
    return out

def local(ts):
    import datetime
    try: return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError: return ts[:16].replace("T", " ")

def sesion(f, claves=()):
    tit = ai = last = None; ts = ""; primero = None; cwd = ""
    partes = []; raw = dict.fromkeys(claves, 0)
    for l in open(f, encoding="utf-8", errors="ignore"):
        if '"type":"user"' not in l and '"type":"assistant"' not in l and '-title"' not in l and 'last-prompt' not in l: continue
        try: j = json.loads(l)
        except ValueError: continue
        t = j.get("type")
        if claves and t in ("user", "assistant") and not j.get("isSidechain"):
            c = (j.get("message") or {}).get("content")
            ll = (c if isinstance(c, str) else " ".join(x.get("text", "") if x.get("type") == "text" else json.dumps(x.get("input"), ensure_ascii=False) if x.get("type") == "tool_use" else "" for x in c or [] if isinstance(x, dict))).lower().replace("\\\\", "/").replace("\\", "/")
            for k in claves:
                if k in ll: raw[k] += ll.count(k)
        if t in ("user", "assistant") and not j.get("isSidechain"):
            c = (j.get("message") or {}).get("content")
            if isinstance(c, list):
                for x in c or []:
                    if not isinstance(x, dict): continue
                    if x.get("type") == "tool_use" and isinstance(x.get("input"), dict):
                        partes += [str(x["input"][k]) for k in ("file_path", "notebook_path", "path") if x["input"].get(k)]
        if t == "custom-title": tit = j.get("customTitle")
        elif t == "ai-title": ai = j.get("aiTitle")
        elif t == "last-prompt": last = j.get("lastPrompt")
        elif t == "user" and not primero and not j.get("isSidechain"):
            c = (j.get("message") or {}).get("content")
            c = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict) and x.get("type") == "text")
            c = re.sub(r"<[^>]+>[^<]*</[^>]+>", "", c).strip()
            if c and not c.startswith("This session is being continued"): primero = c
        if j.get("timestamp"): ts = max(ts, j["timestamp"])
        cwd = cwd or j.get("cwd", "")
    return "\n".join(partes).lower().replace("\\\\", "/").replace("\\", "/"), {"id": os.path.basename(f)[:-6], "t": (tit or ai or primero or "Chat sin título")[:90],
                         "u": re.sub(r"\s+", " ", last or primero or "")[:160], "f": local(ts), "cwd": cwd.lower(), "raw": raw}

def chats(data_txt, maximo=5):
    R = os.path.expanduser("~/.claude/projects")
    fs = glob.glob("\\\\?\\" + R + "\\*\\*.jsonl") if os.name == "nt" else glob.glob(R + "/*/*.jsonl")
    ses, P = [], proyectos(data_txt)
    claves = sorted({a.strip("/") for _, al in P for a in al})
    cf = os.path.join(os.environ.get("TEMP", R), "infografia-chats-cache.json")  # caché por (mtime, tamaño): solo relee los chats que cambiaron
    try: cache = json.load(open(cf, encoding="utf-8"))
    except (OSError, ValueError): cache = {}
    if cache.get("claves") != claves: cache = {"claves": claves}
    nuevo = {"claves": claves}
    for f in fs:
        try: st = os.stat(f)
        except OSError: continue
        if st.st_size < 3000: continue
        k, firma = os.path.basename(f), [st.st_mtime, st.st_size]
        c = cache.get(k)
        if not (c and c[0] == firma):
            try: c = [firma, list(sesion(f, claves))]
            except OSError: continue
        nuevo[k] = c; ses.append(tuple(c[1]))
    try: json.dump(nuevo, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
    except OSError: pass
    out = {}
    pts = [[sum(low.count(a) for a in al) + (20 if any(a in s["cwd"].replace("\\", "/") + "/" for a in al) else 0) for _, al in P] for low, s in ses]
    infog = [i for i, (n, al) in enumerate(P) if "/infografia/" in al]
    for pi, (nom, al) in enumerate(P):
        hits = []
        for si, (low, s) in enumerate(ses):
            k, top = pts[si][pi], max(pts[si])
            if k >= 10 and k >= 0.6 * top: hits.append(dict(s, m=k))
        if not hits:  # respaldo: chats donde se pidió o mencionó la carpeta (fuera de los chats de esta infografía)
            for si, (low, s) in enumerate(ses):
                k = sum(s["raw"].get(a.strip("/"), 0) for a in al)
                if k >= 10 and not any(pts[si][i] == max(pts[si]) > 0 for i in infog): hits.append(dict(s, m=k))
        vistos = set()
        hits = [h for h in sorted(hits, key=lambda s: s["f"], reverse=True) if not ((h["t"], h["f"]) in vistos or vistos.add((h["t"], h["f"])))]
        if hits: out[nom] = [{x: h[x] for x in ("id", "t", "u", "f", "m")} for h in hits[:maximo]]
    return out

def pbis(data_txt):
    """Archivos .pbip/.pbix dentro de la carpeta de cada proyecto (sin respaldos), para el botón «Abrir en mi PC»."""
    base = re.search(r'base:\s*"([^"]*)"', data_txt).group(1) or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace("\\", "/") + "/"
    out = {}
    for m in re.finditer(r'ruta:"([^"]+)"', data_txt):
        n = re.findall(r'\{n:"([^"]+)"', data_txt[:m.start()])
        ruta = m.group(1).rstrip("/")
        hall = []
        pila = [(base + ruta, 0)]  # scandir en vez de os.walk: en Google Drive (G:) os.walk es muy lento
        while pila:
            raiz, prof = pila.pop()
            try:
                with os.scandir(raiz) as it:
                    for e in it:
                        if e.is_dir(follow_symlinks=False):
                            if prof < 3 and not re.search(r"respaldo|backup|node_modules|^\.|\.Report$|\.SemanticModel$|\.Dataset$", e.name, re.I):
                                pila.append((os.path.join(raiz, e.name), prof + 1))
                        elif e.name.lower().endswith((".pbip", ".pbix")):
                            hall.append(raiz[len(base):].replace("\\", "/") + "/" + e.name)
            except OSError:
                pass
        if hall and n: out[n[-1]] = sorted(hall)[:6]
    return out

def chats_js(data_txt):
    return ("window.CHATS=" + json.dumps(chats(data_txt), ensure_ascii=False) + ";\nwindow.PBIS=" +
            json.dumps(pbis(data_txt), ensure_ascii=False) + ";").replace("</", "<\\/")

if __name__ == "__main__":
    import sys
    r = chats(open(sys.argv[1], encoding="utf-8").read())
    for k, v in r.items():
        print("##", k)
        for s in v: print("  ", s["f"], s["m"], s["t"][:60], "|", s["u"][:60])
