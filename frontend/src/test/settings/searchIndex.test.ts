import {
	buildSettingsIndex,
	fieldHaystack,
	searchSettings,
} from '$lib/components/settings/searchIndex'
import { settingsSections } from '$lib/components/settings/sections'
import { describe, expect, it } from 'vitest'

const visibleSections = settingsSections.filter((section) => !section.adminOnly)

describe('settings index', () => {
	it('indexes at least one field for every section', () => {
		for (const section of settingsSections) {
			expect(section.fields.length, `${section.id} has no indexed fields`).toBeGreaterThan(0)
		}
	})

	it('keeps field ids unique within a section', () => {
		for (const section of settingsSections) {
			const ids = section.fields.map((field) => field.id)
			expect(new Set(ids).size, `${section.id} has duplicate field ids`).toBe(ids.length)
		}
	})

	it('flattens every field into the index', () => {
		const entries = buildSettingsIndex()
		const total = settingsSections.reduce((sum, section) => sum + section.fields.length, 0)

		expect(entries).toHaveLength(total)
		expect(
			entries.every((entry) => entry.haystack.includes(entry.field.label.toLowerCase()))
		).toBe(true)
	})

	it('carries the section label into a field haystack', () => {
		const section = settingsSections[0]
		const field = section.fields[0]

		expect(fieldHaystack(section, field)).toContain(section.label.toLowerCase())
	})
})

describe('searchSettings', () => {
	it('returns nothing for an empty query', () => {
		expect(searchSettings('   ')).toEqual([])
	})

	it('matches a field label case-insensitively and groups it under its section', () => {
		const groups = searchSettings('Haptic')

		expect(groups).toHaveLength(1)
		expect(groups[0].section.id).toBe('accessibility')
		expect(groups[0].fields.map((field) => field.id)).toContain('haptic-feedback')
	})

	it('matches a description, not just the label', () => {
		const groups = searchSettings('battery level')
		const ids = groups.flatMap((group) => group.fields.map((field) => field.id))

		expect(ids).toContain('battery-status')
	})

	it('matches keywords that are never rendered', () => {
		const groups = searchSettings('vibration')
		const ids = groups.flatMap((group) => group.fields.map((field) => field.id))

		expect(ids).toContain('haptic-feedback')
	})

	it('matches tokens in any order', () => {
		const ids = searchSettings('wallpaper auto').flatMap((group) =>
			group.fields.map((field) => field.id)
		)

		expect(ids).toContain('auto-wallpaper')
	})

	it('requires every token to match', () => {
		expect(searchSettings('wallpaper battery')).toEqual([])
	})

	it('finds a field through its section name', () => {
		const groups = searchSettings('appearance theme')

		expect(groups.map((group) => group.section.id)).toEqual(['appearance'])
		expect(groups[0].fields.map((field) => field.id)).toContain('theme')
	})

	it('keeps the section row when the section itself matches', () => {
		const groups = searchSettings('security')
		const security = groups.find((group) => group.section.id === 'security')

		expect(security?.sectionMatched).toBe(true)
	})

	it('honours the section list it is given', () => {
		const groups = searchSettings('debug', visibleSections)

		expect(groups.every((group) => group.section.id !== 'debug')).toBe(true)
	})

	it('returns no groups when nothing matches', () => {
		expect(searchSettings('zzzznotasetting')).toEqual([])
	})
})
