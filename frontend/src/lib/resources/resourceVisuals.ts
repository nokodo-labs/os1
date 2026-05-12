import Calendar from '$lib/components/icons/Calendar.svelte'
import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
import CheckBox from '$lib/components/icons/CheckBox.svelte'
import Clip from '$lib/components/icons/Clip.svelte'
import Cog6 from '$lib/components/icons/Cog6.svelte'
import Document from '$lib/components/icons/Document.svelte'
import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
import UserGroup from '$lib/components/icons/UserGroup.svelte'
import Users from '$lib/components/icons/Users.svelte'
import { accentColors, type AccentColorKey } from '$lib/contexts/themeContext.svelte'
import type { AppId } from '$lib/stores/appNavigation.svelte'

export type AppVisualId = AppId | 'library'

export type ResourceVisualType =
	| 'thread'
	| 'note'
	| 'reminder_list'
	| 'project'
	| 'file'
	| 'calendar'
	| 'messages'
	| 'group'
	| 'settings'

export type ResourcePreviewTone = 'amber' | 'emerald' | 'rose' | 'sky' | 'yellow'

export type ResourceIconComponent = typeof Document

export interface ResourceVisual {
	type: ResourceVisualType
	label: string
	pluralLabel: string
	icon: ResourceIconComponent
	accent: AccentColorKey
	tone: ResourcePreviewTone
}

export interface AppVisual {
	id: AppVisualId
	title: string
	description: string
	icon: ResourceIconComponent
	accent: AccentColorKey
}

export const resourceVisuals = {
	thread: {
		type: 'thread',
		label: 'chat',
		pluralLabel: 'chats',
		icon: ChatBubbles,
		accent: 'green',
		tone: 'emerald',
	},
	note: {
		type: 'note',
		label: 'note',
		pluralLabel: 'notes',
		icon: Document,
		accent: 'notes',
		tone: 'amber',
	},
	reminder_list: {
		type: 'reminder_list',
		label: 'reminder list',
		pluralLabel: 'reminders',
		icon: CheckBox,
		accent: 'reminders',
		tone: 'rose',
	},
	project: {
		type: 'project',
		label: 'project',
		pluralLabel: 'projects',
		icon: FinderFolder,
		accent: 'yellow',
		tone: 'yellow',
	},
	file: {
		type: 'file',
		label: 'file',
		pluralLabel: 'files',
		icon: Clip,
		accent: 'blue',
		tone: 'sky',
	},
	calendar: {
		type: 'calendar',
		label: 'calendar',
		pluralLabel: 'calendars',
		icon: Calendar,
		accent: 'calendar',
		tone: 'emerald',
	},
	messages: {
		type: 'messages',
		label: 'message',
		pluralLabel: 'messages',
		icon: ChatBubbles,
		accent: 'green',
		tone: 'emerald',
	},
	group: {
		type: 'group',
		label: 'group',
		pluralLabel: 'groups',
		icon: UserGroup,
		accent: 'orange',
		tone: 'amber',
	},
	settings: {
		type: 'settings',
		label: 'setting',
		pluralLabel: 'settings',
		icon: Cog6,
		accent: 'gray',
		tone: 'sky',
	},
} satisfies Record<ResourceVisualType, ResourceVisual>

export const appVisuals = [
	{
		id: 'notes',
		title: 'notes',
		description: 'capture and organize thoughts',
		...pickAppVisual('note'),
	},
	{
		id: 'reminders',
		title: 'reminders',
		description: 'track tasks and alerts',
		...pickAppVisual('reminder_list'),
	},
	{
		id: 'calendar',
		title: 'calendar',
		description: 'plan your schedule',
		...pickAppVisual('calendar'),
	},
	{
		id: 'messages',
		title: 'messages',
		description: 'conversations and inbox',
		...pickAppVisual('messages'),
	},
	{
		id: 'projects',
		title: 'projects',
		description: 'group work and files',
		...pickAppVisual('project'),
	},
	{
		id: 'library',
		title: 'files',
		description: 'uploads and generated assets',
		...pickAppVisual('file'),
	},
	{
		id: 'social',
		title: 'social',
		description: 'groups and shared spaces',
		icon: Users,
		accent: 'orange',
	},
	{
		id: 'settings',
		title: 'settings',
		description: 'preferences and account',
		...pickAppVisual('settings'),
	},
] satisfies AppVisual[]

export const projectResourceTypes = [
	'thread',
	'note',
	'file',
	'reminder_list',
	'calendar',
] as const satisfies ResourceVisualType[]

export function resourceVisual(type: ResourceVisualType): ResourceVisual {
	return resourceVisuals[type]
}

export function resourceAccentColor(type: ResourceVisualType): string {
	return accentColors[resourceVisual(type).accent].primary
}

export function resourceAccentStyle(type: ResourceVisualType): string {
	const colors = accentColors[resourceVisual(type).accent]
	return [
		`--resource-accent: ${colors.primary}`,
		`--resource-accent-rgb: ${colors.rgb}`,
		`--accent-primary: ${colors.primary}`,
		`--accent-rgb: ${colors.rgb}`,
	].join('; ')
}

function pickAppVisual(type: ResourceVisualType): Pick<AppVisual, 'icon' | 'accent'> {
	const visual = resourceVisual(type)
	return { icon: visual.icon, accent: visual.accent }
}
