import type { SettingsFieldGroup } from './types'

export const debugFields = {
	debugApps: {
		id: 'debug-apps',
		label: 'debug apps',
		description: 'show placeholder apps on the home screen for testing.',
		keywords: ['enable debug apps'],
	},
	appearance: {
		id: 'appearance-overrides',
		label: 'appearance',
		description: 'admin-only debug overrides.',
		keywords: ['disable background'],
	},
	debugPages: {
		id: 'debug-pages',
		label: 'debug pages',
		description: 'visual test pages and playgrounds.',
	},
	deviceInsights: {
		id: 'device-insights',
		label: 'device insights',
		description: 'computed device metrics and gpu tier signal breakdown.',
		keywords: ['gpu', 'renderer', 'webgl'],
	},
	appsGrid: {
		id: 'apps-grid',
		label: 'apps grid',
		description: 'visual tweaks for the home apps grid.',
		keywords: ['icon shape'],
	},
	markdownStreaming: {
		id: 'markdown-streaming',
		label: 'markdown streaming',
		description: 'tune the streamdown animation used while tokens arrive.',
		keywords: ['tokenize', 'duration'],
	},
	chatSendAnimation: {
		id: 'chat-send-animation',
		label: 'chat send animation',
		description:
			'how an outgoing message animates from the input into a bubble. morph uses the view transitions api; flyup is a css fallback.',
	},
} satisfies SettingsFieldGroup
