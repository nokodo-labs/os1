import type { SettingsFieldGroup } from './types'

export const securityFields = {
	session: {
		id: 'session',
		label: 'session',
		description:
			'your current session is encrypted and refreshed automatically.',
		keywords: ['log out all sessions', 'revoke'],
	},
	changePassword: {
		id: 'change-password',
		label: 'change password',
		description: "update your account password. you'll need to enter your current password.",
	},
	externalAuthentication: {
		id: 'external-authentication',
		label: 'external authentication',
		description:
			'connect your account to an external identity provider via OpenID Connect (OIDC) for single sign-on.',
		keywords: ['sso'],
	},
	emailAddress: {
		id: 'email-address',
		label: 'email address',
		description: 'your email address for notifications and account recovery.',
	},
} satisfies SettingsFieldGroup
