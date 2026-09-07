import AppNotification from '$lib/components/icons/AppNotification.svelte'
import CommandLine from '$lib/components/icons/CommandLine.svelte'
import Eye from '$lib/components/icons/Eye.svelte'
import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
import Lock from '$lib/components/icons/Lock.svelte'
import ShieldCheck from '$lib/components/icons/ShieldCheck.svelte'
import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
import Sparkles from '$lib/components/icons/Sparkles.svelte'
import Wrench from '$lib/components/icons/Wrench.svelte'
import type { Component } from 'svelte'
import { aboutFields } from './fields/about'
import { accessibilityFields } from './fields/accessibility'
import { advancedFields, homepageSuggestionApps } from './fields/advanced'
import { aiFields } from './fields/ai'
import { appearanceFields } from './fields/appearance'
import { debugFields } from './fields/debug'
import { integrationsFields, pendingIntegrationFields } from './fields/integrations'
import { notificationsFields } from './fields/notifications'
import { privacyFields, privacyVisibilityFields } from './fields/privacy'
import { securityFields } from './fields/security'
import type { SettingsFieldDef } from './fields/types'

export type SettingsSectionId =
	| 'appearance'
	| 'notifications'
	| 'privacy'
	| 'accessibility'
	| 'ai'
	| 'security'
	| 'integrations'
	| 'advanced'
	| 'about'
	| 'debug'

export type SettingsSectionIcon = Component<{ class?: string; variant?: 'outline' | 'solid' }>

export interface SettingsSectionDef {
	id: SettingsSectionId
	label: string
	icon: SettingsSectionIcon
	description: string
	/** every field the section renders, in render order. */
	fields: SettingsFieldDef[]
	/** extra search terms for things the section shows without a field of their own. */
	keywords?: readonly string[]
	/** superuser-only sections are hidden until the sidebar opts them in. */
	adminOnly?: boolean
}

/**
 * the settings registry: what the sidebar lists and what the search index covers.
 *
 * fields come from each section's static declaration module, so the index is
 * complete without any section page having to render first.
 */
export const settingsSections: SettingsSectionDef[] = [
	{
		id: 'appearance',
		label: 'appearance',
		icon: Eye,
		description: 'theme, colors, and visual preferences',
		fields: Object.values(appearanceFields),
	},
	{
		id: 'notifications',
		label: 'notifications',
		icon: AppNotification,
		description: 'alerts, sounds, and reminders',
		fields: Object.values(notificationsFields),
	},
	{
		id: 'privacy',
		label: 'privacy',
		icon: Lock,
		description: 'data collection and sharing settings',
		fields: [
			...Object.values(privacyFields),
			...privacyVisibilityFields.map((entry) => entry.field),
		],
	},
	{
		id: 'accessibility',
		label: 'accessibility',
		icon: SoundHigh,
		description: 'haptic feedback and assistive features',
		fields: Object.values(accessibilityFields),
	},
	{
		id: 'ai',
		label: 'AI',
		icon: Sparkles,
		description: 'model preferences and behavior',
		fields: Object.values(aiFields),
	},
	{
		id: 'security',
		label: 'security',
		icon: ShieldCheck,
		description: 'passwords, email, and authentication',
		fields: Object.values(securityFields),
	},
	{
		id: 'integrations',
		label: 'integrations',
		icon: GlobeAlt,
		description: 'imports and connected apps',
		fields: [
			...Object.values(integrationsFields),
			...pendingIntegrationFields.map((entry) => entry.field),
		],
	},
	{
		id: 'advanced',
		label: 'advanced',
		icon: Wrench,
		description: 'data management and experiments',
		fields: [
			...Object.values(advancedFields),
			...homepageSuggestionApps.map((app) => app.field),
		],
	},
	{
		id: 'about',
		label: 'about',
		icon: InfoCircle,
		description: 'app info, credits, and links',
		keywords: ['version', 'release'],
		fields: Object.values(aboutFields),
	},
	{
		id: 'debug',
		label: 'debug',
		icon: CommandLine,
		description: 'debug-only UI toggles and diagnostics',
		adminOnly: true,
		fields: Object.values(debugFields),
	},
]
