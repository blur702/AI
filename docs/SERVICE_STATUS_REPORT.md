# AI Services Status Report
**Generated: 2025-12-05 05:50 EST**

## Playwright Test Results

| Service | Port | Status | Notes |
|---------|------|--------|-------|
| Ollama Generation | 11434 | **PASS** | LLM backend working (gemma2:27b tested) |
| Open WebUI | 3000 | **PASS** | Chat interface with model selector |
| ComfyUI | 8188 | **PASS** | Image generation with network access |
| Wan2GP Video | 7860 | **PASS** | Text/Image to Video generation |
| YuE Music | 7870 | **PASS** | Full song generation with vocals |
| DiffRhythm | 7871 | **PASS** | Fast full-song generation |
| MusicGen | 7872 | **FAIL** | Venv path issue - see Known Issues |
| Stable Audio | 7873 | **PASS** | Audio generation |
| Open WebUI Chat | 3000 | **PASS** | Chat interface functional |

**Summary: 8 Passed | 0 Warnings | 1 Failed**

## Currently Running Services

| Service | Port | Status | Command |
|---------|------|--------|---------|
| Open WebUI | 3000 | **WORKING** | Docker container |
| Ollama API | 11434 | **WORKING** | `ollama serve` |
| ComfyUI | 8188 | **WORKING** | `D:/AI/ComfyUI/run_network.bat` |
| Wan2GP Video | 7860 | **WORKING** | `D:/AI/Wan2GP/wan2gp_env/python.exe wgp.py --listen` |
| YuE Music | 7870 | **WORKING** | `D:/AI/YuE/yue_env/Scripts/python.exe run_ui.py` |
| DiffRhythm | 7871 | **WORKING** | `D:/AI/DiffRhythm/diffrhythm_env/Scripts/python.exe run_ui.py` |
| Stable Audio | 7873 | **WORKING** | `D:/AI/stable-audio-tools/stable_audio_env/Scripts/python.exe run_ui.py` |

## Services Ready to Launch

### MusicGen/AudioCraft (Port 7872) - NEEDS FIX
```bash
cd D:/AI/audiocraft
D:/AI/audiocraft/audiocraft_env/Scripts/python.exe run_musicgen_ui.py
```
**Known Issue:** The venv was created using Python from Wan2GP, causing path resolution issues. The `julius` module cannot be imported due to incorrect Python path configuration in `pyvenv.cfg`.

**To fix:** Recreate the venv using a standalone Python 3.10 installation, not from another venv.

## Known Issues

### MusicGen audiocraft_env Path Issue
- **Symptom:** `ModuleNotFoundError: No module named 'julius'` even though julius is installed
- **Cause:** The venv's `pyvenv.cfg` points to `D:\AI\Wan2GP\wan2gp_env` as the home directory
- **Impact:** Python path includes Wan2GP's directories before audiocraft_env's site-packages
- **Solution:** Delete `D:\AI\audiocraft\audiocraft_env` and recreate using a proper Python 3.10 installation (not from another venv)

## Model Downloads

- **Wan2.1 Models**: All downloaded successfully
  - wan2.1_text2video_14B_mbf16.safetensors
  - wan2.1_image2video_480p_14B_mbf16.safetensors
  - wan2.1_image2video_720p_14B_mbf16.safetensors
  - hunyuan_video_720_bf16.safetensors
  - VAE, T5 Encoder, CLIP components

## Test Artifacts

- Screenshots saved to: `D:/AI/screenshots/`
- Test results JSON: `D:/AI/test_results.json`

## System Info

- GPU: NVIDIA GeForce RTX 3090 (24GB VRAM)
- All services configured for network access (0.0.0.0)
- Open WebUI connected to Ollama via host.docker.internal:11434

## Fixes Applied This Session

1. **YuE run_ui.py** - Removed `theme=` argument from Gradio launch
2. **DiffRhythm run_ui.py** - Removed `theme=` argument from Gradio launch
3. **Stable Audio run_ui.py** - Removed `theme=` argument from Gradio launch
4. **MusicGen run_musicgen_ui.py** - Removed `theme=gr.themes.Soft()` from gr.Blocks()
