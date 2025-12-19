import { ServiceConfig } from "../types";

export const SERVICES_CONFIG: readonly ServiceConfig[] = [
  {
    id: "openwebui",
    name: "Open WebUI",
    port: 3000,
    icon: "\uD83D\uDCAC",
    description:
      "Chat interface for LLMs. Connect to Ollama models for conversations, code assistance, and more.",
    tags: ["Chat", "LLM", "Ollama"],
    cardClass: "card-openwebui",
    section: "main",
    external: true,
    proxyId: "openwebui",
    models: ["*"], // Uses any Ollama model
  },
  {
    id: "comfyui",
    name: "ComfyUI",
    port: 8188,
    icon: "\uD83C\uDFA8",
    description:
      "Node-based image generation with Stable Diffusion. Create images with advanced workflows.",
    tags: ["Image Gen", "Stable Diffusion", "Workflows"],
    cardClass: "card-comfyui",
    section: "main",
    proxyId: "comfyui",
  },
  {
    id: "alltalk",
    name: "AllTalk TTS",
    port: 7851,
    icon: "\uD83C\uDF99\uFE0F",
    description:
      "Text-to-speech with voice cloning. Create custom voices from audio samples using XTTS v2.",
    tags: ["TTS", "Voice Clone", "XTTS"],
    cardClass: "card-alltalk",
    section: "main",
    proxyId: "alltalk",
  },
  {
    id: "ollama",
    name: "Ollama API",
    port: 11434,
    icon: "\uD83E\uDD99",
    description:
      "REST API for running local LLMs. Backend for Open WebUI and other applications.",
    tags: ["API", "Qwen 32B", "Backend"],
    cardClass: "card-ollama",
    section: "main",
    external: true,
    proxyId: "ollama",
    models: ["*"], // Uses any Ollama model
  },
  {
    id: "wan2gp",
    name: "Wan2GP Video",
    port: 7860,
    icon: "\uD83C\uDFAC",
    description:
      "AI video generation with Wan 2.1/2.2, LTX Video, Hunyuan Video, and Flux 2. Text-to-video and image-to-video.",
    tags: ["Video Gen", "Wan 2.1", "LTX Video"],
    cardClass: "card-wan2gp",
    section: "main",
    proxyId: "wan2gp",
  },
  {
    id: "n8n",
    name: "N8N Workflows",
    port: 5678,
    icon: "🔄",
    description:
      "Visual workflow automation to orchestrate local AI tools, APIs, and webhooks.",
    tags: ["Automation", "Workflows", "Webhooks"],
    cardClass: "card-n8n",
    section: "main",
    proxyId: "n8n",
  },
  {
    id: "weaviate",
    name: "Weaviate Console",
    port: 8081,
    icon: "\uD83E\uDDE0",
    description:
      "Vector database explorer for semantic search, RAG, and long-term memory. Query and visualize data.",
    tags: ["Vector DB", "RAG", "Memory"],
    cardClass: "card-weaviate",
    section: "main",
    external: true,
    proxyId: "weaviate-console",
    instructions:
      "Connect to http://localhost:8080 (Weaviate API) to explore collections and query data.",
  },
  {
    id: "yue",
    name: "YuE Music",
    port: 7870,
    icon: "\uD83C\uDFB5",
    description:
      "Full song generation with vocals from lyrics. Supports multiple languages and genres like EDM, pop, rock.",
    tags: ["Text-to-Music", "Vocals", "5 min songs"],
    cardClass: "card-yue",
    section: "music",
    proxyId: "yue",
  },
  {
    id: "diffrhythm",
    name: "DiffRhythm",
    port: 7871,
    icon: "\uD83C\uDFBC",
    description:
      "Fast full-song generation. Creates 4+ minute songs with vocals and instrumentals in ~10 seconds.",
    tags: ["Fast Gen", "Full Songs", "Diffusion"],
    cardClass: "card-diffrhythm",
    section: "music",
    proxyId: "diffrhythm",
  },
  {
    id: "musicgen",
    name: "MusicGen",
    port: 7872,
    icon: "\uD83C\uDFB9",
    description:
      "Meta's AudioCraft for high-quality instrumental music generation from text or melody prompts.",
    tags: ["Instrumental", "Meta AI", "Melody Input"],
    cardClass: "card-musicgen",
    section: "music",
    proxyId: "musicgen",
  },
  {
    id: "stable_audio",
    name: "Stable Audio",
    port: 7873,
    icon: "\uD83D\uDD0A",
    description:
      "Sound effects, drum beats, ambient sounds, and production elements. Up to 47 second audio clips.",
    tags: ["Sound FX", "Beats", "Ambient"],
    cardClass: "card-stableaudio",
    section: "music",
    proxyId: "stable-audio",
  },
  {
    id: "a1111",
    name: "A1111 WebUI",
    port: 7861,
    icon: "\uD83D\uDDBC\uFE0F",
    description:
      "AUTOMATIC1111 Stable Diffusion Web UI. The classic interface for image generation with extensive features.",
    tags: ["Image Gen", "SD", "Classic"],
    cardClass: "card-a1111",
    section: "image",
    proxyId: "a1111",
  },
  {
    id: "forge",
    name: "SD Forge",
    port: 7862,
    icon: "\u2692\uFE0F",
    description:
      "Stable Diffusion WebUI Forge. Optimized fork with better memory management and faster generation.",
    tags: ["Image Gen", "SD", "Optimized"],
    cardClass: "card-forge",
    section: "image",
    proxyId: "forge",
  },
  {
    id: "fooocus",
    name: "Fooocus",
    port: 7865,
    icon: "\uD83C\uDFAF",
    description:
      "Simplified Stable Diffusion interface inspired by Midjourney. Focus on prompts, minimal settings.",
    tags: ["Image Gen", "Simple", "Midjourney-like"],
    cardClass: "card-fooocus",
    section: "image",
    proxyId: "fooocus",
  },
];

export const getApiBase = (): string => {
  // Use same origin (single-port deployment)
  return window.location.origin;
};

export const getServiceUrl = (port: number, proxyId?: string): string => {
  // If proxyId is provided and we're not on localhost, use the reverse proxy
  const isLocalhost =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";

  if (proxyId && !isLocalhost) {
    // Use nginx direct path for external access (matches nginx location blocks)
    return `${window.location.origin}/${proxyId}/`;
  }

  // Direct port access for local network
  // Use environment variable for development host, fallback to current hostname
  const host = import.meta.env.VITE_DEV_HOST || window.location.hostname;
  return `http://${host}:${port}`;
};
