# =========================================================
# FLEX Installer
# Levy Lab
# =========================================================

$ErrorActionPreference = "Stop"

function msg($icon, $text, $color="White") {
    Write-Host "$icon  $text" -ForegroundColor $color
}

function fail($text) {
    msg "✖" $text Red
    Read-Host "Press Enter to exit"
    exit 1
}

# -------------------------
# Python detection
# -------------------------
$python = $null

foreach ($cmd in @("py", "python")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        try {
            & $cmd -c "import sys" | Out-Null
            $python = $cmd
            break
        } catch {}
    }
}

if (-not $python) {
    fail "Python not found (install Python 3.10+ or enable py launcher)"
}

# Python version display
try {
    $pyVer = & $python -c "import sys; print(sys.version.split()[0])"
    msg "✔" "Python ($python) $pyVer" Green
} catch {
    fail "Unable to determine Python version"
}

# version check
$ver = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([double]$ver -lt 3.10) {
    fail "Python $ver detected (requires 3.10+)"
}

# -------------------------
# pip check
# -------------------------
& $python -m pip --version *> $null
if ($LASTEXITCODE -ne 0) { fail "pip not working" }
msg "✔" "pip OK" Green

# -------------------------
# Git check + version
# -------------------------
try {
    $gitVer = git --version
    msg "✔" "$gitVer" Green
} catch {
    fail "Git not installed"
}

# -------------------------
# VSCode check + version
# -------------------------
if (Get-Command code -ErrorAction SilentlyContinue) {
    try {
        $vscodeVer = code --version | Select-Object -First 1
        msg "✔" "VSCode $vscodeVer" Green
    } catch {
        msg "⚠" "VSCode detected (version unknown)" Yellow
    }
} else {
    msg "⚠" "VSCode not installed (optional)" Yellow
}

msg "✔" "Prerequisites OK" Green

# -------------------------
# venv detection
# -------------------------
$isVenv = $env:VIRTUAL_ENV -ne $null

if ($isVenv) {
    msg "ℹ" "Virtual environment detected:" Cyan
    msg "ℹ" $env:VIRTUAL_ENV Cyan

    $choice = Read-Host "Install FLEX here? (Y = venv / N = system Python)"

    if ($choice -match "^(n|N)$") {
        $python = "python"
        msg "ℹ" "Switching to system Python" Yellow
    }
}

# -------------------------
# install options
# -------------------------
Write-Host ""
Write-Host "1) Stable (main)"
Write-Host "2) Development (develop)"

$choice = Read-Host "Select [1]"
$branch = if ($choice -eq "2") { "develop" } else { "main" }

# -------------------------
# FLEX detection
# -------------------------
$info = & $python -c @"
import json, importlib.metadata
try:
    import flex
    print(json.dumps({
        "v": importlib.metadata.version("flex"),
        "p": flex.__file__
    }))
except:
    print(json.dumps({}))
"@

$flex = $info | ConvertFrom-Json

if ($flex.v) {
    msg "✔" "Existing FLEX detected ($($flex.v))" Green
    msg "ℹ" "Location: $($flex.p)" Cyan

    if ((Read-Host "Reinstall? (Y/n)") -match "^(n|N)$") {
        exit 0
    }
}

# -------------------------
# install FLEX
# -------------------------
msg "..." "Installing FLEX ($branch)" Yellow

& $python -m pip install --upgrade pip | Out-Null

& $python -m pip install `
    --upgrade `
    --force-reinstall `
    "git+https://github.com/levylabpitt/FLEX.git@$branch"

if ($LASTEXITCODE -ne 0) {
    fail "FLEX installation failed"
}

# -------------------------
# verify
# -------------------------
& $python -c "import flex"
if ($LASTEXITCODE -ne 0) {
    fail "FLEX installed but import failed"
}

msg "✔" "FLEX installation successful" Green
msg "ℹ" "import flex" Cyan

Read-Host "Press Enter to finish"