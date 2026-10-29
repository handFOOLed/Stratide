import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    target: 'es2022',
    modulePreload: false,
    rollupOptions: {
      output: { entryFileNames: 'assets/app.js', assetFileNames: 'assets/app.[ext]' },
    },
  },
});
