import { readFile, writeFile } from 'node:fs/promises'

const TYPES_PATH = new URL('../src/lib/api/types.ts', import.meta.url)

const original = await readFile(TYPES_PATH, 'utf8')

let next = original

next = next.replace(
	/"JSONObject-Input"\s*:\s*\{\s*\[key: string\]: components\["schemas"\]\["JSONValue-Input"\];\s*\};/m,
	'"JSONObject-Input": Record<string, components["schemas"]["JSONValue-Input"]>;'
)

next = next.replace(
	/"JSONObject-Output"\s*:\s*\{\s*\[key: string\]: components\["schemas"\]\["JSONValue-Output"\];\s*\};/m,
	'"JSONObject-Output": Record<string, components["schemas"]["JSONValue-Output"]>;'
)

next = next.replace(
	/"JSONValue-Input"\s*:\s*[\s\S]*?components\["schemas"\]\["JSONValue-Input"\][\s\S]*?\|\s*null;/m,
	'"JSONValue-Input": null | boolean | number | string | Record<string, unknown> | unknown[];'
)

next = next.replace(
	/"JSONValue-Output"\s*:\s*[\s\S]*?components\["schemas"\]\["JSONValue-Output"\][\s\S]*?\|\s*null;/m,
	'"JSONValue-Output": null | boolean | number | string | Record<string, unknown> | unknown[];'
)

if (next === original) {
	console.warn(
		'[postprocess-openapi-types] no changes applied; the generated output may have changed format.'
	)
} else {
	console.log('[postprocess-openapi-types] patched JSONValue schemas for TS compatibility')
}

await writeFile(TYPES_PATH, next, 'utf8')
