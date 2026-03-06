import { sveltekit } from '@sveltejs/kit/vite'
import { defineConfig } from 'vite'

export default defineConfig({
	plugins: [sveltekit()],
	build: {
		// TODO: large chunks come from mermaid (~2MB), shiki (~1.9MB), and other heavy libs.
		// proper fix requires dynamic imports in components that use these libraries.
		// for now, suppress the warning as it doesn't affect production.
		chunkSizeWarningLimit: 600,
	},
	server: {
		port: 888,
		host: true,
		allowedHosts: true,
		proxy: {
			'/health': {
				target: 'http://localhost:1383',
				changeOrigin: true,
			},
		},
	},
})
