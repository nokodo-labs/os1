import { vitePreprocess } from '@sveltejs/vite-plugin-svelte'

export default {
    // Consult https://svelte.dev/docs/kit/integrations
    // for more information about preprocessors
    preprocess: vitePreprocess(),
    compilerOptions: {
        runes: true,
    },
    kit: {
        alias: {
            $lib: './src/lib',
            '$lib/*': './src/lib/*',
        },
    },
}
