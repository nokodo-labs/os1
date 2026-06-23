import type {
	AssetResponse,
	DefaultPermissionsSettings,
	MediaAssetDraft,
	PwaAssetDraft,
	PwaManifestAssetsDraft,
	PwaManifestAssetsPatch,
} from './types'

export function pwaAsset(): PwaAssetDraft {
	return { source: 'default', url: '' }
}

export function defaultPwaAssets(): PwaManifestAssetsDraft {
	return {
		icon_1024_maskable: pwaAsset(),
		icon_512_any: pwaAsset(),
		shortcut_notes: pwaAsset(),
		shortcut_reminders: pwaAsset(),
		shortcut_calendar: pwaAsset(),
		shortcut_messages: pwaAsset(),
		shortcut_projects: pwaAsset(),
		shortcut_library: pwaAsset(),
		shortcut_social: pwaAsset(),
		shortcut_settings: pwaAsset(),
		screenshot_narrow_1: pwaAsset(),
		screenshot_narrow_2: pwaAsset(),
		screenshot_narrow_3: pwaAsset(),
		screenshot_narrow_4: pwaAsset(),
		screenshot_narrow_5: pwaAsset(),
		screenshot_wide_1: pwaAsset(),
		screenshot_wide_2: pwaAsset(),
		screenshot_wide_3: pwaAsset(),
		screenshot_wide_4: pwaAsset(),
		screenshot_wide_5: pwaAsset(),
		screenshot_wide_6: pwaAsset(),
		screenshot_wide_7: pwaAsset(),
		screenshot_wide_8: pwaAsset(),
	}
}

export function toMediaAsset(value: AssetResponse | undefined): MediaAssetDraft {
	if (value?.url) return { source: 'custom', url: value.url }
	const source = value?.source === 'cdn' || value?.source === 'custom' ? value.source : 'default'
	return { source, url: '' }
}

export function toPwaAsset(value: AssetResponse | undefined): PwaAssetDraft {
	const source =
		value?.source === 'cdn' || value?.source === 'custom' || value?.source === 'disabled'
			? value.source
			: 'default'
	if (source !== 'disabled' && value?.url) return { source: 'custom', url: value.url }
	return { source, url: '' }
}

export function clonePwaAssets(value: PwaManifestAssetsDraft): PwaManifestAssetsDraft {
	return {
		icon_1024_maskable: { ...value.icon_1024_maskable },
		icon_512_any: { ...value.icon_512_any },
		shortcut_notes: { ...value.shortcut_notes },
		shortcut_reminders: { ...value.shortcut_reminders },
		shortcut_calendar: { ...value.shortcut_calendar },
		shortcut_messages: { ...value.shortcut_messages },
		shortcut_projects: { ...value.shortcut_projects },
		shortcut_library: { ...value.shortcut_library },
		shortcut_social: { ...value.shortcut_social },
		shortcut_settings: { ...value.shortcut_settings },
		screenshot_narrow_1: { ...value.screenshot_narrow_1 },
		screenshot_narrow_2: { ...value.screenshot_narrow_2 },
		screenshot_narrow_3: { ...value.screenshot_narrow_3 },
		screenshot_narrow_4: { ...value.screenshot_narrow_4 },
		screenshot_narrow_5: { ...value.screenshot_narrow_5 },
		screenshot_wide_1: { ...value.screenshot_wide_1 },
		screenshot_wide_2: { ...value.screenshot_wide_2 },
		screenshot_wide_3: { ...value.screenshot_wide_3 },
		screenshot_wide_4: { ...value.screenshot_wide_4 },
		screenshot_wide_5: { ...value.screenshot_wide_5 },
		screenshot_wide_6: { ...value.screenshot_wide_6 },
		screenshot_wide_7: { ...value.screenshot_wide_7 },
		screenshot_wide_8: { ...value.screenshot_wide_8 },
	}
}

export function pwaAssetsKey(value: PwaManifestAssetsDraft): string {
	return JSON.stringify(value)
}

export function pwaAssetsFromResponse(
	value: Partial<Record<keyof PwaManifestAssetsDraft, AssetResponse>> | null | undefined
): PwaManifestAssetsDraft {
	return {
		icon_1024_maskable: toPwaAsset(value?.icon_1024_maskable),
		icon_512_any: toPwaAsset(value?.icon_512_any),
		shortcut_notes: toPwaAsset(value?.shortcut_notes),
		shortcut_reminders: toPwaAsset(value?.shortcut_reminders),
		shortcut_calendar: toPwaAsset(value?.shortcut_calendar),
		shortcut_messages: toPwaAsset(value?.shortcut_messages),
		shortcut_projects: toPwaAsset(value?.shortcut_projects),
		shortcut_library: toPwaAsset(value?.shortcut_library),
		shortcut_social: toPwaAsset(value?.shortcut_social),
		shortcut_settings: toPwaAsset(value?.shortcut_settings),
		screenshot_narrow_1: toPwaAsset(value?.screenshot_narrow_1),
		screenshot_narrow_2: toPwaAsset(value?.screenshot_narrow_2),
		screenshot_narrow_3: toPwaAsset(value?.screenshot_narrow_3),
		screenshot_narrow_4: toPwaAsset(value?.screenshot_narrow_4),
		screenshot_narrow_5: toPwaAsset(value?.screenshot_narrow_5),
		screenshot_wide_1: toPwaAsset(value?.screenshot_wide_1),
		screenshot_wide_2: toPwaAsset(value?.screenshot_wide_2),
		screenshot_wide_3: toPwaAsset(value?.screenshot_wide_3),
		screenshot_wide_4: toPwaAsset(value?.screenshot_wide_4),
		screenshot_wide_5: toPwaAsset(value?.screenshot_wide_5),
		screenshot_wide_6: toPwaAsset(value?.screenshot_wide_6),
		screenshot_wide_7: toPwaAsset(value?.screenshot_wide_7),
		screenshot_wide_8: toPwaAsset(value?.screenshot_wide_8),
	}
}

