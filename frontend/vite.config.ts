import { sveltekit } from '@sveltejs/kit/vite'
import { defineConfig } from 'vite'

export default defineConfig({
	plugins: [sveltekit()],
	build: {
		// TODO: Large chunks come from mermaid (~2MB), shiki (~1.9MB), and other heavy libs.
		// Proper fix requires dynamic imports in components that use these libraries.
		// For now, suppress the warning as it doesn't affect production.
		chunkSizeWarningLimit: 600,
	},
	server: {
		port: 888,
		host: true,
		proxy: {
			'/v1': {
				target: 'http://localhost:1383',
				changeOrigin: true,
			},
			'/health': {
				target: 'http://localhost:1383',
				changeOrigin: true,
			},
		},
	},
})
