import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({
			fallback: "index.html", // SPA mode
		}),
		alias: {
			$lib: "src/lib",
		},
	},
	compilerOptions: {
		runes: true,
	},
};

export default config;