export function pwaAssetToPatch(value: PwaAssetDraft) {
	return { source: value.source, url: value.source === 'custom' ? value.url || null : null }
}

export function pwaAssetsToPatch(value: PwaManifestAssetsDraft): PwaManifestAssetsPatch {
	return {
		icon_1024_maskable: pwaAssetToPatch(value.icon_1024_maskable),
		icon_512_any: pwaAssetToPatch(value.icon_512_any),
		shortcut_notes: pwaAssetToPatch(value.shortcut_notes),
		shortcut_reminders: pwaAssetToPatch(value.shortcut_reminders),
		shortcut_calendar: pwaAssetToPatch(value.shortcut_calendar),
		shortcut_messages: pwaAssetToPatch(value.shortcut_messages),
		shortcut_projects: pwaAssetToPatch(value.shortcut_projects),
		shortcut_library: pwaAssetToPatch(value.shortcut_library),
		shortcut_social: pwaAssetToPatch(value.shortcut_social),
		shortcut_settings: pwaAssetToPatch(value.shortcut_settings),
		screenshot_narrow_1: pwaAssetToPatch(value.screenshot_narrow_1),
		screenshot_narrow_2: pwaAssetToPatch(value.screenshot_narrow_2),
		screenshot_narrow_3: pwaAssetToPatch(value.screenshot_narrow_3),
		screenshot_narrow_4: pwaAssetToPatch(value.screenshot_narrow_4),
		screenshot_narrow_5: pwaAssetToPatch(value.screenshot_narrow_5),
		screenshot_wide_1: pwaAssetToPatch(value.screenshot_wide_1),
		screenshot_wide_2: pwaAssetToPatch(value.screenshot_wide_2),
		screenshot_wide_3: pwaAssetToPatch(value.screenshot_wide_3),
		screenshot_wide_4: pwaAssetToPatch(value.screenshot_wide_4),
		screenshot_wide_5: pwaAssetToPatch(value.screenshot_wide_5),
		screenshot_wide_6: pwaAssetToPatch(value.screenshot_wide_6),
		screenshot_wide_7: pwaAssetToPatch(value.screenshot_wide_7),
		screenshot_wide_8: pwaAssetToPatch(value.screenshot_wide_8),
	}
}

export function arrayEquals(a: string[], b: string[]): boolean {
	return a.length === b.length && a.every((v, i) => v === b[i])
}

export function toStringOrEmpty(v: unknown): string {
	if (v === null || v === undefined) return ''
	return String(v)
}

export function toBool(v: unknown): boolean {
	return Boolean(v)
}

export function formatJsonObject(value: unknown): string {
	if (value === null || typeof value !== 'object' || Array.isArray(value)) return '{}'
	return JSON.stringify(value, null, 2)
}

export function parseJsonObject(value: string): Record<string, unknown> {
	const trimmed = value.trim()
	if (!trimmed) return {}
	const parsed: unknown = JSON.parse(trimmed)
	if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
		throw new Error('expected JSON object')
	}
	return Object.fromEntries(Object.entries(parsed))
}

export function parseCommaList(value: string): string[] {
	return value
		.split(',')
		.map((s) => s.trim())
		.filter(Boolean)
}

export function toRerankDefaultStrategy(value: string | undefined): 'none' | 'external' | 'native' {
	if (value === 'none' || value === 'external' || value === 'native') return value
	return 'native'
}

export function normalizeDefaultPermissions(
	input: DefaultPermissionsSettings
): DefaultPermissionsSettings {
	return {
		resource_access: {
			thread: input.resource_access?.thread ?? null,
			project: input.resource_access?.project ?? null,
			file: input.resource_access?.file ?? null,
			calendar: input.resource_access?.calendar ?? null,
			note: input.resource_access?.note ?? null,
			group: input.resource_access?.group ?? null,
			reminder_list: input.resource_access?.reminder_list ?? null,
		},
		action_permissions: [...(input.action_permissions ?? [])].sort(),
	}
}

export function defaultPermissionsKey(value: DefaultPermissionsSettings): string {
	return JSON.stringify(normalizeDefaultPermissions(value))
}

export function buildDefaultPermissionsPatch(value: DefaultPermissionsSettings) {
	return {
		resource_access: {
			thread: value.resource_access?.thread ?? null,
			project: value.resource_access?.project ?? null,
			file: value.resource_access?.file ?? null,
			calendar: value.resource_access?.calendar ?? null,
			note: value.resource_access?.note ?? null,
			group: value.resource_access?.group ?? null,
			reminder_list: value.resource_access?.reminder_list ?? null,
		},
		action_permissions: value.action_permissions ?? [],
	}
}
