<#
.SYNOPSIS
    Ollama Model Loader with Progress Indicators for Roo Code
.DESCRIPTION
    Pre-loads Ollama models into VRAM with visual progress feedback.
    Supports loading specific models or all local models configured in Roo Code.
.EXAMPLE
    .\ollama-model-loader.ps1                           # Interactive menu
    .\ollama-model-loader.ps1 -Model qwen3-coder:30b    # Load specific model
    .\ollama-model-loader.ps1 -Model qwen3-coder:30b -KeepAlive 7200  # Keep for 2 hours
    .\ollama-model-loader.ps1 -List                     # List available models
    .\ollama-model-loader.ps1 -Status                   # Show loaded models
    .\ollama-model-loader.ps1 -Unload -Model qwen3-coder:30b  # Unload model
#>

param(
    [string]$Model,
    [switch]$List,
    [switch]$Status,
    [switch]$Unload,
    [int]$KeepAlive = 3600,  # Keep model loaded for 1 hour by default (seconds)
    [string]$OllamaUrl = "http://localhost:11434",
    # Filter patterns for interactive menu (models matching any pattern are shown)
    [string[]]$ModelFilter = @('qwen', 'coder', 'code', 'llama', 'dolphin', 'gemma', 'gpt-oss')
)

# Colors for output
$colors = @{
    Success = "Green"
    Error = "Red"
    Warning = "Yellow"
    Info = "Cyan"
    Progress = "Magenta"
}

function Write-ColorOutput {
    <#
    .SYNOPSIS
        Write colored output to the console
    .PARAMETER Message
        The message to display
    .PARAMETER Color
        The color to use for the message
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Message,

        [Parameter()]
        [ValidateSet('Black', 'DarkBlue', 'DarkGreen', 'DarkCyan', 'DarkRed', 'DarkMagenta', 'DarkYellow', 'Gray', 'DarkGray', 'Blue', 'Green', 'Cyan', 'Red', 'Magenta', 'Yellow', 'White')]
        [string]$Color = "White"
    )

    try {
        Write-Host $Message -ForegroundColor $Color
    }
    catch {
        # Fallback to plain output if color fails
        Write-Host $Message
    }
}

function Show-Progress {
    param(
        [string]$Activity,
        [string]$Status,
        [int]$PercentComplete = -1
    )

    if ($PercentComplete -ge 0) {
        Write-Progress -Activity $Activity -Status $Status -PercentComplete $PercentComplete
    } else {
        # Indeterminate progress - show spinner
        $spinner = @('|', '/', '-', '\')
        $i = [int]((Get-Date).Millisecond / 250) % 4
        Write-Host "`r$($spinner[$i]) $Activity - $Status" -NoNewline -ForegroundColor $colors.Progress
    }
}

function Get-OllamaModels {
    <#
    .SYNOPSIS
        Get list of available Ollama models
    .OUTPUTS
        Array of model objects or $null on error
    #>
    try {
        $response = Invoke-RestMethod -Uri "$script:OllamaUrl/api/tags" -Method Get -TimeoutSec 30 -ErrorAction Stop
        if ($null -eq $response -or $null -eq $response.models) {
            Write-ColorOutput "No models returned from Ollama API" $colors.Warning
            return @()
        }
        return $response.models
    }
    catch {
        Write-ColorOutput "Error connecting to Ollama: $_" $colors.Error
        Write-ColorOutput "Ensure Ollama is running on $script:OllamaUrl" $colors.Warning
        return $null
    }
}

function Get-LoadedModels {
    <#
    .SYNOPSIS
        Get list of currently loaded Ollama models
    .OUTPUTS
        Array of loaded model objects or $null on error
    #>
    try {
        $response = Invoke-RestMethod -Uri "$script:OllamaUrl/api/ps" -Method Get -TimeoutSec 30 -ErrorAction Stop
        if ($null -eq $response) {
            return @()
        }
        return $response.models
    }
    catch {
        Write-ColorOutput "Error getting loaded models: $_" $colors.Error
        return $null
    }
}

function Get-ModelSize {
    <#
    .SYNOPSIS
        Get human-readable model size
    .PARAMETER ModelInfo
        The model info object from Ollama API
    .OUTPUTS
        String representation of model size
    #>
    param(
        [Parameter(Mandatory)]
        [object]$ModelInfo
    )

    try {
        if ($ModelInfo.size -and $ModelInfo.size -gt 0) {
            $sizeGB = [math]::Round($ModelInfo.size / 1GB, 1)
            return "${sizeGB}GB"
        }
        return "Unknown"
    }
    catch {
        return "Unknown"
    }
}

function Test-ModelLoaded {
    <#
    .SYNOPSIS
        Check if a model is currently loaded in VRAM
    .PARAMETER ModelName
        The name of the model to check
    .OUTPUTS
        Boolean indicating if model is loaded
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$ModelName
    )

    try {
        $loaded = Get-LoadedModels
        if ($null -eq $loaded -or $loaded.Count -eq 0) {
            return $false
        }
        return ($loaded | Where-Object { $_.name -eq $ModelName }) -ne $null
    }
    catch {
        Write-ColorOutput "Error checking if model is loaded: $_" $colors.Error
        return $false
    }
}

