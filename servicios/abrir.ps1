param([string]$Uri)
$inf = Split-Path $PSScriptRoot -Parent
$base = ([regex]::Match((Get-Content (Join-Path $inf 'data.js') -Raw -Encoding UTF8), 'base:\s*"([^"]*)"').Groups[1].Value -replace '/', '\').TrimEnd('\')
if (-not $base) { $base = Split-Path $inf -Parent }
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
# Todo lo web (paginas, dashboards, HTML, PDF) se abre en Chrome, no en el navegador predeterminado (Edge)
function Web([string]$u) { if ($chrome) { Start-Process $chrome -ArgumentList """$u""" } else { Start-Process $u } }
# Accion fija abrir:actualizar -> lee todo Claude en VS Code (actualizar.py) y abre el Área de Trabajo local. Sin argumentos externos.
if ($Uri -match '^abrir:/*actualizar(-local)?/?$') {
  python (Join-Path $inf 'actualizar.py') | Out-Null
  Start-Process pythonw -ArgumentList ('"' + (Join-Path $inf 'generador\bq_reportes.py') + '"') -WindowStyle Hidden
  if ($Uri -notmatch 'local') { Web (Join-Path $inf 'index.html') }
  exit 0
}
# Acciones fijas abrir:dash-<id> -> levantan un dashboard Streamlit (si no corre) y lo abren en el navegador. Tabla cerrada, sin argumentos externos.
$dash = @{
  # 'dash-<id>' = @('<carpeta del proyecto>', '<app>.py', <puerto>)
}
if ($Uri -match '^abrir:/*([a-z-]+)/?$' -and $dash.ContainsKey($Matches[1])) {
  $d = $dash[$Matches[1]]
  $dir = Join-Path $base $d[0]
  # Prueba TCP directa (Get-NetTCPConnection tarda ~4 s y el servicio corta a los 10 s)
  $c = New-Object Net.Sockets.TcpClient; $arriba = $c.ConnectAsync('127.0.0.1', $d[2]).Wait(500) -and $c.Connected; $c.Close()
  if (-not $arriba) {
    Start-Process python -ArgumentList '-m','streamlit','run',$d[1],'--server.address','127.0.0.1','--server.port',$d[2],'--server.headless','true' -WorkingDirectory $dir -WindowStyle Minimized
    Start-Sleep -Seconds 7
  }
  Web ('http://127.0.0.1:' + $d[2])
  exit 0
}
# Abre archivos y carpetas desde enlaces abrir:<ruta> (Área de Trabajo). Solo dentro de las raices permitidas; nunca ejecuta programas.
$ruta = [Uri]::UnescapeDataString(($Uri -replace '^abrir:/*', '')) -replace '/', '\'
$full = [IO.Path]::GetFullPath($ruta.TrimEnd('\'))
$raices = @($base, (Join-Path $env:USERPROFILE '.claude'), (Join-Path $env:USERPROFILE '.orca'))
if (-not ($raices | Where-Object { $full.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) })) { exit 1 }
# exit 2 = Google Drive (G:) desmontado; el Área de Trabajo muestra "Drive no disponible"
if (-not (Test-Path -LiteralPath $base)) { exit 2 }
if (-not (Test-Path -LiteralPath $full)) { exit 1 }
$ext = [IO.Path]::GetExtension($full).ToLower()
if ((Test-Path -LiteralPath $full -PathType Leaf) -and $ext -in '.exe', '.msi', '.lnk', '.scr', '.com', '.url') { exit 1 }
$texto = '.ps1', '.py', '.js', '.cmd', '.bat', '.vbs', '.sh', '.ts', '.md', '.json', '.tmdl', '.log', '.txt', '.css', '.yml', '.yaml', '.toml', '.sql'
if ((Test-Path -LiteralPath $full -PathType Leaf) -and $texto -contains $ext) {
  Start-Process code -ArgumentList "`"$full`"" -WindowStyle Hidden
} elseif ((Test-Path -LiteralPath $full -PathType Leaf) -and $ext -in '.html', '.htm', '.pdf', '.svg') {
  Web $full
} else {
  Invoke-Item -LiteralPath $full
}
