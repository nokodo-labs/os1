import adapter from '@sveltejs/adapter-static'
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte'

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({
			fallback: '200.html',
		}),
		paths: {
			relative: false,
		},
		alias: {
			$lib: 'src/lib',
		},
		prerender: {
			handleHttpError: 'warn',
		},
	},
	compilerOptions: {
		runes: true,
	},
}

export default config
