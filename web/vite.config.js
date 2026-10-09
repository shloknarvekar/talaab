import { copyFileSync, mkdirSync } from 'node:fs';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// MapLibre (the AWS dark basemap) runs its tile work in a web worker that it locates at runtime, so neither the
// dev server nor the build can see it. Serve the worker and the module it imports from /maplibre/ instead; MapView
// calls setWorkerUrl('/maplibre/maplibre-gl-worker.mjs'). public/maplibre is generated, not committed.
function maplibreWorker() {
  return {
    name: 'talaab-maplibre-worker',
    buildStart() {
      mkdirSync('public/maplibre', { recursive: true });
      for (const file of ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs']) {
        copyFileSync(`node_modules/maplibre-gl/dist/${file}`, `public/maplibre/${file}`);
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), maplibreWorker()],
  server: {
    port: 5173,
  },
});
