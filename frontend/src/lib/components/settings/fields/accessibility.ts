import type { SettingsFieldGroup } from './types'

export const accessibilityFields = {
	hapticFeedback: {
		id: 'haptic-feedback',
		label: 'haptic feedback',
		description: 'enable haptic feedback on supported devices',
		keywords: ['vibration'],
	},
} satisfies SettingsFieldGroup
