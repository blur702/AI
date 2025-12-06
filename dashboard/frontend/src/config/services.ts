import { ServiceConfig } from '../types';

export const SERVICES_CONFIG: ServiceConfig[] = [
  {
    id: 'openwebui',
    name: 'Open WebUI',
    port: 3000,
    icon: '\uD83D\uDCAC',
    description: 'Chat interface for LLMs. Connect to Ollama models for conversations, code assistance, and more.',
    tags: ['Chat', 'LLM', 'Ollama'],
    cardClass: 'card-openwebui',
    section: 'main',
    external: true
  },
  {
    id: 'comfyui',
    name: 'ComfyUI',
    port: 8188,
    icon: '\uD83C\uDFA8',
    description: 'Node-based image generation with Stable Diffusion. Create images with advanced workflows.',
    tags: ['Image Gen', 'Stable Diffusion', 'Workflows'],
    cardClass: 'card-comfyui',
    section: 'main'
  },
  {
    id: 'alltalk',
    name: 'AllTalk TTS',
    port: 7851,
    icon: '\uD83C\uDF99\uFE0F',
    description: 'Text-to-speech with voice cloning. Create custom voices from audio samples using XTTS v2.',
    tags: ['TTS', 'Voice Clone', 'XTTS'],
    cardClass: 'card-alltalk',
    section: 'main'
  },
  {
    id: 'ollama',
    name: 'Ollama API',
    port: 11434,
    icon: '\uD83E\uDD99',
    description: 'REST API for running local LLMs. Backend for Open WebUI and other applications.',
    tags: ['API', 'Qwen 32B', 'Backend'],
    cardClass: 'card-ollama',
    section: 'main',
    external: true
  },
  {
    id: 'wan2gp',
    name: 'Wan2GP Video',
    port: 7860,
    icon: '\uD83C\uDFAC',
    description: 'AI video generation with Wan 2.1/2.2, LTX Video, Hunyuan Video, and Flux 2. Text-to-video and image-to-video.',
    tags: ['Video Gen', 'Wan 2.1', 'LTX Video'],
    cardClass: 'card-wan2gp',
    section: 'main'
  },
  {
    id: 'n8n',
    name: 'N8N Workflows',
    port: 5678,
    icon: 'n8n',
    description: 'Visual workflow automation to orchestrate local AI tools, APIs, and webhooks.',
    tags: ['Automation', 'Workflows', 'Webhooks'],
    cardClass: 'card-n8n',
    section: 'main'
  },
  {
    id: 'yue',
    name: 'YuE Music',
    port: 7870,
    icon: '\uD83C\uDFB5',
    description: 'Full song generation with vocals from lyrics. Supports multiple languages and genres like EDM, pop, rock.',
    tags: ['Text-to-Music', 'Vocals', '5 min songs'],
    cardClass: 'card-yue',
    section: 'music'
  },
  {
    id: 'diffrhythm',
    name: 'DiffRhythm',
    port: 7871,
    icon: '\uD83C\uDFBC',
    description: 'Fast full-song generation. Creates 4+ minute songs with vocals and instrumentals in ~10 seconds.',
    tags: ['Fast Gen', 'Full Songs', 'Diffusion'],
    cardClass: 'card-diffrhythm',
    section: 'music'
  },
  {
    id: 'musicgen',
    name: 'MusicGen',
    port: 7872,
    icon: '\uD83C\uDFB9',
    description: "Meta's AudioCraft for high-quality instrumental music generation from text or melody prompts.",
    tags: ['Instrumental', 'Meta AI', 'Melody Input'],
    cardClass: 'card-musicgen',
    section: 'music'
  },
  {
    id: 'stable_audio',
    name: 'Stable Audio',
    port: 7873,
    icon: '\uD83D\uDD0A',
    description: 'Sound effects, drum beats, ambient sounds, and production elements. Up to 47 second audio clips.',
    tags: ['Sound FX', 'Beats', 'Ambient'],
    cardClass: 'card-stableaudio',
    section: 'music'
  }
];

export const getApiBase = (): string => {
  // Use same origin (single-port deployment)
  return window.location.origin;
};

export const getServiceUrl = (port: number): string => {
  const host = window.location.hostname || '10.0.0.138';
  return `http://${host}:${port}`;
};
