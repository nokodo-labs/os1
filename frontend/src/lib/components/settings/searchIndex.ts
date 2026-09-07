/**
 * search over the settings registry.
 *
 * the index is derived from `settingsSections`, which carries the same field
 * declarations the section pages render, so a result can never point at a field
 * that is not there. matching is a case-insensitive token match: every token in
 * the query must appear somewhere in the field's label, description, keywords,
 * or its section's label.
 */

import type { SettingsFieldDef } from './fields/types'
import { settingsSections, type SettingsSectionDef } from './sections'

export interface SettingsIndexEntry {
	section: SettingsSectionDef
	field: SettingsFieldDef
	haystack: string
}

export interface SettingsSearchGroup {
	section: SettingsSectionDef
	/** the section itself matched, so its own row belongs in the results. */
	sectionMatched: boolean
	fields: SettingsFieldDef[]
}

function joinTerms(parts: (string | undefined)[], keywords: readonly string[] = []): string {
	return [...parts, ...keywords]
		.filter((part): part is string => Boolean(part))
		.join(' ')
		.toLowerCase()
}

export function sectionHaystack(section: SettingsSectionDef): string {
	return joinTerms([section.label, section.description], section.keywords)
}

export function fieldHaystack(section: SettingsSectionDef, field: SettingsFieldDef): string {
	return joinTerms([field.label, field.description, section.label], field.keywords)
}

function tokenize(query: string): string[] {
	return query.toLowerCase().split(/\s+/).filter(Boolean)
}

function matchesAll(haystack: string, tokens: string[]): boolean {
	return tokens.every((token) => haystack.includes(token))
}

/** every indexed field, flattened. */
export function buildSettingsIndex(
	sections: readonly SettingsSectionDef[] = settingsSections
): SettingsIndexEntry[] {
	return sections.flatMap((section) =>
		section.fields.map((field) => ({
			section,
			field,
			haystack: fieldHaystack(section, field),
		}))
	)
}

/** matching sections and fields, grouped by section and kept in registry order. */
export function searchSettings(
	query: string,
	sections: readonly SettingsSectionDef[] = settingsSections
): SettingsSearchGroup[] {
	const tokens = tokenize(query)
	if (tokens.length === 0) return []
	return sections.flatMap((section) => {
		const sectionMatched = matchesAll(sectionHaystack(section), tokens)
		const fields = section.fields.filter((field) =>
			matchesAll(fieldHaystack(section, field), tokens)
		)
		if (!sectionMatched && fields.length === 0) return []
		return [{ section, sectionMatched, fields }]
	})
}
