# Local Voice Assistant Setup Plan

## Overview
Set up **local-talking-llm** with optimizations for your RTX 3090 (24GB VRAM) system.

## Components
| Component | Tool | Purpose |
|-----------|------|---------|
| Speech-to-Text | OpenAI Whisper (large-v3) | Transcribe your voice to text |
| LLM | Ollama (qwen2.5:32b or gemma2:27b) | Generate intelligent responses |
| Text-to-Speech | ChatterBox TTS | High-quality voice synthesis with cloning |

## Hardware Optimization Notes
- Your RTX 3090 can run Whisper large-v3 (~3GB VRAM) alongside the LLM
- ChatterBox TTS uses ~2-3GB VRAM
- Total VRAM budget: ~22-24GB when all running (fits your 24GB)
- Alternative: Use Whisper medium (~1.5GB) for more headroom

## Installation Steps

### Step 1: Clone the Repository
```powershell
cd D:\AI
git clone https://github.com/vndee/local-talking-llm.git
cd local-talking-llm
```

### Step 2: Create Python Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install -e .
```

This installs:
- `chatterbox-tts` - Advanced TTS with voice cloning
- `openai-whisper` - Speech recognition
- `langchain-ollama` - LLM integration
- `sounddevice`, `pyaudio` - Audio I/O
- `torch` with CUDA support

### Step 4: Download NLTK Data
```powershell
python -c "import nltk; nltk.download('punkt')"
```

### Step 5: Verify Ollama Models
Your models are already downloaded:
- `qwen2.5:32b` (recommended for quality)
- `gemma2:27b` (alternative, faster)

### Step 6: Test Run
```powershell
python app.py --model qwen2.5:32b
```

## Optional Enhancements

### Voice Cloning
Record a 10-30 second sample of a voice you want to clone:
```powershell
python app.py --voice D:\AI\my_voice_sample.wav --model qwen2.5:32b
```

### Adjust Voice Parameters
- `--exaggeration 0.7` - More emotional expression
- `--cfg-weight 0.3` - Control speech pacing
- `--save-voice` - Save generated audio to files

### Use Larger Whisper Model (RTX 3090 Optimization)
Edit the code to use `whisper.load_model("large-v3")` instead of default for better accuracy.

## Expected Workflow
1. **You speak** → Microphone captures audio
2. **Whisper** → Transcribes speech to text
3. **Ollama (qwen2.5:32b)** → Generates response
4. **ChatterBox TTS** → Converts response to speech
5. **Speaker** → You hear the response

## Troubleshooting

### PyAudio Installation Issues (Windows)
If pip fails, install via:
```powershell
pip install pipwin
pipwin install pyaudio
```

### CUDA/GPU Issues
Ensure PyTorch is installed with CUDA:
```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Microphone Not Detected
Check Windows Sound settings and ensure default input device is set correctly.

## Files Location
- Repository: `D:\AI\local-talking-llm\`
- Ollama models: `D:\AI\ollama-models\`
- Voice samples (if cloning): `D:\AI\voice-samples\`
