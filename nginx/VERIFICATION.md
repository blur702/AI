# Nginx Configuration Verification Checklist

Manual testing steps to verify the nginx reverse proxy is working correctly.

## Pre-Flight Checks

- [ ] SSL certificate files exist in `ssl/` directory
- [ ] Nginx configuration test passes: `test-nginx.bat`
- [ ] Flask dashboard is running on port 80
- [ ] Required backend services are running

## HTTPS Access Tests

### 1. Basic HTTPS Access

```
URL: https://ssdd.kevinalthaus.com/
Expected: Dashboard loads with valid SSL (green lock icon)
```

- [ ] Page loads successfully
- [ ] SSL certificate is valid (no warnings)
- [ ] Browser shows secure connection

### 2. HTTP to HTTPS Redirect

```
URL: http://ssdd.kevinalthaus.com/
Expected: Redirects to https://ssdd.kevinalthaus.com/
```

- [ ] HTTP request redirects to HTTPS
- [ ] Final URL is HTTPS version

## Dashboard Tests

### 3. Dashboard API

```
URL: https://ssdd.kevinalthaus.com/api/services
Expected: JSON response with service list
```

- [ ] Returns valid JSON
- [ ] Contains service data

### 4. WebSocket Connection

```
URL: https://ssdd.kevinalthaus.com/ (open browser console)
Expected: Socket.IO connects successfully
```

- [ ] No WebSocket errors in console
- [ ] VRAM updates appear in dashboard

## Service Proxy Tests

Run these tests for each service that's currently running:

### 5. ComfyUI (Port 8188)

```
URL: https://ssdd.kevinalthaus.com/comfyui/
Expected: ComfyUI interface loads
```

- [ ] UI loads correctly
- [ ] WebSocket for queue updates works

### 6. N8N (Port 5678)

```
URL: https://ssdd.kevinalthaus.com/n8n/
Expected: N8N workflow interface loads
```

- [ ] UI loads correctly
- [ ] Can create/edit workflows

### 7. Open WebUI (Port 3000)

```
URL: https://ssdd.kevinalthaus.com/openwebui/
Expected: Open WebUI chat interface loads
```

- [ ] UI loads correctly
- [ ] Can send chat messages

### 8. AllTalk (Port 7851)

```
URL: https://ssdd.kevinalthaus.com/alltalk/
Expected: AllTalk TTS interface loads
```

- [ ] UI loads correctly

### 9. Wan2GP (Port 7860)

```
URL: https://ssdd.kevinalthaus.com/wan2gp/
Expected: Gradio interface loads
```

- [ ] Gradio UI renders correctly
- [ ] File upload works

### 10. YuE Music (Port 7870)

```
URL: https://ssdd.kevinalthaus.com/yue/
Expected: Gradio interface loads
```

- [ ] Gradio UI renders correctly

### 11. DiffRhythm (Port 7871)

```
URL: https://ssdd.kevinalthaus.com/diffrhythm/
Expected: Gradio interface loads
```

- [ ] Gradio UI renders correctly

### 12. MusicGen (Port 7872)

```
URL: https://ssdd.kevinalthaus.com/musicgen/
Expected: Gradio interface loads
```

- [ ] Gradio UI renders correctly

### 13. Stable Audio (Port 7873)

```
URL: https://ssdd.kevinalthaus.com/stable-audio/
Expected: Gradio interface loads
```

- [ ] Gradio UI renders correctly

### 14. Ollama API (Port 11434)

```bash
curl -X POST https://ssdd.kevinalthaus.com/ollama/api/generate \
  -d '{"model":"llama3.2","prompt":"Hello","stream":false}'
```

Expected: JSON response with generated text

- [ ] API responds correctly
- [ ] Can generate text

### 15. Weaviate (Port 8080)

```
URL: https://ssdd.kevinalthaus.com/weaviate/v1/schema
Expected: JSON schema response
```

- [ ] API responds correctly

### 16. Weaviate Console (Port 8081)

```
URL: https://ssdd.kevinalthaus.com/weaviate-console/
Expected: Console UI loads
```

- [ ] UI loads correctly

### 17. A1111 (Port 7861)

```
URL: https://ssdd.kevinalthaus.com/a1111/
Expected: Stable Diffusion WebUI loads
```

- [ ] Gradio UI renders correctly

### 18. SD Forge (Port 7862)

```
URL: https://ssdd.kevinalthaus.com/forge/
Expected: SD Forge WebUI loads
```

- [ ] Gradio UI renders correctly

### 19. Fooocus (Port 7865)

```
URL: https://ssdd.kevinalthaus.com/fooocus/
Expected: Fooocus interface loads
```

- [ ] Gradio UI renders correctly

## Security Tests

### 20. Direct Port Access Blocked

After running `configure-firewall.ps1`:

```
From external machine:
curl http://ssdd.kevinalthaus.com:8188/
Expected: Connection refused/timeout
```

- [ ] Cannot access ComfyUI directly on port 8188
- [ ] Cannot access other service ports directly

### 21. SSL Certificate Validity

```bash
openssl s_client -connect ssdd.kevinalthaus.com:443 -servername ssdd.kevinalthaus.com
```

- [ ] Certificate chain is valid
- [ ] Certificate not expired
- [ ] Hostname matches

## Log Verification

### 22. Access Logs

```
File: nginx/logs/access.log
```

- [ ] Requests are being logged
- [ ] Status codes are correct (200, 301, etc.)

### 23. Error Logs

```
File: nginx/logs/error.log
```

- [ ] No critical errors
- [ ] No repeated connection failures

## Performance Tests

### 24. Response Time

```bash
curl -w "@curl-format.txt" -o /dev/null -s https://ssdd.kevinalthaus.com/
```

- [ ] Time to first byte < 500ms
- [ ] Total time reasonable for page type

### 25. Large File Upload

Test uploading a file through ComfyUI or similar:

- [ ] Files up to 100MB upload successfully
- [ ] No timeout errors

## Troubleshooting Commands

```bash
# Check if nginx is running
tasklist /fi "imagename eq nginx.exe"

# Check what's using port 443
netstat -ano | findstr :443

# View recent errors
type nginx\logs\error.log | more

# Test backend service directly
curl http://localhost:8188/

# Reload config after changes
nginx\reload-nginx.bat
```

## Test Results Summary

| Category        | Passed | Failed | Notes |
| --------------- | ------ | ------ | ----- |
| HTTPS Access    |        |        |       |
| Dashboard       |        |        |       |
| Service Proxies |        |        |       |
| Security        |        |        |       |
| Logs            |        |        |       |
| Performance     |        |        |       |

**Overall Status:** ☐ PASS / ☐ FAIL

**Tested By:** **\*\***\_\_\_**\*\***
**Date:** **\*\***\_\_\_**\*\***
