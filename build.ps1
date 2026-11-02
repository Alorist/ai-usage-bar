# Builds dist\AIUsageBar_<version>.rmskin
#   1. bundles src\aiusage.py into a standalone exe (no Python needed by users)
#   2. regenerates the skin layouts
#   3. packs everything into an .rmskin that Rainmeter installs with a double-click
# Needs Python 3.12+ on the build machine only.
param([string]$Version = "1.0.0", [string]$Python = "py")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv-build)) { & $Python -3.13 -m venv .venv-build }
$py = ".\.venv-build\Scripts\python.exe"
& $py -m pip install --disable-pip-version-check -q -r requirements-build.txt

& $py -m PyInstaller --noconfirm --clean --onedir --noconsole --name aiusage `
    --distpath build\dist --workpath build\work --specpath build src\aiusage.py
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$bin = "skin\AIUsageBar\@Resources\bin"
if (Test-Path $bin) { Remove-Item -Recurse -Force $bin }
New-Item -ItemType Directory -Force $bin | Out-Null
Copy-Item -Recurse build\dist\aiusage "$bin\aiusage"

& $py tools\gen_skins.py
& $py tools\make_rmskin.py $Version
