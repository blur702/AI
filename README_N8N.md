# N8N Workflow Automation Setup Guide

This guide explains how to install, verify, and run the N8N workflow automation service as part of your local AI services dashboard.

## Prerequisites

- Node.js **20.19.x to 24.x** is recommended for compatibility with current N8N versions.
- A working internet connection to download N8N and its dependencies.
- Sufficient disk space for Node.js, npm, and the global N8N installation.

Download Node.js from the official website:

- https://nodejs.org/

Using a supported Node.js version helps avoid installation and runtime issues with N8N.

## Installation Steps

### 1. Verify Node.js Installation

Open a terminal or Command Prompt and run:

```bash
node --version
```

Expected output format:

- `v20.x.x` or
- `v24.x.x`

If Node.js is not installed or the version is outside this range, install a compatible version from:

- https://nodejs.org/

After installation, open a new terminal and run `node --version` again to confirm.

### 2. Install N8N Globally

Install N8N as a **global** npm package so the `n8n` command is available system-wide:

```bash
npm install n8n -g
```

Notes:

- The `-g` flag installs N8N globally, not just in the current project.
- On Windows, you may need to run the terminal as **Administrator** for the global install to succeed.
- Installation time and size depend on your network speed and machine performance (typically a few minutes).

### 3. Verify N8N Installation

After the installation completes, verify that N8N is available on your PATH:

```bash
n8n --version
```

Expected output:

- A version string such as `1.x.x` (exact value depends on the installed release).

If this command fails, see the troubleshooting section below (PATH and permissions issues are common causes).

## Running N8N with `start_n8n.bat`

Once Node.js and N8N are installed, use the provided startup script to run N8N alongside your other AI services.

From `D:\AI`, run:

```bash
start_n8n.bat
```

What the script does:

- Prints a banner showing that N8N is starting on port **5678**.
- Confirms local and network URLs.
- Ensures it is running from `D:\AI`.
- Checks that `n8n` is installed and on PATH via `n8n --version`.
  - If the check fails, it prints an error message, reminds you to run `npm install n8n -g`, and exits.
- If the check succeeds, it runs:

```bash
n8n start
```

The process runs in the foreground and keeps the console window open.

### Verifying N8N is Running

After `start_n8n.bat` reports that N8N is starting:

- Open a browser on the same machine and go to:
  - `http://localhost:5678`

On first access, N8N will guide you through creating an admin account and performing the initial setup.

If your dashboard is running (via `start_dashboard.bat`), you can also click the N8N card on the main dashboard to open the same URL.

## Troubleshooting

### Node.js Version Mismatch

**Symptom:** N8N fails to install, fails at runtime, or prints compatibility/deprecation warnings.

- Check Node.js version:

  ```bash
  node --version
  ```

- If the version is not `v20.x.x` or `v24.x.x`, install a supported version from https://nodejs.org/ and retry.

### Port 5678 Already in Use

**Symptom:** `n8n start` fails with an error indicating that port 5678 is already in use.

- Another application or a previous N8N instance may be using port 5678.
- Close or stop the process using this port, then rerun `start_n8n.bat`.
- Alternatively, configure N8N to use a different port via environment variables (see Configuration below).

### Global npm Permission Errors

**Symptom:** `npm install n8n -g` fails with permission or access-denied errors.

- On Windows, run your terminal as **Administrator** and execute:

  ```bash
  npm install n8n -g
  ```

- Ensure your user account has permission to modify the global npm directory.
- If you changed npm’s global directory, confirm that the directory is writable and on your PATH.

### `n8n` Not on PATH

**Symptom:** Running `n8n --version` or `n8n start` results in `'n8n' is not recognized as an internal or external command`.

- Close and reopen your terminal after installing N8N globally so PATH changes take effect.
- Verify that the global npm `bin` directory is included in your PATH environment variable.
- If needed, reinstall N8N globally:

  ```bash
  npm install n8n -g
  ```

### Firewall Blocking Access

**Symptom:** N8N appears to be running, but you cannot reach `http://localhost:5678` or the network URL from other devices.

- Check Windows Firewall or any third-party firewall.
- Allow inbound connections on port **5678** for local and/or LAN access as required.
- If accessing from another machine, confirm that:
  - The host machine’s IP address is correct.
  - The firewall allows inbound HTTP traffic on port 5678.

## Configuration Options

N8N supports extensive configuration via environment variables and configuration files. Common options include:

- `N8N_PORT` – Change the default port (5678).
- `N8N_HOST` – Configure the host/interface N8N listens on.
- `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD` – Enable basic authentication for the UI.
- `N8N_ENCRYPTION_KEY` – Set an encryption key for secure storage of credentials and sensitive data.
- `DATA_FOLDER` – Customize the data folder location for N8N (e.g., for backups or custom storage).
- `WEBHOOK_URL` – Set the public URL for webhooks when exposing N8N externally.

For production or remote deployments, review N8N’s security and deployment best practices in the official docs.

## Additional Resources

- Official N8N documentation: https://docs.n8n.io/
- N8N community forum: https://community.n8n.io/
- N8N GitHub repository: https://github.com/n8n-io/n8n

Use these resources for deeper guides on workflows, nodes, integrations, and secure deployment options.

