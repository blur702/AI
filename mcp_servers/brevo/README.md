# Brevo MCP Proxy Server

A FastMCP proxy server that bridges Brevo's hosted MCP services to local STDIO transport for use with VS Code, Claude Desktop, and other MCP clients.

## Overview

This proxy provides access to Brevo's comprehensive suite of marketing and communication services through the Model Context Protocol (MCP). Instead of implementing individual tools, it forwards requests to Brevo's hosted MCP infrastructure, which exposes 26+ services.

## Prerequisites

- Python 3.8+
- Brevo account with MCP API key
- Internet connectivity to reach Brevo's servers

## Installation

```bash
cd mcp_servers/brevo
pip install -r requirements.txt
```

## Configuration

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your Brevo MCP token:
   ```
   BREVO_MCP_TOKEN=your_brevo_mcp_token_here
   ```

3. (Optional) Adjust logging level:
   ```
   LOG_LEVEL=DEBUG
   ```

## Running

### Direct execution

```bash
python -m mcp_servers.brevo.main
```

### VS Code / Claude Code Configuration

Add to your VS Code settings or `.vscode/mcp.json`:

```json
{
  "mcpServers": {
    "brevo": {
      "command": "python",
      "args": ["-m", "mcp_servers.brevo.main"],
      "cwd": "/path/to/your/AI/workspace"
    }
  }
}
```

**Note:** Replace `/path/to/your/AI/workspace` with the absolute path to your AI project directory (e.g., `C:\\Users\\YourName\\AI` on Windows or `/home/user/AI` on Linux/macOS).

### Claude Desktop Configuration

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "brevo": {
      "command": "python",
      "args": ["-m", "mcp_servers.brevo.main"],
      "cwd": "/path/to/your/AI/workspace"
    }
  }
}
```

**Note:** Replace `/path/to/your/AI/workspace` with the absolute path to your AI project directory (e.g., `C:\\Users\\YourName\\AI` on Windows or `/home/user/AI` on Linux/macOS).

## Available Services

The Brevo MCP endpoint provides access to these services:

### Email
- **Email Campaigns** - Create, send, and manage marketing campaigns
- **Transactional Emails** - Send triggered emails via SMTP or API
- **Email Templates** - Manage reusable email templates

### Contacts & Lists
- **Contacts** - Create, update, and manage contact records
- **Lists** - Organize contacts into mailing lists
- **Segments** - Create dynamic contact segments
- **Attributes** - Define custom contact attributes

### CRM
- **Deals** - Manage sales pipeline and opportunities
- **Companies** - Track business accounts
- **Tasks** - Create and assign follow-up tasks
- **Notes** - Add notes to CRM records

### Messaging
- **SMS Campaigns** - Send bulk SMS messages
- **WhatsApp** - WhatsApp Business messaging
- **Inbound Parsing** - Process incoming emails

### Configuration
- **Senders** - Manage verified sender identities
- **Domains** - Configure sending domains
- **Webhooks** - Set up event notifications

### Analytics
- **Reports** - Access campaign statistics
- **Events** - Track email events (opens, clicks, etc.)

### Account
- **Users** - Manage team members
- **Account Info** - Access account details

## Architecture

```
VS Code/Claude Desktop
        |
        | STDIO (JSON-RPC)
        v
   MCP Proxy (main.py)
        |
        | HTTPS/SSE
        v
  Brevo Hosted MCP Server
  (https://mcp.brevo.com/brevo/mcp/{token})
        |
        v
   Brevo Services
   (Email, CRM, SMS, etc.)
```

## Security Notes

- **Never commit the `.env` file** - It contains your API credentials
- **MCP token provides full account access** - Treat it like a password
- **Store token securely** - Use environment variables or secrets management
- **Rotate token if compromised** - Generate a new key in Brevo settings

## Integration Status

- Domain verification pending (configure your sender domain in Brevo settings)
- Service ready for integration
- API documentation available at https://developers.brevo.com

## Troubleshooting

### Connection Errors
- Verify internet connectivity
- Check Brevo service status at https://status.brevo.com
- Ensure the MCP token is valid

### Authentication Errors
- Verify `BREVO_MCP_TOKEN` is set correctly in `.env`
- Check that the token has MCP permissions in Brevo settings
- Ensure the token hasn't been revoked

### STDIO Transport Issues
- Ensure all logging goes to stderr (not stdout)
- Check that no print statements write to stdout
- Verify the MCP client configuration uses correct command/args

### Debug Mode
Enable debug logging to see detailed request/response information:
```
LOG_LEVEL=DEBUG
```

## Development

To test the proxy locally:

```bash
# Set environment variables
export BREVO_MCP_TOKEN=your_token_here

# Run with debug logging
LOG_LEVEL=DEBUG python -m mcp_servers.brevo.main
```

## Related Documentation

- [Brevo API Documentation](https://developers.brevo.com/)
- [MCP Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
