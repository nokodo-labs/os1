import type { SettingsFieldGroup } from './types'

export const notificationsFields = {
	push: {
		id: 'push-notifications',
		label: 'push notifications',
		description: 'extra delivery when the app is closed or in the background.',
	},
	email: {
		id: 'email-notifications',
		label: 'email notifications',
		description: 'email digests and important alerts.',
	},
} satisfies SettingsFieldGroup
