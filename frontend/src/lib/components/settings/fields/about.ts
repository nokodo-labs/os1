import type { SettingsFieldGroup } from './types'

export const aboutFields = {
	links: {
		id: 'links',
		label: 'links',
		keywords: ['website', 'github', 'changelog', 'releases'],
	},
	community: {
		id: 'community',
		label: 'community',
		keywords: ['stars', 'license badge'],
	},
	legal: {
		id: 'legal',
		label: 'legal',
		keywords: ['license', 'copyright', 'open source', 'dependencies'],
	},
} satisfies SettingsFieldGroup