function Load-Model {
    <#
    .SYNOPSIS
        Load a model into VRAM
    .PARAMETER ModelName
        The name of the model to load
    .OUTPUTS
        Boolean indicating success
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$ModelName
    )

    Write-ColorOutput "`nLoading model: $ModelName" $colors.Info
    Write-ColorOutput "This may take a moment while the model loads into VRAM..." $colors.Warning

    $startTime = Get-Date
    $keepAliveStr = "${script:KeepAlive}s"
    $body = @{
        model = $ModelName
        prompt = "Hello"
        stream = $false
        keep_alive = $keepAliveStr
    } | ConvertTo-Json

    # Show loading animation
    $job = Start-Job -ScriptBlock {
        param($url, $body)
        try {
            Invoke-RestMethod -Uri "$url/api/generate" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 300
            return @{ Success = $true }
        } catch {
            return @{ Success = $false; Error = $_.Exception.Message }
        }
    } -ArgumentList $OllamaUrl, $body

    # ASCII spinner that works in all terminals
    $spinChars = @('|', '/', '-', '\')
    $i = 0

    while ($job.State -eq 'Running') {
        $elapsed = ((Get-Date) - $startTime).TotalSeconds
        $spin = $spinChars[$i % $spinChars.Length]
        Write-Host "`r$spin Loading $ModelName... (${elapsed:F0}s elapsed)    " -NoNewline -ForegroundColor $colors.Progress
        Start-Sleep -Milliseconds 100
        $i++
    }

    Write-Host "`r" -NoNewline  # Clear the line

    $result = Receive-Job -Job $job
    Remove-Job -Job $job

    $elapsed = ((Get-Date) - $startTime).TotalSeconds

    if ($result.Success) {
        $keepAliveMin = [math]::Round($script:KeepAlive / 60, 0)
        Write-ColorOutput "[OK] Model '$ModelName' loaded successfully in ${elapsed:F1} seconds (keep-alive: ${keepAliveMin}m)" $colors.Success

        # Show VRAM usage
        $loaded = Get-LoadedModels
        $modelInfo = $loaded | Where-Object { $_.name -eq $ModelName }
        if ($modelInfo -and $modelInfo.size_vram) {
            $vramGB = [math]::Round($modelInfo.size_vram / 1GB, 2)
            Write-ColorOutput "    VRAM Usage: ${vramGB}GB" $colors.Info
        }
        return $true
    } else {
        Write-ColorOutput "[FAIL] Failed to load model: $($result.Error)" $colors.Error
        return $false
    }
}

function Unload-Model {
    <#
    .SYNOPSIS
        Unload a model from VRAM
    .PARAMETER ModelName
        The name of the model to unload
    .OUTPUTS
        Boolean indicating success
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$ModelName
    )

    Write-ColorOutput "Unloading model: $ModelName" $colors.Info

    try {
        $body = @{
            model = $ModelName
            keep_alive = 0
        } | ConvertTo-Json

        $null = Invoke-RestMethod -Uri "$script:OllamaUrl/api/generate" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop
        Write-ColorOutput "[OK] Model '$ModelName' unloaded" $colors.Success
        return $true
    }
    catch {
        Write-ColorOutput "[FAIL] Failed to unload model: $_" $colors.Error
        return $false
    }
}

function Show-ModelStatus {
    Write-ColorOutput "`n=== Ollama Model Status ===" $colors.Info

    # Available models
    $available = Get-OllamaModels
    if ($available) {
        Write-ColorOutput "`nAvailable Models:" $colors.Info
        foreach ($m in $available) {
            $size = Get-ModelSize $m
            Write-Host "  - $($m.name) " -NoNewline
            Write-Host "($size)" -ForegroundColor DarkGray
        }
    }

    # Loaded models
    $loaded = Get-LoadedModels
    Write-ColorOutput "`nCurrently Loaded (in VRAM):" $colors.Info
    if ($loaded -and $loaded.Count -gt 0) {
        foreach ($m in $loaded) {
            $vramGB = [math]::Round($m.size_vram / 1GB, 2)
            Write-Host "  - $($m.name) " -NoNewline -ForegroundColor $colors.Success
            Write-Host "(${vramGB}GB VRAM)" -ForegroundColor DarkGray
        }
    } else {
        Write-ColorOutput "  (none)" "DarkGray"
    }

    # VRAM info via nvidia-smi
    Write-ColorOutput "`nGPU VRAM:" $colors.Info
    try {
        $nvidiaSmi = nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>$null
        if ($nvidiaSmi) {
            $parts = $nvidiaSmi.Split(',')
            $used = [int]$parts[0].Trim()
            $total = [int]$parts[1].Trim()
            $percent = [math]::Round(($used / $total) * 100, 1)
            $usedGB = [math]::Round($used / 1024, 1)
            $totalGB = [math]::Round($total / 1024, 1)

            # Progress bar
            $barWidth = 30
            $filledWidth = [math]::Round(($percent / 100) * $barWidth)
            $emptyWidth = $barWidth - $filledWidth
            $bar = "[" + ("=" * $filledWidth) + (" " * $emptyWidth) + "]"

            $barColor = if ($percent -gt 90) { $colors.Error } elseif ($percent -gt 70) { $colors.Warning } else { $colors.Success }
            Write-Host "  $bar " -NoNewline -ForegroundColor $barColor
            Write-Host "${usedGB}GB / ${totalGB}GB (${percent}%)" -ForegroundColor $barColor
        }
    } catch {
        Write-ColorOutput "  (nvidia-smi not available)" "DarkGray"
    }
}

