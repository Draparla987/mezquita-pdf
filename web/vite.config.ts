import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

// iOS Safari 16+ y navegadores de escritorio recientes.
const objetivo = ['safari16', 'ios16', 'chrome109', 'edge109', 'firefox115'];

export default defineConfig({
  // Rutas relativas: la app funciona servida desde cualquier subcarpeta (p. ej. GitHub Pages).
  base: './',
  build: {
    target: objetivo,
    chunkSizeWarningLimit: 2500,
    sourcemap: false,
  },
  worker: {
    format: 'es',
  },
  optimizeDeps: {
    // pdf.js se sirve tal cual (incluye su propio worker)
    exclude: ['pdfjs-dist'],
  },
  plugins: [
    VitePWA({
      registerType: 'prompt',
      injectRegister: false,
      includeAssets: ['icons/*.png'],
      manifest: {
        id: './',
        name: 'Mezquita PDF',
        short_name: 'Mezquita PDF',
        description: 'Abre, edita, firma y comparte tus documentos PDF. Todo en tu dispositivo.',
        lang: 'es-ES',
        dir: 'ltr',
        start_url: './',
        scope: './',
        display: 'standalone',
        orientation: 'any',
        theme_color: '#8E1B2C',
        background_color: '#FBF8F4',
        categories: ['productivity', 'business', 'utilities'],
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: 'icons/icon-maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: 'icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          { src: 'icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' },
        ],
      },
      workbox: {
        // Todo se precarga: la app debe funcionar sin conexión desde la primera visita.
        globPatterns: ['**/*.{js,mjs,css,html,png,svg,ico,woff2,webmanifest,bcmap,pfb,ttf,wasm,icc}'],
        globIgnores: ['**/LICENSE*'],
        maximumFileSizeToCacheInBytes: 8 * 1024 * 1024,
        navigateFallback: 'index.html',
        cleanupOutdatedCaches: true,
        clientsClaim: false,
        skipWaiting: false,
      },
      devOptions: { enabled: false },
    }),
  ],
});
