# Post-Message Store Hook for Claude Code
# Stores conversation turns in Weaviate for semantic retrieval
#
# Input: JSON from stdin with:
#   - session_id: Session identifier
#   - prompt: The user's prompt text
#   - transcript_path: Path to session transcript
#   - cwd: Current working directory
#
# This hook is triggered when user submits a prompt (UserPromptSubmit event)

param(
    [Parameter(ValueFromPipeline=$true)]
    [string]$InputJson
)

# Ensure we read all input if piped
if (-not $InputJson) {
    $InputJson = $input | Out-String
}

if (-not $InputJson -or $InputJson.Trim() -eq "") {
    exit 0
}

# Parse the JSON input
try {
    $data = $InputJson | ConvertFrom-Json
} catch {
    # Invalid JSON, skip silently
    exit 0
}

# Extract the prompt from UserPromptSubmit event
$userMessage = $data.prompt
$sessionId = $data.session_id

# Generate session ID if not provided
if (-not $sessionId) {
    $sessionId = [guid]::NewGuid().ToString()
}

# Skip if no user message found
if (-not $userMessage -or $userMessage.Trim() -eq "") {
    exit 0
}

# Build the conversation data for storage
$conversationData = @{
    session_id = $sessionId
    user_message = $userMessage
    assistant_response = $assistantResponse
    tool_calls = $toolCalls
    file_paths = $filePaths
    tags = @()
}

$jsonPayload = $conversationData | ConvertTo-Json -Compress

# Store in Weaviate via the Python script
try {
    $result = $jsonPayload | python -m api_gateway.services.claude_conversation_schema store-stdin 2>&1

    if ($LASTEXITCODE -eq 0) {
        # Successfully stored
        # Optionally output for debugging
        # Write-Host "Conversation stored: $result"
    }
} catch {
    # Storage failed, but don't block the user
    # Write-Host "Failed to store conversation: $_"
}

exit 0
