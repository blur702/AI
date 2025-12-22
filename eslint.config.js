import eslint from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";

export default [
  eslint.configs.recommended,
  {
    files: ["**/*.ts", "**/*.tsx"],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
      },
      globals: {
        // Browser-like globals used in fixtures
        fetch: "readonly",
        RequestInit: "readonly",
        setTimeout: "readonly",
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
    },
    rules: {
      // TypeScript specific rules
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/explicit-function-return-type": "off",
      "@typescript-eslint/explicit-module-boundary-types": "off",

      // General rules
      "no-console": "off",
      "no-unused-vars": "off", // Use TypeScript version instead
      "prefer-const": "warn",
      "no-var": "error",
    },
  },
  {
    files: ["**/*.js", "**/*.jsx"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        // Node/browser globals used in fixtures and tools
        require: "readonly",
        module: "readonly",
        console: "readonly",
        fetch: "readonly",
        setTimeout: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "prefer-const": "warn",
      "no-var": "error",
    },
  },
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/build/**",
      "**/.venv/**",
      "**/*_env/**",
      "**/venv/**",
      "**/ComfyUI/**",
      "**/alltalk_tts/**",
      "**/audiocraft/**",
      "**/DiffRhythm/**",
      "**/stable-audio-tools/**",
      "**/Wan2GP/**",
      "**/YuE/**",
      "**/open-webui/**",
      "**/MusicGPT/**",
      "**/nginx/**",
      // Test/parser fixtures that intentionally use globals and unused symbols
      "api_gateway/services/tests/fixtures/**",
      "**/*.min.js",
      "**/coverage/**",
      "**/reports/**",
    ],
  },
];
