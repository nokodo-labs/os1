import path from 'node:path'
import { defineConfig } from 'vite'
import type {} from 'vitest/config'

export default defineConfig({
	test: {
		globals: true,
		environment: 'happy-dom',
		include: ['src/**/*.{test,spec}.{js,ts}'],
		alias: {
			$lib: path.resolve(__dirname, './src/lib'),
		},
		coverage: {
			provider: 'v8',
			reporter: ['text', 'json', 'html'],
			exclude: [
				'node_modules/',
				'build/',
				'.svelte-kit/',
				'**/*.d.ts',
				'**/*.config.*',
				'src/lib/api/generated/',
				'src/lib/api/types.ts',
			],
		},
	},
})
