# Post-Message Store Hook for Claude Code
# Stores conversation turns in Weaviate for semantic retrieval
#
# Input: JSON from stdin with conversation data
# Output: Result JSON to stdout
#
# This hook is triggered after user prompts are submitted
# It extracts the conversation context and stores it in Weaviate

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

# Extract relevant data from the hook input
# The structure depends on the hook type (PreToolUse, PostToolUse, etc.)
$sessionId = $env:CLAUDE_SESSION_ID
if (-not $sessionId) {
    $sessionId = [guid]::NewGuid().ToString()
}

# For user-prompt-submit-hook, extract the prompt
$userMessage = ""
$assistantResponse = ""
$toolCalls = @()
$filePaths = @()

# Try to extract from different possible input structures
if ($data.prompt) {
    $userMessage = $data.prompt
}
if ($data.user_message) {
    $userMessage = $data.user_message
}
if ($data.message) {
    $userMessage = $data.message
}
if ($data.tool_input) {
    # This might be from a tool use event
    if ($data.tool_input.prompt) {
        $userMessage = $data.tool_input.prompt
    }
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
