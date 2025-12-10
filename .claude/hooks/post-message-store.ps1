# Post-Message Store Hook
# Stores user prompts to Weaviate ClaudeConversation collection
#
# Environment variables provided by Claude Code:
#   $env:CLAUDE_USER_PROMPT - The user's message
#   $env:CLAUDE_SESSION_ID - Current session ID
#   $env:CLAUDE_PROJECT_DIR - The project root directory

$userPrompt = $env:CLAUDE_USER_PROMPT
$sessionId = $env:CLAUDE_SESSION_ID
$projectDir = $env:CLAUDE_PROJECT_DIR

# Skip if no prompt (shouldn't happen, but be safe)
if (-not $userPrompt) {
    exit 0
}

# Skip very short prompts (likely just "y", "ok", etc.)
if ($userPrompt.Length -lt 10) {
    exit 0
}

# Get timestamp
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")

# Create JSON payload for the Python script
$payload = @{
    session_id = $sessionId
    timestamp = $timestamp
    user_message = $userPrompt
    assistant_response = ""  # Will be filled by a future hook or manually
} | ConvertTo-Json -Compress

# Store to Weaviate via Python script (fire and forget, don't block)
$scriptPath = Join-Path $projectDir "api_gateway\services\claude_conversation_schema.py"

if (Test-Path $scriptPath) {
    # Run in background to not block the user
    Start-Process -NoNewWindow -FilePath "python" -ArgumentList @(
        "-m", "api_gateway.services.claude_conversation_schema",
        "store-stdin"
    ) -RedirectStandardInput (
        [System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($payload))
    ) 2>$null
}

# Always exit success - don't block the conversation
exit 0
