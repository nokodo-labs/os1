/**
 * searchable metadata for one settings field.
 *
 * a field is declared once here and rendered from the same object by its
 * section page (through `SettingsField`), so the search index can never drift
 * from what a section actually shows. declarations are static: the index covers
 * every section without any of them having to mount.
 */
export interface SettingsFieldDef {
	/** unique within its section. used by `?field=` and the reveal anchor. */
	id: string
	label: string
	description?: string
	/** extra search terms that are never rendered, for controls without a description. */
	keywords?: readonly string[]
}

/** a section's field declarations, keyed for direct access from its page. */
export type SettingsFieldGroup = Record<string, SettingsFieldDef>
