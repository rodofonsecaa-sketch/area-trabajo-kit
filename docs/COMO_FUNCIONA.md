# Cómo funciona por dentro

## Flujo

1. `data.js` (a mano) + `auto.js` y `chats.js` (de `actualizar.py`) son los datos.
2. `generador/build.py` arma:
   - `index.html` + `app.js` locales en esta carpeta;
   - la versión web (`3b_aurora2.html`) y sus archivos publicados (`pub/`) en `%TEMP%\area-trabajo-build\` (fuera del Drive porque pesan ~60 MB).
3. Claude publica la versión web en claude.ai (a pedido: la herramienta exige revisar cada archivo subido, por eso no es automática).

Construir: `python generador/build.py` (PYTHONIOENCODING=utf-8).
Publicar: Artifact con `file_path=%TEMP%\area-trabajo-build\3b_aurora2.html`, `url` del artefacto, `root=%TEMP%\area-trabajo-build\pub` y `files` = {"f/NNN.ext": "NNN.ext"} sacado de `pub.json`.

## Piezas

- **Todo abre desde Drive G:**: `home` en `data.js` apunta a la copia de `~/.claude` en tu Drive (espejo de `~/.claude`) y `actualizar.py` (`enlace()`) escribe en `auto.js` la ruta del espejo cuando existe. `sync-a-drive.ps1` copia C:→G: y de vuelta G:→C: lo editado en Drive (más nuevo, solo archivos que ya existen en C:), cada 15 min.
- **Conectores sin uso**: `conectoresSinUso` en `data.js` (REG) fuerza "falta autorizar" aunque se hayan conectado alguna vez.
- **Estados de conectores**: `actualizar.py` lee `~/.claude.json` (`claudeAiMcpEverConnected`) y `~/.claude/mcp-needs-auth-cache.json` (los que faltan autorizar). `core.js` pone activo/pendiente en Canva, Figma, Netlify, Vercel, etc. Claude Code refresca ese archivo al abrir una sesión nueva.
- **Chats por proyecto** (`generador/chats.py`): un chat cuenta para un proyecto solo si abrió o editó archivos dentro de su carpeta (o se abrió desde ella) al menos 10 veces, y ese proyecto es el principal del chat. Enlace: `vscode://anthropic.claude-code/open?session=<id>`.
- **PBIP/PBIX**: `chats.py` busca .pbip/.pbix en la carpeta de cada proyecto (sin respaldos, hasta 3 niveles) → botón «Abrir en mi PC · archivo».
- **Abrir en mi PC**: enlaces `abrir:<ruta>` que abre `~/.claude/scripts/abrir.ps1` (solo rutas del Drive, `.claude` u `.orca`; nunca ejecutables). Funcionan solo en este PC.
- **Videos**: los .mp4 grandes se comprimen con ffmpeg (720p/540p/360p) y se guardan en `%TEMP%\area-trabajo-build\vcache`.
- **Fondo**: red animada `.bgnet` (SVG en `tpl.html`, CSS en el tema aurora2 dentro de `build.py`).
- **Temas**: el CSS de cada tema vive en `build.py`; los archivos de `themes/` se regeneran en cada build.
