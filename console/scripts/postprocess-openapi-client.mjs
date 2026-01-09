import { readFile, writeFile } from 'node:fs/promises'

const ROOT = new URL('../src/lib/api/generated/models/', import.meta.url)

const patches = [
	{
		file: new URL('JSONValue_Input.ts', ROOT),
		re: /^export type JSONValue_Input\s*=\s*\([^;]+\);\s*$/m,
		replacement:
			'export type JSONValue_Input = null | boolean | number | string | Record<string, unknown> | unknown[];',
	},
	{
		file: new URL('JSONValue_Output.ts', ROOT),
		re: /^export type JSONValue_Output\s*=\s*\([^;]+\);\s*$/m,
		replacement:
			'export type JSONValue_Output = null | boolean | number | string | Record<string, unknown> | unknown[];',
	},
]

let changedAny = false

for (const { file, re, replacement } of patches) {
	let original
	try {
		original = await readFile(file, 'utf8')
	} catch {
		continue
	}

	const next = original.replace(re, replacement)
	if (next !== original) {
		await writeFile(file, next, 'utf8')
		changedAny = true
	}
}

if (changedAny) {
	console.log('[postprocess-openapi-client] patched JSONValue models for TS compatibility')
} else {
	console.warn(
		'[postprocess-openapi-client] no changes applied; the generated output may have changed format.'
	)
}
