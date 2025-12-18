import { defineConfig, type UserConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }): UserConfig => ({
  plugins: [react()],

  // Base path for deployed assets
  base: mode === 'production' ? '/' : '/',

  server: {
    port: 3001,
    host: '0.0.0.0'
  },

  build: {
    outDir: 'dist',

    // Generate source maps only for development
    sourcemap: mode !== 'production',

    // CSS code splitting for better caching
    cssCodeSplit: true,

    // Inline assets smaller than 4kb
    assetsInlineLimit: 4096,

    // Warn if chunks exceed 500kb
    chunkSizeWarningLimit: 500,

    // Use terser for production minification
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: mode === 'production',
        drop_debugger: true,
      },
    },

    rollupOptions: {
      output: {
        // Manual chunks for vendor code splitting
        manualChunks: {
          // React core
          'react-vendor': ['react', 'react-dom'],

          // React Router
          'router': ['react-router-dom'],

          // Material UI core
          'mui-core': ['@mui/material', '@emotion/react', '@emotion/styled'],

          // Material UI icons (large, separate chunk)
          'mui-icons': ['@mui/icons-material'],

          // Charts library
          'charts': ['recharts'],

          // Socket.io client
          'socket': ['socket.io-client'],
        },

        // Asset file naming with hashes for cache busting
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name?.split('.') || []
          const ext = info[info.length - 1]
          if (/png|jpe?g|svg|gif|tiff|bmp|ico/i.test(ext)) {
            return 'assets/images/[name]-[hash][extname]'
          }
          if (/woff2?|eot|ttf|otf/i.test(ext)) {
            return 'assets/fonts/[name]-[hash][extname]'
          }
          return 'assets/[name]-[hash][extname]'
        },

        // Chunk file naming
        chunkFileNames: 'assets/js/[name]-[hash].js',

        // Entry file naming
        entryFileNames: 'assets/js/[name]-[hash].js',
      },
    },
  },

  // Preview server configuration
  preview: {
    port: 3001,
    host: '0.0.0.0',
  },
}))
