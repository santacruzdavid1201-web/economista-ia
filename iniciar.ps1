# Enciende todo lo que necesita la interfaz del economista IA, en orden:
#   1. Servidor de LM Studio (API en http://localhost:1234)
#   2. Modelo cargado en la tarjeta gráfica (si no lo está)
#   3. Interfaz de Streamlit (http://localhost:8501)
#
# Uso, desde la carpeta del proyecto en PowerShell:
#   .\iniciar.ps1
# Si Windows bloquea el script por la política de ejecución, una sola vez:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#
# Antes de correrlo: abra la aplicación LM Studio (si está cerrada, el
# servicio a veces no arranca desde la terminal).

$ErrorActionPreference = "Continue"
$lms = Join-Path $env:USERPROFILE ".lmstudio\bin\lms.exe"
$modelo = if ($env:LLM_MODELO) { $env:LLM_MODELO } else { "qwen2.5-7b-instruct" }
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $lms)) {
    Write-Host "No se encontró LM Studio ($lms). ¿Está instalado?" -ForegroundColor Red
    exit 1
}

Write-Host "1/3 Encendiendo el servidor de LM Studio..." -ForegroundColor Cyan
& $lms server start
if ($LASTEXITCODE -ne 0) {
    Write-Host "No arrancó el servidor. Abra la aplicación LM Studio y vuelva a ejecutar .\iniciar.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "2/3 Verificando el modelo $modelo..." -ForegroundColor Cyan
$cargados = (& $lms ps) -join "`n"
if ($cargados -notmatch [regex]::Escape($modelo)) {
    # --gpu max: todo el modelo en la tarjeta gráfica (en CPU es 5-10 veces más lento)
    & $lms load $modelo --gpu max -y
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudo cargar $modelo. Revise en LM Studio que el modelo esté descargado." -ForegroundColor Red
        exit 1
    }
}

Write-Host "3/3 Abriendo la interfaz en http://localhost:8501 (Ctrl+C para cerrarla)..." -ForegroundColor Cyan
& $python -m streamlit run (Join-Path $PSScriptRoot "frontend\app.py") --browser.gatherUsageStats false
