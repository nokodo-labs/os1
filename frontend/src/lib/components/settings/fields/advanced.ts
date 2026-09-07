import { appVisuals, type AppVisualId } from '$lib/resources/resourceVisuals'
import type { SettingsFieldDef, SettingsFieldGroup } from './types'

export const advancedFields = {
	experimentalFeatures: {
		id: 'experimental-features',
		label: 'experimental features',
		description: 'these features are experimental and may cause performance issues or bugs.',
	},
	svgLiquidGlass: {
		id: 'svg-liquid-glass',
		label: 'enable svg liquid glass globally',
		description:
			'use svg-based liquid glass effects everywhere when your browser supports it. this can be very heavy on performance.',
	},
	svgLiquidGlassIsland: {
		id: 'svg-liquid-glass-island',
		label: 'enable svg liquid glass for island',
		description: 'use svg-based liquid glass effects specifically for the island component.',
	},
	svgLiquidMetal: {
		id: 'svg-liquid-metal',
		label: 'enable svg liquid metal',
		description: 'use svg-based liquid metal edge refractions when supported by your browser.',
	},
	homepageSuggestions: {
		id: 'homepage-suggestions',
		label: 'homepage suggestions',
		description: 'choose which apps appear when you search on the home screen.',
	},
	appCache: {
		id: 'app-cache',
		label: 'app cache',
		description: 'clears all caches and restarts the app.',
		keywords: ['clear caches and restart app', 'reload'],
	},
	dataExport: {
		id: 'data-export',
		label: 'data export',
		description: 'download your data in portable formats.',
	},
	downloadAllChats: {
		id: 'download-all-chats',
		label: 'download all chats',
		description: 'export all your conversations as JSON',
	},
	downloadAllMemories: {
		id: 'download-all-memories',
		label: 'download all memories',
		description: 'export all AI memories as JSON',
	},
	downloadAllData: {
		id: 'download-all-data',
		label: 'download all your data',
		description: 'export everything: chats, memories, preferences, and files',
	},
	chatManagement: {
		id: 'chat-management',
		label: 'chat management',
		description: 'organize or clean up your conversations.',
	},
	archiveAllChats: {
		id: 'archive-all-chats',
		label: 'archive all chats',
		description: 'move all conversations to the archive',
	},
	deleteAllChats: {
		id: 'delete-all-chats',
		label: 'delete all chats',
		description: 'permanently remove all conversations',
	},
	dangerZone: {
		id: 'danger-zone',
		label: 'danger zone',
		description: 'irreversible actions. proceed with extreme caution.',
		keywords: ['delete account'],
	},
} satisfies SettingsFieldGroup

/** homepage suggestion keys, mirroring the homepage preference group. */
export type HomepageSuggestionKey =
	| 'chats'
	| 'reminders'
	| 'notes'
	| 'projects'
	| 'calendar'
	| 'library'
	| 'friends'

export interface HomepageSuggestionApp {
	key: HomepageSuggestionKey
	appId: AppVisualId
	field: SettingsFieldDef
}

function suggestion(appId: AppVisualId, key: HomepageSuggestionKey): HomepageSuggestionApp {
	const visual = appVisuals.find((app) => app.id === appId)
	return {
		key,
		appId,
		field: {
			id: `homepage-${key}`,
			label: visual?.title ?? appId,
			description: visual?.description,
		},
	}
}

/** one toggle per app offered on the home screen, labelled from the app's own visual. */
export const homepageSuggestionApps: HomepageSuggestionApp[] = [
	suggestion('messages', 'chats'),
	suggestion('reminders', 'reminders'),
	suggestion('notes', 'notes'),
	suggestion('projects', 'projects'),
	suggestion('calendar', 'calendar'),
	suggestion('library', 'library'),
	suggestion('social', 'friends'),
]