function Show-InteractiveMenu {
    $models = Get-OllamaModels
    if (-not $models) {
        Write-ColorOutput "No models available or Ollama not running." $colors.Error
        return
    }

    # Filter to coding-relevant models using configurable ModelFilter parameter
    $codingModels = $models | Where-Object {
        $modelName = $_.name
        $matchesFilter = $false
        foreach ($pattern in $script:ModelFilter) {
            if ($modelName -match [regex]::Escape($pattern)) {
                $matchesFilter = $true
                break
            }
        }
        $matchesFilter
    }

    # Fallback to all models if filter yields no results
    if (-not $codingModels -or $codingModels.Count -eq 0) {
        $codingModels = $models
    }

    Show-ModelStatus

    Write-ColorOutput "`n=== Load Model Menu ===" $colors.Info
    Write-ColorOutput "Select a model to load into VRAM:`n" "White"

    $i = 1
    $modelList = @()
    foreach ($m in $codingModels) {
        $size = Get-ModelSize $m
        $loaded = if (Test-ModelLoaded $m.name) { " [LOADED]" } else { "" }
        $loadedColor = if ($loaded) { $colors.Success } else { "White" }

        Write-Host "  [$i] " -NoNewline -ForegroundColor $colors.Info
        Write-Host "$($m.name) " -NoNewline -ForegroundColor $loadedColor
        Write-Host "($size)$loaded" -ForegroundColor DarkGray

        $modelList += $m.name
        $i++
    }

    Write-Host "`n  [U] Unload all models" -ForegroundColor $colors.Warning
    Write-Host "  [Q] Quit`n" -ForegroundColor DarkGray

    $selection = Read-Host "Enter selection"

    if ($selection -eq 'Q' -or $selection -eq 'q') {
        return
    }

    if ($selection -eq 'U' -or $selection -eq 'u') {
        $loaded = Get-LoadedModels
        if ($loaded) {
            foreach ($m in $loaded) {
                Unload-Model $m.name
            }
        }
        Write-ColorOutput "`nAll models unloaded." $colors.Success
        return
    }

    # Safely parse selection as integer
    $parsedIdx = 0
    if (-not [int]::TryParse($selection, [ref]$parsedIdx)) {
        Write-ColorOutput "Invalid selection." $colors.Error
        return
    }

    $idx = $parsedIdx - 1
    if ($idx -ge 0 -and $idx -lt $modelList.Count) {
        $selectedModel = $modelList[$idx]

        if (Test-ModelLoaded $selectedModel) {
            Write-ColorOutput "Model '$selectedModel' is already loaded." $colors.Warning
            $confirm = Read-Host "Reload anyway? (y/N)"
            if ($confirm -ne 'y' -and $confirm -ne 'Y') {
                return
            }
        }

        Load-Model $selectedModel

        Write-Host "`n"
        Show-ModelStatus
    } else {
        Write-ColorOutput "Invalid selection." $colors.Error
    }
}

# Main execution
Write-ColorOutput "`n========================================" $colors.Info
Write-ColorOutput "  Ollama Model Loader for Roo Code" $colors.Info
Write-ColorOutput "========================================`n" $colors.Info

# Check Ollama is running
try {
    Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -Method Get -TimeoutSec 5 | Out-Null
} catch {
    Write-ColorOutput "ERROR: Cannot connect to Ollama at $OllamaUrl" $colors.Error
    Write-ColorOutput "Make sure Ollama is running." $colors.Warning
    exit 1
}

if ($Status) {
    Show-ModelStatus
} elseif ($List) {
    $models = Get-OllamaModels
    Write-ColorOutput "Available Ollama Models:" $colors.Info
    foreach ($m in $models) {
        $size = Get-ModelSize $m
        Write-Host "  - $($m.name) ($size)"
    }
} elseif ($Unload -and $Model) {
    Unload-Model $Model
} elseif ($Model) {
    Load-Model $Model
    Show-ModelStatus
} else {
    Show-InteractiveMenu
}

Write-Host ""
