# Nginx Reverse Proxy Configuration

HTTPS reverse proxy for `ssdd.kevinalthaus.com` with path-based routing to backend AI services.

## Architecture

```
Internet → Nginx (443/HTTPS) → Backend Services (localhost ports)
                ↓
         SSL Termination
                ↓
    Path-based routing:
    /           → Flask Dashboard (80)
    /comfyui/   → ComfyUI (8188)
    /n8n/       → N8N (5678)
    /ollama/    → Ollama (11434)
    ... etc
```

## Prerequisites

1. **Nginx for Windows**
   - Download from: https://nginx.org/en/download.html
   - Extract to `C:\nginx` or add to PATH
   - Ensure `nginx.exe` is accessible from this directory

2. **SSL Certificates** (choose one):
   - **Let's Encrypt** (production): Requires Certbot
   - **Self-Signed** (testing): Requires OpenSSL

## Quick Start

### 1. Install SSL Certificate

**Option A: Let's Encrypt (Recommended)**
```batch
setup-letsencrypt.bat
```
Requires port 80 temporarily available for domain verification.

**Option B: Self-Signed (Testing)**
```batch
generate-self-signed-cert.bat
```
Will show browser security warnings.

### 2. Start Nginx
```batch
start-nginx.bat
```

**Note:** The start script validates SSL certificates before launching. If either `ssl\ssdd.kevinalthaus.com.crt` or `ssl\ssdd.kevinalthaus.com.key` is missing, nginx will not start and you'll see an error message directing you to run the certificate setup scripts first.

### 3. Access Services
- Dashboard: `https://ssdd.kevinalthaus.com/`
- ComfyUI: `https://ssdd.kevinalthaus.com/comfyui/`
- N8N: `https://ssdd.kevinalthaus.com/n8n/`
- See full list below

## Management Scripts

| Script | Description |
|--------|-------------|
| `start-nginx.bat` | Start nginx (checks certificates first) |
| `stop-nginx.bat` | Stop nginx gracefully |
| `reload-nginx.bat` | Reload config without restart |
| `test-nginx.bat` | Test config syntax |
| `setup-letsencrypt.bat` | Get Let's Encrypt certificate |
| `generate-self-signed-cert.bat` | Create self-signed cert |
| `setup-renewal-task.bat` | Auto-renewal scheduled task |
| `configure-firewall.ps1` | Windows firewall rules |

## Service Routing

| Path | Service | Port | Notes |
|------|---------|------|-------|
| `/` | Dashboard | 80 | Flask + React |
| `/api/` | Dashboard API | 80 | REST endpoints |
| `/socket.io/` | WebSocket | 80 | Real-time updates |
| `/comfyui/` | ComfyUI | 8188 | Image generation |
| `/n8n/` | N8N | 5678 | Workflow automation |
| `/openwebui/` | Open WebUI | 3000 | LLM chat |
| `/alltalk/` | AllTalk | 7851 | Text-to-speech |
| `/wan2gp/` | Wan2GP | 7860 | Video generation |
| `/yue/` | YuE | 7870 | Music generation |
| `/diffrhythm/` | DiffRhythm | 7871 | Music generation |
| `/musicgen/` | MusicGen | 7872 | Audio generation |
| `/stable-audio/` | Stable Audio | 7873 | Audio generation |
| `/ollama/` | Ollama | 11434 | LLM API |
| `/weaviate/` | Weaviate | 8080 | Vector database |
| `/weaviate-console/` | Weaviate Console | 8081 | DB admin UI |
| `/a1111/` | A1111 | 7861 | Stable Diffusion |
| `/forge/` | SD Forge | 7862 | Stable Diffusion |
| `/fooocus/` | Fooocus | 7865 | Image generation |

## Firewall Configuration

Run as Administrator:
```powershell
powershell -ExecutionPolicy Bypass -File configure-firewall.ps1
```

This will:
- Allow inbound ports 80 and 443 (nginx)
- Block external access to service ports (localhost only)

## Directory Structure

```
nginx/
├── nginx.conf          # Main configuration
├── conf.d/
│   └── ssdd.conf       # Site-specific config
├── ssl/
│   ├── ssdd.kevinalthaus.com.crt
│   └── ssdd.kevinalthaus.com.key
├── logs/
│   ├── access.log
│   └── error.log
└── *.bat               # Management scripts
```

## Troubleshooting

### Nginx won't start
1. **Missing SSL certificates**: The start script pre-checks for both `ssl\ssdd.kevinalthaus.com.crt` and `ssl\ssdd.kevinalthaus.com.key`. If either file is missing or misnamed, nginx will not start. Run `setup-letsencrypt.bat` or `generate-self-signed-cert.bat` to create them.
2. Check if port 443/80 is in use: `netstat -ano | findstr :443`
3. Test config: `test-nginx.bat`
4. Check logs: `logs\error.log`

### Certificate errors
1. Verify both cert files exist in `ssl/`:
   - `ssl\ssdd.kevinalthaus.com.crt` (certificate)
   - `ssl\ssdd.kevinalthaus.com.key` (private key)
2. Check cert validity: `openssl x509 -in ssl\ssdd.kevinalthaus.com.crt -text -noout`
3. Regenerate if expired

### Service not accessible
1. Verify service is running on its port
2. Check nginx error log
3. Test direct access: `curl http://localhost:PORT/`

### WebSocket connection fails
1. Check browser console for errors
2. Verify WebSocket upgrade headers in nginx config
3. Check service supports WebSocket

## SSL Certificate Renewal

Let's Encrypt certificates expire after 90 days.

**Manual renewal:**
```batch
certbot renew
```

**Automatic renewal:**
```batch
setup-renewal-task.bat
```
Creates Windows scheduled task running daily.

## Configuration Changes

1. Edit `conf.d/ssdd.conf`
2. Test: `test-nginx.bat`
3. Reload: `reload-nginx.bat`

## Adding New Services

Add a location block to `conf.d/ssdd.conf`:

```nginx
location /newservice/ {
    proxy_pass http://127.0.0.1:PORT/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Add WebSocket support if needed:
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

Then reload nginx: `reload-nginx.bat`
