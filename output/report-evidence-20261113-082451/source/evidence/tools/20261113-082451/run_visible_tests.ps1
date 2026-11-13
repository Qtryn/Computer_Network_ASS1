$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'C:/Users/quang/Desktop/MMT_LAB'
$Host.UI.RawUI.WindowTitle='ASS1 Genuine Tests 20261113-082451'
$env:PYTHONIOENCODING='utf-8'
& '.\.venv\Scripts\python.exe' -u 'downloads/report-evidence-20261113-082451/run_visible_tests.py'
exit $LASTEXITCODE
