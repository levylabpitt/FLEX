# ==============================================================================
# FLEX Installer  -  Levy Lab
# Author: Pubudu Wijesinghe
#
#   Usage:   irm flex.levylab.org/install.ps1 | iex
#
#   Optional environment overrides (set before piping):
#     $env:FLEX_BRANCH = 'develop'   # install from a specific branch (default: main)
#     $env:FLEX_YES    = '1'         # non-interactive: accept all defaults
# ==============================================================================

& {
    # Pin error handling so the caller's session preferences (e.g. a profile that
    # sets 'Stop') can't turn a native command's stderr into a fatal error and
    # break Python detection. Scoped to this block only.
    $ErrorActionPreference = 'Continue'

    $RepoOwner = 'levylabpitt'
    $RepoName  = 'FLEX'

    # --- logging ---------------------------------------------------------------
    function Log  ([string]$m, [string]$c = 'Gray') { Write-Host "  $m" -ForegroundColor $c }
    function Ok   ([string]$m) { Write-Host "  [ OK ] $m"   -ForegroundColor Green }
    function Warn ([string]$m) { Write-Host "  [WARN] $m"   -ForegroundColor Yellow }
    function Fail ([string]$m) {
        Write-Host ""
        Write-Host "  [FAIL] $m" -ForegroundColor Red
        Write-Host "  Installation aborted." -ForegroundColor Yellow
    }

    # Run a native executable with array args (robust quoting on PS 5 & 7).
    function Invoke-Exe {
        param([string]$FilePath, [string[]]$Arguments = @())
        try {
            $global:LASTEXITCODE = 0
            $out = & $FilePath @Arguments 2>&1
            [pscustomobject]@{
                ExitCode = $LASTEXITCODE
                Output   = (($out | Out-String) -replace "`r", '').Trim()
            }
        } catch {
            [pscustomobject]@{ ExitCode = -1; Output = $_.Exception.Message }
        }
    }

    # Run a native executable attached to the current console so its output
    # (including pip's live progress bars) streams in real time. The caller sees
    # the actual install as it happens. Returns the process exit code.
    function Invoke-ExeLive {
        param([string]$FilePath, [string[]]$Arguments = @())
        try {
            $p = Start-Process -FilePath $FilePath -ArgumentList $Arguments -NoNewWindow -PassThru
            $null = $p.Handle          # cache handle so ExitCode is populated after exit
            $p.WaitForExit()
            return $p.ExitCode
        } catch {
            Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
            return -1
        }
    }

    # Probe a Python invocation; return its version + real executable, or $null.
    function Test-Python {
        param([string]$Exe, [string[]]$Prefix = @())
        # CRITICAL: pass NO double quotes in the -c snippet. Windows PowerShell 5.1
        # strips embedded double quotes when building a native command line, which
        # corrupts the code (e.g. "%s" -> %s -> SyntaxError). Tab-separate the
        # fields with chr(9) instead of a quoted delimiter - no quotes needed.
        $code = 'import sys;print(sys.version_info[0],sys.version_info[1],sys.version_info[2],sys.executable,sep=chr(9))'
        $r = Invoke-Exe $Exe (@($Prefix) + @('-c', $code))
        if ($r.ExitCode -ne 0) { return $null }
        $line = ($r.Output -split "`n" | Where-Object { $_ -match "^\d+`t\d+`t\d+`t" } | Select-Object -First 1)
        if (-not $line -or $line -notmatch "^(\d+)`t(\d+)`t(\d+)`t(.+)$") { return $null }
        [pscustomobject]@{
            Exe     = $Exe
            Prefix  = $Prefix
            Version = [version]"$($Matches[1]).$($Matches[2]).$($Matches[3])"
            Path    = $Matches[4].Trim()
        }
    }

    # Read a CLI app's version (first numeric line of its --version output).
    function Get-AppVersion {
        param([string]$Command, [string[]]$Paths = @())
        $exe = (Get-Command $Command -ErrorAction SilentlyContinue).Source
        if (-not $exe) { foreach ($p in $Paths) { if ($p -and (Test-Path $p)) { $exe = $p; break } } }
        if (-not $exe) { return $null }
        $r = Invoke-Exe $exe @('--version')
        if ($r.ExitCode -ne 0) { return $null }
        $line = ($r.Output -split "`n" | Where-Object { $_ -match '\d+\.\d+' } | Select-Object -First 1)
        if ($line) { $line.Trim() } else { 'installed' }
    }

    function Read-Default {
        param([string]$Prompt, [string]$Default)
        if ($env:FLEX_YES -or -not [Environment]::UserInteractive) { return $Default }
        $ans = Read-Host $Prompt
        if ([string]::IsNullOrWhiteSpace($ans)) { return $Default }
        $ans
    }

    Write-Host ""
    Write-Host "  ===============================================" -ForegroundColor Cyan
    Write-Host "                 FLEX  Installer                 " -ForegroundColor White
    Write-Host "  ===============================================" -ForegroundColor Cyan
    Write-Host ""

    # --- 1. Discover every plausible Python, pick the best >= 3.10 -------------
    Log "Locating a suitable Python (3.10+)..."

    $invocations = New-Object System.Collections.Generic.List[object]
    $seen = New-Object System.Collections.Generic.HashSet[string]
    function Add-Invocation { param([string]$Exe, [string[]]$Prefix = @())
        $key = ($Exe + '|' + ($Prefix -join ' ')).ToLowerInvariant()
        if ($seen.Add($key)) { $invocations.Add(@{ Exe = $Exe; Prefix = $Prefix }) }
    }

    # (a) The 'py' launcher (handles version selection itself).
    if (Get-Command py -ErrorAction SilentlyContinue) { Add-Invocation 'py' @('-3') }

    # (b) python / python3 on PATH. NOTE: do not exclude \WindowsApps\ by path -
    #     a real Microsoft Store Python also lives there and works fine. The
    #     "install me" Store stub fails the probe below (exits 9009, prints no
    #     version), so Test-Python filters it out without skipping real installs.
    foreach ($name in 'python', 'python3') {
        foreach ($c in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
            if ($c.Source) { Add-Invocation $c.Source }
        }
    }

    # (c) Registry (per-machine, per-user, 32-bit hive).
    $hives = @(
        'HKLM:\SOFTWARE\Python\PythonCore',
        'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore',
        'HKCU:\SOFTWARE\Python\PythonCore'
    )
    foreach ($hive in $hives) {
        if (-not (Test-Path $hive)) { continue }
        foreach ($ver in Get-ChildItem $hive -ErrorAction SilentlyContinue) {
            $ip = Get-ItemProperty "$($ver.PSPath)\InstallPath" -ErrorAction SilentlyContinue
            if (-not $ip) { continue }
            $exe = $ip.ExecutablePath
            if (-not $exe) { $exe = Join-Path $ip.'(default)' 'python.exe' }
            if ($exe -and (Test-Path $exe)) { Add-Invocation $exe }
        }
    }

    # (d) Common install locations.
    $globs = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:ProgramFiles\Python3*\python.exe",
        "${env:ProgramFiles(x86)}\Python3*\python.exe",
        "C:\Python3*\python.exe"
    )
    foreach ($g in $globs) {
        foreach ($f in @(Get-ChildItem $g -ErrorAction SilentlyContinue)) { Add-Invocation $f.FullName }
    }

    # Probe candidates; keep those >= 3.10, dedup by real executable, pick newest.
    $found = @{}
    foreach ($inv in $invocations) {
        $info = Test-Python -Exe $inv.Exe -Prefix $inv.Prefix
        if ($info -and $info.Version -ge [version]'3.10') {
            $k = $info.Path.ToLowerInvariant()
            if (-not $found.ContainsKey($k) -or $info.Version -gt $found[$k].Version) { $found[$k] = $info }
        }
    }
    $python = $found.Values | Sort-Object Version -Descending | Select-Object -First 1

    if (-not $python) {
        Fail "No Python 3.10+ was found on this system."
        Write-Host ""
        Write-Host "  Install Python from https://www.python.org/downloads/ (check" -ForegroundColor Yellow
        Write-Host "  'Add python.exe to PATH'), or run:  winget install Python.Python.3.12" -ForegroundColor Yellow
        Write-Host "  Then re-run this installer." -ForegroundColor Yellow
        return
    }
    # Use the resolved real executable for everything from here on.
    $py = $python.Path

    # --- 2. Ensure pip ---------------------------------------------------------
    if ((Invoke-Exe $py @('-m', 'pip', '--version')).ExitCode -ne 0) {
        Log "pip not found; bootstrapping with ensurepip..."
        $ep = Invoke-Exe $py @('-m', 'ensurepip', '--upgrade')
        if ((Invoke-Exe $py @('-m', 'pip', '--version')).ExitCode -ne 0) {
            Fail "Could not provision pip for this Python.`n$($ep.Output)"
            return
        }
    }
    # Quietly upgrade pip itself (non-fatal).
    $up = Invoke-Exe $py @('-m', 'pip', 'install', '--upgrade', 'pip', '--quiet', '--disable-pip-version-check')
    if ($up.ExitCode -ne 0) { Warn "Could not upgrade pip; continuing." }

    # --- 3. Detect tooling + existing FLEX, then report environment ------------
    $vscode = Get-AppVersion 'code' @(
        "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd",
        "$env:ProgramFiles\Microsoft VS Code\bin\code.cmd",
        "${env:ProgramFiles(x86)}\Microsoft VS Code\bin\code.cmd"
    )

    $flexProbe = Invoke-Exe $py @('-c', 'import importlib.metadata as m; print(m.version(''flex''))')
    if ($flexProbe.ExitCode -eq 0 -and $flexProbe.Output) { $flexVer = $flexProbe.Output } else { $flexVer = $null }

    Write-Host ""
    Write-Host "  Environment" -ForegroundColor White
    Write-Host ("    Python   : v{0}" -f $python.Version) -ForegroundColor Green
    Write-Host ("               {0}" -f $py)              -ForegroundColor DarkGray
    if ($vscode) { Write-Host ("    VS Code  : v{0}" -f $vscode) -ForegroundColor Green }
    else { Write-Host "    VS Code  : not found  (recommended: https://code.visualstudio.com)" -ForegroundColor Yellow }
    if ($flexVer) { Write-Host ("    FLEX     : v{0}  (already installed - will be upgraded)" -f $flexVer) -ForegroundColor Cyan }
    else { Write-Host "    FLEX     : not installed" -ForegroundColor DarkGray }
    if ($env:VIRTUAL_ENV) { Write-Host ("    Target   : venv -> {0}" -f $env:VIRTUAL_ENV) -ForegroundColor Cyan }

    # --- 4. Choose branch ------------------------------------------------------
    $branch = $env:FLEX_BRANCH
    if ([string]::IsNullOrWhiteSpace($branch)) {
        Write-Host ""
        Log "Release channel:  [1] main (stable)   [2] develop (edge)"
        if ((Read-Default "  Select channel [1] or Press Ctrl + C to abort" '1') -eq '2') { $branch = 'develop' } else { $branch = 'main' }
    }

    # --- 5. Install from the GitHub zip archive (no Git needed) ----------------
    $archive = "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$branch.zip"
    Write-Host ""
    Log "Installing FLEX from '$branch' - downloading packages, this can take a few minutes..." 'Yellow'
    Write-Host "  ----------------------------- pip ----------------------------" -ForegroundColor DarkGray

    # Pass 1: install/upgrade dependencies (and FLEX). Output streams live so the
    # user watches the real download/build progress instead of a blank screen.
    $code = Invoke-ExeLive $py @('-m', 'pip', 'install', '--upgrade', $archive)
    if ($code -ne 0 -and (Get-Command git -ErrorAction SilentlyContinue)) {
        Warn "Archive install failed; retrying via Git..."
        $code = Invoke-ExeLive $py @('-m', 'pip', 'install', '--upgrade', "git+https://github.com/$RepoOwner/$RepoName.git@$branch")
    }
    if ($code -ne 0) {
        Write-Host "  --------------------------------------------------------------" -ForegroundColor DarkGray
        Fail "Installation failed - see the pip output above for the cause."
        return
    }

    # Pass 2: force-refresh the FLEX package only, so branch updates without a
    # version bump still land (skips reinstalling the heavy dependency tree).
    $code = Invoke-ExeLive $py @('-m', 'pip', 'install', '--upgrade', '--force-reinstall', '--no-deps', '--quiet', $archive)
    Write-Host "  --------------------------------------------------------------" -ForegroundColor DarkGray
    if ($code -ne 0) { Warn "Could not force-refresh FLEX package; existing copy retained." }

    # --- 6. Verify -------------------------------------------------------------
    $verify = Invoke-Exe $py @('-c', 'import flex, importlib.metadata as m; print(m.version(''flex''))')
    if ($verify.ExitCode -ne 0) {
        Fail "FLEX imported but could not be verified.`n$($verify.Output)"
        return
    }

    Write-Host ""
    Write-Host "  ===============================================" -ForegroundColor Green
    Ok "FLEX $($verify.Output) installed successfully."
    Write-Host "  ===============================================" -ForegroundColor Green
    Write-Host ""
}
