# =========================================================
# FLEX Installer
# Levy Lab
# =========================================================

$ErrorActionPreference = "Stop"

function Write-Log($Level, $Message, $Color="White") {
    $DateTime = Get-Date -Format "HH:mm:ss"
    Write-Host "[$DateTime] [$Level] $Message" -ForegroundColor $Color
}

function fail($text) {
    Write-Log "ERROR" $text "Red"
    Read-Host "Press Enter to exit"
    exit 1
}

# -------------------------
# Environment Initialization
# -------------------------
Write-Log "INFO" "Initializing system diagnostics..." "Gray"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Log "WARN" "Script is not running as Administrator. Installation may fail if permissions are restricted." "Yellow"
}

# Pre-declare dependency metrics
$pyStatus   = "Missing"
$pipStatus  = "Missing"
$gitStatus  = "Missing"
$vsStatus   = "Not installed (Optional)"
$flexStatus = "None detected"
$python     = $null
$criticalDependencyMissing = $false

# 1. Evaluate Python
foreach ($cmd in @("py", "python")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $python = $cmd; break }
}

if ($null -ne $python) {
    try {
        $pyPath = (Get-Command $python).Source
        $versionInfo = (Get-Item $pyPath).VersionInfo
        $verStr = if ($versionInfo.ProductMajorPart -and $versionInfo.ProductMajorPart -ne 0) { "$($versionInfo.ProductMajorPart).$($versionInfo.ProductMinorPart)" } else { ((& $python --version 2>&1) -replace "[^\d\.]", "").Trim() }
        
        if ([version]$verStr -lt [version]"3.10") {
            $pyStatus = "FAIL (v$verStr detected, requires 3.10+)"
            $criticalDependencyMissing = $true
        } else {
            $pyStatus = "Verified (v$verStr)"
        }
    } catch {
        $pyStatus = "Error reading properties"; $criticalDependencyMissing = $true
    }
} else {
    $criticalDependencyMissing = $true
}

# 2. Evaluate Pip
if ($null -ne $python -and $pyStatus -like "Verified*") {
    $pipOut = & $python -m pip --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $pipStatus = "Verified (v$(($pipOut -split ' ')[1]))"
    } else {
        $pipStatus = "Broken or missing package manager"; $criticalDependencyMissing = $true
    }
}

# 3. Evaluate Git
try {
    $gitOut = (git --version).Trim()
    $gitStatus = "Verified (v$(($gitOut -split ' ')[2]))"
} catch {
    $gitStatus = "Missing (Required to build dynamically)"; $criticalDependencyMissing = $true
}

# 4. Evaluate VSCode
if (Get-Command code -ErrorAction SilentlyContinue) {
    try {
        $codeOut = code --version
        $vsStatus = if ($codeOut) { "Verified (v$($codeOut[0].Trim()))" } else { "Detected (Version unknown)" }
    } catch { $vsStatus = "Detected (Version query blocked)" }
}

# 5. Evaluate Existing FLEX Metadata
if ($null -ne $python -and $pyStatus -like "Verified*") {
    $pipShow = & $python -m pip show flex 2>&1
    if ($LASTEXITCODE -eq 0) {
        $currentVer = ($pipShow | Select-String "^Version:").Line -replace "Version:\s*", ""
        $currentLoc = ($pipShow | Select-String "^Location:").Line -replace "Location:\s*", ""
        $flexStatus = "v$currentVer inside $currentLoc"
    }
}

# -------------------------
# Compute Output Colors (PS 5.1 Safe Method)
# -------------------------
$pyColor   = if ($pyStatus -like "Verified*") { "Green" } else { "Red" }
$pipColor  = if ($pipStatus -like "Verified*") { "Green" } else { "Red" }
$gitColor  = if ($gitStatus -like "Verified*") { "Green" } else { "Red" }
$vsColor   = if ($vsStatus -like "Verified*") { "Green" } else { "DarkGray" }
$flexColor = if ($flexStatus -ne "None detected") { "Cyan" } else { "DarkGray" }

# -------------------------
# Diagnostic Report Display
# -------------------------
Write-Host "`n=========================================================" -ForegroundColor "Gray"
Write-Host "                  SYSTEM COMPONENT REPORT                " -ForegroundColor "White"
Write-Host "=========================================================" -ForegroundColor "Gray"
Write-Host " [Prereq] Python Context:    $pyStatus" -ForegroundColor $pyColor
Write-Host " [Prereq] Pip Environment:   $pipStatus" -ForegroundColor $pipColor
Write-Host " [Prereq] Git Core Engine:   $gitStatus" -ForegroundColor $gitColor
Write-Host " [Prereq] VSCode Engine:   $vsStatus" -ForegroundColor $vsColor
Write-Host "---------------------------------------------------------" -ForegroundColor "Gray"
Write-Host " [FLEX] Existing FLEX:     $flexStatus" -ForegroundColor $flexColor
Write-Host "=========================================================`n" -ForegroundColor "Gray"

if ($criticalDependencyMissing) {
    fail "Structural prerequisite criteria unmet. Address missing packages before deploying."
}

Write-Log "SUCCESS" "System requirements confirmed. Proceeding to environment evaluation." "Green"

# -------------------------
# Virtual Environment Detection
# -------------------------
if ($null -ne $env:VIRTUAL_ENV) {
    Write-Log "INFO" "Active Virtual Environment detected:" "Cyan"
    Write-Log "INFO" "-> $env:VIRTUAL_ENV" "Cyan"
    if ((Read-Host "Install FLEX directly into this venv? (Y = venv / N = force system Python)") -match "^(n|N)$") {
        $python = "python"
        Write-Log "WARN" "Overriding environment selector: Switching execution context to system Python." "Yellow"
    }
}

# -------------------------
# Installation Target Selector
# -------------------------
Write-Host "`n Available Deployment Branches:"
Write-Host "  1) Stable (main)"
Write-Host "  2) Development (develop)"
$branch = if ((Read-Host "Select target channel [Default: 1]") -eq "2") { "develop" } else { "main" }

# -------------------------
# User Handshake for Existing Installation
# -------------------------
if ($flexStatus -ne "None detected" -and (Read-Host "Existing workspace layout detected. Proceed with reinstall? (Y/n)") -match "^(n|N)$") {
    Write-Log "INFO" "Execution aborted by user manual termination." "Gray"
    Read-Host "Press Enter to exit"
    exit 0
}

# -------------------------
# Deployment Subroutine
# -------------------------
Write-Log "INFO" "Upgrading underlying pipeline dependencies (pip)..." "Yellow"
& $python -m pip install --upgrade pip > $null 2>&1

Write-Log "INFO" "Fetching repository assets from remote branch: $branch..." "Yellow"
$repoUrl = "git+https://github.com/levylabpitt/FLEX.git@$branch"

& $python -m pip install --upgrade --force-reinstall $repoUrl
if ($LASTEXITCODE -ne 0) { fail "Remote dependency acquisition or compiling sequence failed." }

# -------------------------
# Validation & Handshake
# -------------------------
Write-Log "INFO" "Validating structural package alignment..." "Yellow"
$finalCheck = & $python -m pip show flex 2>&1
if ($LASTEXITCODE -ne 0) { fail "FLEX layout was populated, but verification engine failed to map structural details." }

$deployedVer = ($finalCheck | Select-String "^Version:").Line -replace "Version:\s*", ""
Write-Log "SUCCESS" "FLEX engine compilation and deployment successful v$deployedVer" "Green"
Write-Log "INFO" "Ready for workspace imports via import flex" "Cyan"

Read-Host "Press Enter to finalize deployment"