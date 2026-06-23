import { describe, expect, it } from 'vitest'

import { asNumberOrNull, asNumberOrUndefined } from './settingsNumbers'

describe('settings number serialization', () => {
	it('accepts string and number input values', () => {
		expect(asNumberOrNull(' 12 ')).toBe(12)
		expect(asNumberOrNull(12)).toBe(12)
		expect(asNumberOrUndefined(' 0.35 ')).toBe(0.35)
		expect(asNumberOrUndefined(0.35)).toBe(0.35)
	})

	it('returns empty values for blank or invalid input', () => {
		expect(asNumberOrNull('')).toBeNull()
		expect(asNumberOrNull(null)).toBeNull()
		expect(asNumberOrNull('abc')).toBeNull()
		expect(asNumberOrUndefined('')).toBeUndefined()
		expect(asNumberOrUndefined(undefined)).toBeUndefined()
		expect(asNumberOrUndefined('abc')).toBeUndefined()
	})
})
