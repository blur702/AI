# N8N Workflow Automation Setup Guide

This guide explains how to install, verify, and run the N8N workflow automation service as part of your local AI services dashboard.

## Prerequisites

- Node.js **20.19.x to 24.x** is recommended for compatibility with recent N8N versions.
- A working internet connection for downloading N8N.
- Sufficient disk space for Node.js and the global N8N installation.

Download Node.js from the official website:

- https://nodejs.org/

Using the recommended Node.js versions helps ensure that N8N installs and runs correctly without runtime or dependency issues.

## Installation Steps

### 1. Verify Node.js Installation

Open a terminal or command prompt and run:

```bash
node --version
```

Expected output format:

- `v20.x.x` or
- `v24.x.x`

If Node.js is not installed or the version is outside this range, download and install a compatible version from:

- https://nodejs.org/

### 2. Install N8N Globally

Install N8N as a **global** npm package so it is available system-wide:

```bash
npm install n8n -g
```

Notes:

- The `-g` flag installs N8N globally, making the `n8n` command available from any directory.
- On Windows, you may need to run the terminal as **Administrator** for the global installation to succeed.
- Installation time and size depend on your network speed and system performance (typically a few minutes).

### 3. Verify N8N Installation

After installation, verify that N8N is available:

```bash
n8n --version
```

Expected output:

- A version string such as `1.x.x` (exact version may vary).

If this command fails, re-check your Node.js installation, npm configuration, and your PATH environment variable.

## Running N8N

Once Node.js and N8N are installed, use the provided startup script to run N8N as a service alongside your other AI tools.

From `D:\AI`, run:

```bash
start_n8n.bat
```

This script will:

- Ensure it is running from `D:\AI`.
- Start N8N with the default configuration.
- Keep the console window open with N8N running in the foreground.

Access URLs:

- Local machine: `http://localhost:5678`
- Local network (example): `http://10.0.0.138:5678`

On first access, N8N will guide you through creating an admin account and initial configuration.

## Integration with the Dashboard

The AI services dashboard served from `D:\AI\index.html` will include N8N as a service card, allowing quick navigation to the N8N web interface.

- Main dashboard URL: `http://localhost/`
- N8N card in the dashboard links to: `http://localhost:5678`

Use the dashboard as your central entry point to all AI and automation services, including N8N.

## Troubleshooting

### Node.js Version Mismatch

**Symptom:** N8N fails to install or run, or displays compatibility errors.

- Check Node.js version: `node --version`
- If the version is not `v20.x.x` or `v24.x.x`, install a supported version from https://nodejs.org/.

### Port 5678 Already in Use

**Symptom:** N8N fails to start and reports that port 5678 is already in use.

- Close any other application or service using port 5678.
- Alternatively, configure N8N to use a different port via environment variables (see Configuration Options below).

### Permission Errors During Global npm Install

**Symptom:** `npm install n8n -g` fails with permission or access denied errors.

- On Windows, open your terminal as **Administrator** and rerun:
  - `npm install n8n -g`
- Ensure your user account has permission to modify global npm directories.

### Firewall Blocking Access

**Symptom:** N8N appears to be running, but you cannot reach `http://localhost:5678` or the network URL.

- Check Windows Firewall or any third-party firewall software.
- Allow inbound connections on port 5678 for local and/or network access as needed.

## Configuration Options

N8N supports extensive configuration via environment variables and configuration files. Common options include:

- `N8N_PORT` – Change the default port (5678).
- `N8N_HOST` – Configure the host/interface N8N listens on.
- `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD` – Enable basic authentication.
- `N8N_ENCRYPTION_KEY` – Set an encryption key for secure data storage.
- `DATA_FOLDER` – Customize the data folder location for N8N.
- `WEBHOOK_URL` – Set the public URL for webhooks (useful when exposing N8N externally).

For production or remote access scenarios, review N8N’s security and deployment recommendations.

## Additional Resources

- Official N8N documentation: https://docs.n8n.io/
- N8N community forum: https://community.n8n.io/
- N8N GitHub repository: https://github.com/n8n-io/n8n

These resources provide deeper guides on workflows, nodes, integrations, and secure deployment options.

