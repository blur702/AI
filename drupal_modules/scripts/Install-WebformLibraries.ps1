<#
.SYNOPSIS
    Installs all 12 Webform external libraries for Drupal.

.DESCRIPTION
    Downloads and installs CodeMirror, jQuery InputMask, Intl-Tel-Input,
    RateIt, Select2, TextCounter, Timepicker, Popper.js, Progress Tracker,
    Signature Pad, Tabby, and Tippy.js to the Drupal libraries directory.

.PARAMETER LibrariesPath
    Optional path to the libraries directory. If not specified, auto-detects
    based on Drupal root structure.

.PARAMETER Force
    Force reinstallation of libraries that already exist.

.EXAMPLE
    .\Install-WebformLibraries.ps1

.EXAMPLE
    .\Install-WebformLibraries.ps1 -LibrariesPath "C:\drupal\libraries"

.EXAMPLE
    .\Install-WebformLibraries.ps1 -Force
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$LibrariesPath,

    [Parameter(Mandatory = $false)]
    [switch]$Force
)

# Library versions
$Versions = @{
    CodeMirror      = "5.65.12"
    InputMask       = "5.0.9"
    IntlTelInput    = "17.0.19"
    RateIt          = "1.1.5"
    Select2         = "4.0.13"
    TextCounter     = "0.9.1"
    Timepicker      = "1.14.0"
    PopperJS        = "2.11.6"
    ProgressTracker = "2.0.7"
    SignaturePad    = "2.3.0"
    Tabby           = "12.0.3"
    TippyJS         = "6.3.7"
}

# Counters
$Script:Installed = 0
$Script:Skipped = 0
$Script:Failed = 0

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Type = "Info"
    )

    switch ($Type) {
        "Success" { Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
        "Warning" { Write-Host "[WARNING] $Message" -ForegroundColor Yellow }
        "Error"   { Write-Host "[ERROR] $Message" -ForegroundColor Red }
        "Info"    { Write-Host "[INFO] $Message" -ForegroundColor Cyan }
        default   { Write-Host $Message }
    }
}

function Get-LibrariesDirectory {
    if ($LibrariesPath) {
        return $LibrariesPath
    }

    $currentDir = Get-Location

    # Check for standard Drupal structure
    if ((Test-Path "$currentDir\index.php") -and (Test-Path "$currentDir\core")) {
        return "$currentDir\libraries"
    }

    # Check for web subdirectory structure
    if ((Test-Path "$currentDir\web\index.php") -and (Test-Path "$currentDir\web\core")) {
        return "$currentDir\web\libraries"
    }

    Write-ColorOutput "Not in Drupal root directory. Please specify -LibrariesPath or cd to Drupal root." -Type "Error"
    exit 1
}

