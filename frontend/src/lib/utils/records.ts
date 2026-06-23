/** shared helpers for narrowing unknown values into plain records and primitives. */

/** returns true when a value is a plain object record. */
export function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** parses a json string only when its top-level value is a plain object record. */
export function parseJsonRecord(json: string): Record<string, unknown> | null {
	try {
		const parsed = JSON.parse(json)
		return isRecord(parsed) ? parsed : null
	} catch {
		return null
	}
}

/** trims and returns a string only when it has visible content. */
export function readNonEmptyString(value: unknown): string | null {
	if (typeof value !== 'string') return null
	const trimmed = value.trim()
	return trimmed.length > 0 ? trimmed : null
}

/** returns a number only when it is finite. */
export function readFiniteNumber(value: unknown): number | null {
	return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** reads a non-empty string field from a nullable record. */
export function readStringField(
	record: Record<string, unknown> | null | undefined,
	field: string
): string | null {
	if (!record) return null
	return readNonEmptyString(record[field])
}

/** reads a numeric field from a nullable record. */
export function readNumberField(
	record: Record<string, unknown> | null | undefined,
	field: string
): number | null {
	if (!record) return null
	const value = record[field]
	return typeof value === 'number' ? value : null
}

/** reads a nested record field from a nullable record. */
export function readRecordField(
	record: Record<string, unknown> | null | undefined,
	field: string
): Record<string, unknown> | null {
	if (!record) return null
	const value = record[field]
	return isRecord(value) ? value : null
}

/** filters an unknown array down to plain object records. */
export function readRecordArray(value: unknown): Record<string, unknown>[] {
	if (!Array.isArray(value)) return []
	return value.filter((item): item is Record<string, unknown> => isRecord(item))
}
