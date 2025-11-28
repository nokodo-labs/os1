import { svelte } from '@sveltejs/vite-plugin-svelte'
import path from 'node:path'
import { defineConfig } from 'vite'

export default defineConfig({
    plugins: [svelte()],
    resolve: {
        alias: {
            $lib: path.resolve(__dirname, 'src/lib'),
        },
    },
    server: {
        port: 4175,
        host: true,
    },
    build: {
        outDir: 'dist',
        sourcemap: true,
    },
})