function Install-CodeMirror {
    $libDir = Join-Path $Script:LibsDir "codemirror"
    $testFile = Join-Path $libDir "lib\codemirror.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "CodeMirror already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing CodeMirror $($Versions.CodeMirror)..." -Type "Info"

    try {
        $tempDir = Join-Path $env:TEMP "webform_libs"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        $zipPath = Join-Path $tempDir "codemirror.zip"
        $url = "https://github.com/codemirror/codemirror5/archive/refs/tags/$($Versions.CodeMirror).zip"

        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

        $extractedDir = Join-Path $tempDir "codemirror5-$($Versions.CodeMirror)"

        New-Item -ItemType Directory -Path $libDir -Force | Out-Null
        Copy-Item -Path "$extractedDir\lib" -Destination $libDir -Recurse -Force
        Copy-Item -Path "$extractedDir\mode" -Destination $libDir -Recurse -Force

        Remove-Item -Path $tempDir -Recurse -Force

        Write-ColorOutput "CodeMirror installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "CodeMirror installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-InputMask {
    $libDir = Join-Path $Script:LibsDir "jquery.inputmask\dist"
    $testFile = Join-Path $libDir "jquery.inputmask.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "InputMask already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing jQuery InputMask $($Versions.InputMask)..." -Type "Info"

    try {
        New-Item -ItemType Directory -Path $libDir -Force | Out-Null

        $url = "https://cdnjs.cloudflare.com/ajax/libs/jquery.inputmask/$($Versions.InputMask)/jquery.inputmask.min.js"
        Invoke-WebRequest -Uri $url -OutFile $testFile -UseBasicParsing

        Write-ColorOutput "InputMask installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "InputMask installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-IntlTelInput {
    $libDir = Join-Path $Script:LibsDir "jquery.intl-tel-input"
    $testFile = Join-Path $libDir "build\js\intlTelInput.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "Intl-Tel-Input already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing jQuery Intl-Tel-Input $($Versions.IntlTelInput)..." -Type "Info"

    try {
        $tempDir = Join-Path $env:TEMP "webform_libs"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        $zipPath = Join-Path $tempDir "intl-tel-input.zip"
        $url = "https://github.com/jackocnr/intl-tel-input/archive/refs/tags/v$($Versions.IntlTelInput).zip"

        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

        $extractedDir = Join-Path $tempDir "intl-tel-input-$($Versions.IntlTelInput)"

        New-Item -ItemType Directory -Path $libDir -Force | Out-Null
        Copy-Item -Path "$extractedDir\build" -Destination $libDir -Recurse -Force

        Remove-Item -Path $tempDir -Recurse -Force

        Write-ColorOutput "Intl-Tel-Input installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "Intl-Tel-Input installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-RateIt {
    $libDir = Join-Path $Script:LibsDir "jquery.rateit"
    $testFile = Join-Path $libDir "scripts\jquery.rateit.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "RateIt already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing jQuery RateIt $($Versions.RateIt)..." -Type "Info"

    try {
        New-Item -ItemType Directory -Path "$libDir\scripts" -Force | Out-Null
        New-Item -ItemType Directory -Path "$libDir\styles" -Force | Out-Null

        $jsUrl = "https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/$($Versions.RateIt)/jquery.rateit.min.js"
        $cssUrl = "https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/$($Versions.RateIt)/rateit.css"

        Invoke-WebRequest -Uri $jsUrl -OutFile $testFile -UseBasicParsing
        Invoke-WebRequest -Uri $cssUrl -OutFile "$libDir\styles\rateit.css" -UseBasicParsing

        Write-ColorOutput "RateIt installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "RateIt installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-Select2 {
    $libDir = Join-Path $Script:LibsDir "jquery.select2"
    $testFile = Join-Path $libDir "dist\js\select2.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "Select2 already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing jQuery Select2 $($Versions.Select2)..." -Type "Info"

    try {
        $tempDir = Join-Path $env:TEMP "webform_libs"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        $zipPath = Join-Path $tempDir "select2.zip"
        $url = "https://github.com/select2/select2/archive/refs/tags/$($Versions.Select2).zip"

        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

        $extractedDir = Join-Path $tempDir "select2-$($Versions.Select2)"

        New-Item -ItemType Directory -Path $libDir -Force | Out-Null
        Copy-Item -Path "$extractedDir\dist" -Destination $libDir -Recurse -Force

        Remove-Item -Path $tempDir -Recurse -Force

        Write-ColorOutput "Select2 installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "Select2 installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-TextCounter {
    $libDir = Join-Path $Script:LibsDir "jquery.textcounter"
    $testFile = Join-Path $libDir "textcounter.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "TextCounter already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing jQuery TextCounter $($Versions.TextCounter)..." -Type "Info"

    try {
        $tempDir = Join-Path $env:TEMP "webform_libs"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        $zipPath = Join-Path $tempDir "textcounter.zip"
        $url = "https://github.com/ractoon/jQuery-Text-Counter/archive/refs/tags/$($Versions.TextCounter).zip"

        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

        $extractedDir = Join-Path $tempDir "jQuery-Text-Counter-$($Versions.TextCounter)"

        New-Item -ItemType Directory -Path $libDir -Force | Out-Null
        Copy-Item -Path "$extractedDir\textcounter.min.js" -Destination $libDir -Force

        Remove-Item -Path $tempDir -Recurse -Force

        Write-ColorOutput "TextCounter installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "TextCounter installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-Timepicker {
    $libDir = Join-Path $Script:LibsDir "jquery.timepicker"
    $testFile = Join-Path $libDir "jquery.timepicker.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "Timepicker already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing jQuery Timepicker $($Versions.Timepicker)..." -Type "Info"

    try {
        $tempDir = Join-Path $env:TEMP "webform_libs"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        $zipPath = Join-Path $tempDir "timepicker.zip"
        $url = "https://github.com/jonthornton/jquery-timepicker/archive/refs/tags/$($Versions.Timepicker).zip"

        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

        $extractedDir = Join-Path $tempDir "jquery-timepicker-$($Versions.Timepicker)"

        New-Item -ItemType Directory -Path $libDir -Force | Out-Null
        Copy-Item -Path "$extractedDir\jquery.timepicker.min.js" -Destination $libDir -Force
        Copy-Item -Path "$extractedDir\jquery.timepicker.min.css" -Destination $libDir -Force

        Remove-Item -Path $tempDir -Recurse -Force

        Write-ColorOutput "Timepicker installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "Timepicker installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-PopperJS {
    $libDir = Join-Path $Script:LibsDir "popperjs\dist\umd"
    $testFile = Join-Path $libDir "popper.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "Popper.js already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing Popper.js $($Versions.PopperJS)..." -Type "Info"

    try {
        New-Item -ItemType Directory -Path $libDir -Force | Out-Null

        $url = "https://cdn.jsdelivr.net/npm/@popperjs/core@$($Versions.PopperJS)/dist/umd/popper.min.js"
        Invoke-WebRequest -Uri $url -OutFile $testFile -UseBasicParsing

        Write-ColorOutput "Popper.js installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "Popper.js installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-ProgressTracker {
    $libDir = Join-Path $Script:LibsDir "progress-tracker"
    $testFile = Join-Path $libDir "src\progress-tracker.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "Progress Tracker already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing Progress Tracker $($Versions.ProgressTracker)..." -Type "Info"

    try {
        $tempDir = Join-Path $env:TEMP "webform_libs"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        $zipPath = Join-Path $tempDir "progress-tracker.zip"
        $url = "https://github.com/NigelOToole/progress-tracker/archive/refs/tags/$($Versions.ProgressTracker).zip"

        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

        $extractedDir = Join-Path $tempDir "progress-tracker-$($Versions.ProgressTracker)"

        New-Item -ItemType Directory -Path $libDir -Force | Out-Null
        Copy-Item -Path "$extractedDir\src" -Destination $libDir -Recurse -Force

        Remove-Item -Path $tempDir -Recurse -Force

        Write-ColorOutput "Progress Tracker installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "Progress Tracker installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-SignaturePad {
    $libDir = Join-Path $Script:LibsDir "signature_pad"
    $testFile = Join-Path $libDir "dist\signature_pad.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "Signature Pad already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing Signature Pad $($Versions.SignaturePad)..." -Type "Info"

    try {
        $tempDir = Join-Path $env:TEMP "webform_libs"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        $zipPath = Join-Path $tempDir "signature_pad.zip"
        $url = "https://github.com/szimek/signature_pad/archive/refs/tags/v$($Versions.SignaturePad).zip"

        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

        $extractedDir = Join-Path $tempDir "signature_pad-$($Versions.SignaturePad)"

        New-Item -ItemType Directory -Path $libDir -Force | Out-Null
        Copy-Item -Path "$extractedDir\dist" -Destination $libDir -Recurse -Force

        Remove-Item -Path $tempDir -Recurse -Force

        Write-ColorOutput "Signature Pad installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "Signature Pad installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-Tabby {
    $libDir = Join-Path $Script:LibsDir "tabby"
    $testFile = Join-Path $libDir "dist\js\tabby.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "Tabby already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing Tabby $($Versions.Tabby)..." -Type "Info"

    try {
        $tempDir = Join-Path $env:TEMP "webform_libs"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        $zipPath = Join-Path $tempDir "tabby.zip"
        $url = "https://github.com/cferdinandi/tabby/archive/refs/tags/$($Versions.Tabby).zip"

        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

        $extractedDir = Join-Path $tempDir "tabby-$($Versions.Tabby)"

        New-Item -ItemType Directory -Path $libDir -Force | Out-Null
        Copy-Item -Path "$extractedDir\dist" -Destination $libDir -Recurse -Force

        Remove-Item -Path $tempDir -Recurse -Force

        Write-ColorOutput "Tabby installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "Tabby installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Install-TippyJS {
    $libDir = Join-Path $Script:LibsDir "tippyjs\dist"
    $testFile = Join-Path $libDir "tippy.umd.min.js"

    if ((Test-Path $testFile) -and -not $Force) {
        Write-ColorOutput "Tippy.js already installed, skipping" -Type "Warning"
        $Script:Skipped++
        return
    }

    Write-ColorOutput "Installing Tippy.js $($Versions.TippyJS)..." -Type "Info"

    try {
        New-Item -ItemType Directory -Path $libDir -Force | Out-Null

        $jsUrl = "https://cdn.jsdelivr.net/npm/tippy.js@$($Versions.TippyJS)/dist/tippy.umd.min.js"
        $cssUrl = "https://cdn.jsdelivr.net/npm/tippy.js@$($Versions.TippyJS)/dist/tippy.css"

        Invoke-WebRequest -Uri $jsUrl -OutFile $testFile -UseBasicParsing
        Invoke-WebRequest -Uri $cssUrl -OutFile "$libDir\tippy.css" -UseBasicParsing

        Write-ColorOutput "Tippy.js installed" -Type "Success"
        $Script:Installed++
    }
    catch {
        Write-ColorOutput "Tippy.js installation failed: $_" -Type "Error"
        $Script:Failed++
    }
}

function Test-Installation {
    Write-Host ""
    Write-Host "=============================================="
    Write-Host "  Installation Verification"
    Write-Host "=============================================="

    $checks = @(
        @{ Name = "CodeMirror"; File = "codemirror\lib\codemirror.js" }
        @{ Name = "InputMask"; File = "jquery.inputmask\dist\jquery.inputmask.min.js" }
        @{ Name = "Intl-Tel-Input"; File = "jquery.intl-tel-input\build\js\intlTelInput.min.js" }
        @{ Name = "RateIt"; File = "jquery.rateit\scripts\jquery.rateit.min.js" }
        @{ Name = "Select2"; File = "jquery.select2\dist\js\select2.min.js" }
        @{ Name = "TextCounter"; File = "jquery.textcounter\textcounter.min.js" }
        @{ Name = "Timepicker"; File = "jquery.timepicker\jquery.timepicker.min.js" }
        @{ Name = "Popper.js"; File = "popperjs\dist\umd\popper.min.js" }
        @{ Name = "Progress Tracker"; File = "progress-tracker\src\progress-tracker.js" }
        @{ Name = "Signature Pad"; File = "signature_pad\dist\signature_pad.min.js" }
        @{ Name = "Tabby"; File = "tabby\dist\js\tabby.min.js" }
        @{ Name = "Tippy.js"; File = "tippyjs\dist\tippy.umd.min.js" }
    )

    $passed = 0
    foreach ($check in $checks) {
        $fullPath = Join-Path $Script:LibsDir $check.File
        if (Test-Path $fullPath) {
            Write-Host "  [OK] $($check.Name)" -ForegroundColor Green
            $passed++
        }
        else {
            Write-Host "  [X] $($check.Name)" -ForegroundColor Red
        }
    }

    Write-Host ""
    Write-Host "Total: $passed / $($checks.Count) libraries installed"
}

# Main execution
Write-Host "=============================================="
Write-Host "  Webform External Libraries Installer"
Write-Host "=============================================="
Write-Host ""

$Script:LibsDir = Get-LibrariesDirectory
Write-ColorOutput "Libraries directory: $Script:LibsDir" -Type "Info"

# Create libraries directory if needed
if (-not (Test-Path $Script:LibsDir)) {
    New-Item -ItemType Directory -Path $Script:LibsDir -Force | Out-Null
}

Write-Host ""
Write-Host "Installing libraries..."
Write-Host ""

# Install all libraries
Install-CodeMirror
Install-InputMask
Install-IntlTelInput
Install-RateIt
Install-Select2
Install-TextCounter
Install-Timepicker
Install-PopperJS
Install-ProgressTracker
Install-SignaturePad
Install-Tabby
Install-TippyJS

# Verify installation
Test-Installation

Write-Host ""
Write-Host "=============================================="
Write-Host "  Summary"
Write-Host "=============================================="
Write-Host "  Installed: $Script:Installed" -ForegroundColor Green
Write-Host "  Skipped: $Script:Skipped" -ForegroundColor Yellow
Write-Host "  Failed: $Script:Failed" -ForegroundColor Red
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Clear Drupal cache: drush cr"
Write-Host "  2. Check status: /admin/reports/status"
Write-Host ""
