import type { components } from '$lib/api/types'
import type { SettingsFieldDef, SettingsFieldGroup } from './types'

type PrivacyKey = keyof components['schemas']['UserPrivacy']

export const privacyFields = {
	profileVisibility: {
		id: 'profile-visibility',
		label: 'profile visibility',
		description: 'choose who can see each part of your profile.',
	},
	emailSearch: {
		id: 'email-search',
		label: 'email search',
		description: 'allow people to find you by your email address',
	},
	aiPersonalization: {
		id: 'ai-personalization',
		label: 'AI personalization',
		description:
			'control what information is shared with the AI to personalise your experience.',
	},
	deviceInformation: {
		id: 'device-information',
		label: 'device information',
		description:
			'share timezone, device type, and browser to help the AI personalise responses',
	},
	preciseLocation: {
		id: 'precise-location',
		label: 'precise location',
		description: 'share your location with the AI for location-aware responses',
	},
	batteryStatus: {
		id: 'battery-status',
		label: 'battery status',
		description: 'share charging state and battery level for context-aware responses',
	},
	dataCollection: {
		id: 'data-collection',
		label: 'data collection',
		description: "control what data is collected and how it's used.",
	},
	analytics: {
		id: 'analytics',
		label: 'analytics',
		keywords: ['usage data'],
	},
	crashReports: {
		id: 'crash-reports',
		label: 'crash reports',
		keywords: ['diagnostics'],
	},
} satisfies SettingsFieldGroup

/** the per-attribute visibility rows, paired with the user field each one controls. */
export const privacyVisibilityFields: { key: PrivacyKey; field: SettingsFieldDef }[] = [
	{
		key: 'online_status',
		field: {
			id: 'online-status',
			label: 'online status',
			description: 'who can see your online/activity status',
		},
	},
	{
		key: 'profile_picture',
		field: {
			id: 'profile-picture',
			label: 'profile picture',
			description: 'who can see your profile picture',
		},
	},
	{
		key: 'real_name',
		field: {
			id: 'real-name',
			label: 'real name',
			description: 'who can see your display name',
		},
	},
	{
		key: 'bio',
		field: { id: 'bio', label: 'bio', description: 'who can see your bio' },
	},
	{
		key: 'email',
		field: {
			id: 'email-address',
			label: 'email address',
			description: 'who can see your email address',
		},
	},
	{
		key: 'gender',
		field: { id: 'gender', label: 'gender', description: 'who can see your gender' },
	},
	{
		key: 'birth_date',
		field: {
			id: 'birth-date',
			label: 'age / birth date',
			description: 'who can see your age or birth date',
		},
	},
	{
		key: 'allow_dms',
		field: {
			id: 'direct-messages',
			label: 'direct messages',
			description: 'who can send you direct messages',
		},
	},
	{
		key: 'allow_friend_requests',
		field: {
			id: 'friend-requests',
			label: 'friend requests',
			description: 'who can send you friend requests',
		},
	},
]
