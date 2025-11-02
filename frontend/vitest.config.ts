import { svelte, vitePreprocess } from '@sveltejs/vite-plugin-svelte'
import { svelteTesting } from '@testing-library/svelte/vite'
import { resolve } from 'path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
    plugins: [
        svelte({
            hot: !process.env.VITEST,
            compilerOptions: {
                runes: true,
            },
            preprocess: vitePreprocess(),
        }),
        svelteTesting(),
    ],
    test: {
        globals: true,
        environment: 'happy-dom',
        setupFiles: ['./src/test/setup.ts'],
        include: ['src/**/*.{test,spec}.{js,ts}'],
        alias: {
            $lib: resolve(__dirname, './src/lib'),
        },
        coverage: {
            provider: 'v8',
            reporter: ['text', 'json', 'html'],
            exclude: [
                'node_modules/',
                'src/test/',
                '**/*.d.ts',
                '**/*.config.*',
                '**/mockData',
                '**/types.ts',
            ],
        },
    },
    resolve: {
        alias: {
            $lib: resolve(__dirname, './src/lib'),
        },
    },
})
