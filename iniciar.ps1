# Enciende todo lo que necesita la interfaz del economista IA, en orden:
#   1. LM Studio. La versión 1.1.8 ("Bionic") enciende sola su servidor al
#      abrirse y carga el modelo con la primera pregunta. Desde la
#      actualización del 12/10/2026 el CLI `lms` ya no logra encenderlo.
#   2. Interfaz web (http://localhost:8000), que se abre en el navegador.
#
# Uso, desde la carpeta del proyecto en PowerShell:
#   .\iniciar.ps1
# Si Windows bloquea el script por la política de ejecución, una sola vez:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$ErrorActionPreference = "Continue"
$app = Join-Path $env:LOCALAPPDATA "Programs\Bionic\Bionic.exe"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

# La misma URL que usa la interfaz: variable de entorno, luego .env, luego el valor por defecto
$url = "http://localhost:1234/v1"
$archivoEnv = Join-Path $PSScriptRoot ".env"
if (Test-Path $archivoEnv) {
    $linea = Select-String -Path $archivoEnv -Pattern '^\s*LLM_URL\s*=\s*(\S+)' | Select-Object -First 1
    if ($linea) { $url = $linea.Matches[0].Groups[1].Value }
}
if ($env:LLM_URL) { $url = $env:LLM_URL }
$url = $url.TrimEnd("/")

function Servidor-Listo {
    try { $null = Invoke-WebRequest "$url/models" -UseBasicParsing -TimeoutSec 3; return $true }
    catch { return $false }
}

Write-Host "1/2 Verificando el servidor del modelo en $url..." -ForegroundColor Cyan
if (-not (Servidor-Listo)) {
    if (-not (Get-Process Bionic -ErrorAction SilentlyContinue)) {
        if (-not (Test-Path $app)) {
            Write-Host "No se encontró LM Studio ($app). ¿Está instalado?" -ForegroundColor Red
            exit 1
        }
        Start-Process $app
    }
    $listo = $false
    for ($i = 0; $i -lt 30 -and -not $listo; $i++) { Start-Sleep 2; $listo = Servidor-Listo }
    if (-not $listo) {
        Write-Host ("El servidor no respondió en 60 s. En LM Studio, pestaña Developer: " +
                    "enciéndalo y revise que el puerto coincida con LLM_URL del .env.") -ForegroundColor Red
        exit 1
    }
}
Write-Host "    Listo. El modelo se carga con la primera pregunta (unos 15 s más)." -ForegroundColor Gray

Write-Host "2/2 Abriendo la interfaz en http://localhost:8000 (Ctrl+C para cerrarla)..." -ForegroundColor Cyan
Start-Process "http://localhost:8000"   # el navegador reintenta mientras el servidor arranca
& $python -m uvicorn app.main:app --port 8000 --app-dir $PSScriptRoot
