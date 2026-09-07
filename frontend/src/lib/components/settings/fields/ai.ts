import type { SettingsFieldGroup } from './types'

export const aiFields = {
	useAccountBio: {
		id: 'use-account-bio',
		label: 'use account bio',
		description:
			'use your account bio as context for AI conversations instead of a separate AI bio.',
	},
	aiBio: {
		id: 'ai-bio',
		label: 'AI bio',
		description:
			'tell the AI about yourself - your interests, work, and preferences. this helps personalize responses.',
	},
	memories: {
		id: 'memories',
		label: 'memories',
		description:
			'the AI remembers things you tell it across conversations to provide more relevant responses.',
		keywords: ['manage memories'],
	},
	enableMemories: {
		id: 'enable-memories',
		label: 'enable memories',
	},
	chatRecall: {
		id: 'chat-recall',
		label: 'chat recall',
		description: 'allow the AI to reference previous conversations for context.',
	},
	customInstructions: {
		id: 'custom-instructions',
		label: 'custom instructions',
		description:
			'provide specific instructions the AI should always follow. these apply to every conversation.',
	},
	personality: {
		id: 'personality',
		label: 'personality',
		description:
			"describe how you'd like the AI to communicate - its tone, style, and character.",
	},
} satisfies SettingsFieldGroup
