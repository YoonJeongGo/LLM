$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw '프로젝트 .venv가 없습니다. README 설치 절차를 먼저 실행하세요.' }
$env:PYTHONPATH = Join-Path $taskRoot 'src'
$env:PYTHONUTF8 = '0'
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
# Opening the app never starts a GPU diagnostic or overwrites historical evidence.
# Explicit diagnostics remain available through the authenticated, bounded API.
& $taskPython -m edu_tutor serve
exit $LASTEXITCODE
