export function toStringOrEmpty(value: unknown): string {
	if (value === null || value === undefined) return ''
	return typeof value === 'string' ? value : String(value)
}

export function asNumberOrNull(value: unknown): number | null {
	const trimmed = toStringOrEmpty(value).trim()
	if (!trimmed) return null
	const n = Number(trimmed)
	return Number.isFinite(n) ? n : null
}

export function asNumberOrUndefined(value: unknown): number | undefined {
	const trimmed = toStringOrEmpty(value).trim()
	if (!trimmed) return undefined
	const n = Number(trimmed)
	return Number.isFinite(n) ? n : undefined
}
