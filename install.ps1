# ==============================================================================
# FLEX Installer
# Levy Lab
# ==============================================================================

$ErrorActionPreference = "Stop"

function Write-Log([string]$Level, [string]$Message, [string]$Color="White") {
    $Timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$Timestamp] [$Level] $Message" -ForegroundColor $Color
}

function Invoke-NativeCommand([string]$Executable, [string]$Arguments) {
    try {
        $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
        $StartInfo.FileName = $Executable
        $StartInfo.Arguments = $Arguments
        $StartInfo.RedirectStandardOutput = $true
        $StartInfo.RedirectStandardError = $true
        $StartInfo.UseShellExecute = $false
        $StartInfo.CreateNoWindow = $true

        $Process = New-Object System.Diagnostics.Process
        $Process.StartInfo = $StartInfo
        
        $null = $Process.Start()
        $Output = $Process.StandardOutput.ReadToEnd()
        $ErrorOut = $Process.StandardError.ReadToEnd()
        $Process.WaitForExit()

        return @{
            ExitCode = $Process.ExitCode
            Output   = $Output.Trim()
            Error    = $ErrorOut.Trim()
        }
    } catch {
        return @{ ExitCode = -1; Output = ""; Error = $_.Exception.Message }
    }
}

function Terminate-Installation([string]$Message) {
    Write-Log "FATAL" $Message "Red"
    Write-Host "`nInstallation aborted. Resolving environment errors required." -ForegroundColor "Yellow"
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Log "INFO" "Initializing system diagnostics..." "Gray"

# Default States
$pyStatus   = "Missing or Corrupt (Requires 3.10+)"
$pipStatus  = "Missing"
$gitStatus  = "Missing"
$vsStatus   = "Not installed (Optional)"
$flexStatus = "None detected"
$PythonPath = $null

# ------------------------------------------------------------------------------
# 1. Component Discovery & Validation
# ------------------------------------------------------------------------------

# Identify Python without triggering Windows Store execution traps
foreach ($Cmd in @("py", "python")) {
    $Target = Get-Command $Cmd -ErrorAction SilentlyContinue
    if ($Target -and $Target.Source -notlike "*\Microsoft\WindowsApps\*") {
        $PythonPath = $Target.Source
        break
    }
}

# Advanced Registry Fallback if Path fails
if ($null -eq $PythonPath) {
    foreach ($Hive in @("HKLM:\SOFTWARE\Python\PythonCore", "HKCU:\SOFTWARE\Python\PythonCore")) {
        if (Test-Path $Hive) {
            $Versions = Get-ChildItem $Hive | Select-Object -ExpandProperty Name
            if ($Versions) {
                $Latest = $Versions | Sort-Object | Select-Object -Last 1
                $InstallPath = Get-ItemProperty -Path "$Hive\$($Latest.Split('\')[-1])\InstallPath" -Name "(Default)" -ErrorAction SilentlyContinue
                if ($InstallPath) {
                    $PythonPath = Join-Path $InstallPath.'(Default)' "python.exe"
                    if (Test-Path $PythonPath) { break }
                }
            }
        }
    }
}

# Evaluate Python Core Environment
if ($null -ne $PythonPath) {
    $PyCheck = Invoke-NativeCommand $PythonPath "-c `"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')`""
    if ($PyCheck.ExitCode -eq 0 -and $PyCheck.Output) {
        $PyVer = $PyCheck.Output
        if ([version]$PyVer -lt [version]"3.10") {
            $pyStatus = "FAIL (v$PyVer detected, requires 3.10+)"
        } else {
            $pyStatus = "Verified (v$PyVer)"
            
            # Evaluate Pip Context safely using isolation runner
            $PipCheck = Invoke-NativeCommand $PythonPath "-m pip --version"
            if ($PipCheck.ExitCode -eq 0 -and $PipCheck.Output) {
                $pipStatus = "Verified (v$($PipCheck.Output.Split(' ')[1]))"
            } else {
                $pipStatus = "Broken or Missing Package Manager"
            }
        }
    } else {
        $pyStatus = "Error evaluating runtime"
    }
}

# Evaluate Git Core
$GitCmd = Get-Command git -ErrorAction SilentlyContinue
if ($GitCmd) {
    $GitCheck = Invoke-NativeCommand $GitCmd.Source "--version"
    if ($GitCheck.ExitCode -eq 0 -and $GitCheck.Output -match "\d+\.\d+\.\d+") {
        $gitStatus = "Verified (v$($Matches[0]))"
    }
}

# Evaluate Visual Studio Code (Optional Environment Target)
$VsCmd = Get-Command code -ErrorAction SilentlyContinue
if ($VsCmd) {
    $VsCheck = Invoke-NativeCommand $VsCmd.Source "--version"
    if ($VsCheck.ExitCode -eq 0 -and $VsCheck.Output) {
        $vsStatus = "Verified (v$($VsCheck.Output.Split("`n")[0].Trim()))"
    }
}

# Evaluate Existing FLEX Footprint
if ($pyStatus -like "Verified*") {
    $FlexCheck = Invoke-NativeCommand $PythonPath "-c `"try: import flex; print(flex.__version__)\nexcept Exception: pass`""
    if ($FlexCheck.ExitCode -eq 0 -and $FlexCheck.Output) {
        $flexStatus = "v$($FlexCheck.Output)"
    }
}

# ------------------------------------------------------------------------------
# 2. Diagnostic Interface & Threshold Guard
# ------------------------------------------------------------------------------
$pyColor   = if ($pyStatus -like "Verified*") { "Green" } else { "Red" }
$pipColor  = if ($pipStatus -like "Verified*") { "Green" } else { "Red" }
$gitColor  = if ($gitStatus -like "Verified*") { "Green" } else { "Red" }
$vscodecolor = if ($gitStatus -like "Verified*") { "Green" } else { "Red" }
$flexColor = if ($flexStatus -ne "None detected") { "Cyan" } else { "DarkGray" }

Write-Host "`n=========================================================" -ForegroundColor "Gray"
Write-Host "                 SYSTEM COMPONENT REPORT                 " -ForegroundColor "White"
Write-Host "=========================================================" -ForegroundColor "Gray"
Write-Host " [Prereq] Python Context:    $pyStatus" -ForegroundColor $pyColor
Write-Host " [Prereq] Pip Environment:   $pipStatus" -ForegroundColor $pipColor
Write-Host " [Prereq] Git Core Engine:   $gitStatus" -ForegroundColor $gitColor
Write-Host " [Prereq] VSCode Editor:     $vsStatus" -ForegroundColor $vscodecolor
Write-Host "---------------------------------------------------------" -ForegroundColor "Gray"
Write-Host " [FLEX] Existing FLEX:       $flexStatus" -ForegroundColor $flexColor
Write-Host "=========================================================`n" -ForegroundColor "Gray"

if ($pyStatus -notlike "Verified*" -or $pipStatus -notlike "Verified*" -or $gitStatus -notlike "Verified*") {
    Terminate-Installation "Structural prerequisite criteria unmet. Please check missing items."
}

# ------------------------------------------------------------------------------
# 3. Execution Scope Context Selection
# ------------------------------------------------------------------------------
if ($null -ne $env:VIRTUAL_ENV) {
    Write-Log "INFO" "Active Virtual Environment context discovered: $env:VIRTUAL_ENV" "Cyan"
    $Selection = Read-Host "Install FLEX into this specific Virtual Environment? (Y/n)"
    if ($Selection -match "^(n|N)$") {
        Write-Log "INFO" "Sourcing global pipeline runtime environment..." "Yellow"
    }
}

Write-Host "`n Target Distribution Pipeline Channels:"
Write-Host " [1] Stable Release Branch (main)"
Write-Host " [2] Development Edge Branch (develop)"
$BranchSelection = Read-Host "Select channel [Default: 1]"
$Branch = if ($BranchSelection -eq "2") { "develop" } else { "main" }

if ($flexStatus -ne "None detected") {
    $ReinstallPrompt = Read-Host "FLEX framework instance detected. Force upgrade/reinstall package? (y/N)"
    if ($ReinstallPrompt -notmatch "^(y|Y)$") {
        Write-Log "INFO" "Deployment execution cancelled by user." "Gray"
        exit 0
    }
}

# ------------------------------------------------------------------------------
# 4. Framework Deployment Execution & Integrity Checks
# ------------------------------------------------------------------------------
Write-Log "INFO" "Updating underlying Pip management module..." "Yellow"
$UpgradePip = Invoke-NativeCommand $PythonPath "-m pip install --upgrade pip --quiet"
if ($UpgradePip.ExitCode -ne 0) {
    Write-Log "WARN" "Pip auto-update exited with exception code: $($UpgradePip.ExitCode). Continuing..." "Yellow"
}

Write-Log "INFO" "Deploying FLEX Framework Engine via Remote Repository ($Branch)..." "Yellow"
$RepoUrl = "git+https://github.com/levylabpitt/FLEX.git@$Branch"
$DeployTask = Invoke-NativeCommand $PythonPath "-m pip install --upgrade --force-reinstall `"$RepoUrl`""

if ($DeployTask.ExitCode -ne 0) {
    Terminate-Installation "Deployment routine failed.`nError Trace: $($DeployTask.Error)"
}

Write-Log "INFO" "Running integration verification checks..." "Yellow"
$VerifyTask = Invoke-NativeCommand $PythonPath "-c `"import flex; print(flex.__version__)`""

if ($VerifyTask.ExitCode -eq 0 -and $VerifyTask.Output) {
    Write-Log "SUCCESS" "FLEX Environment verification passed (v$($VerifyTask.Output))" "Green"
} else {
    Terminate-Installation "Verification check failed. Core files could not be structuralized by Python execution environment."
}

Write-Host "`n=========================================================" -ForegroundColor "Green"
Write-Log "SUCCESS" "FLEX Deployment Sequence Executed Successfully." "Green"
Write-Host "=========================================================" -ForegroundColor "Green"
Read-Host "`nPress Enter to finalize deployment and close terminal"