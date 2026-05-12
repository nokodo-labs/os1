import type { components } from '$lib/api/types'
import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'
import type { AccessLevel } from '$lib/stores/resourceAccess.svelte'

export type ShareTargetId = 'whatsapp' | 'telegram' | 'x'
export type ExportFormat = 'md' | 'txt' | 'json'
export type UserResult = components['schemas']['UserSearchResult']
export type UserPick = Pick<UserResult, 'id' | 'username' | 'display_name' | 'email' | 'avatar_url'>

export interface RuleEntry {
	localId: string
	id: string | null
	subjectLabel: string
	subjectUserId: string | null
	subjectGroupId: string | null
	subjectRoleId: string | null
	level: AccessLevel
	orderIndex: number
}

export interface ShareTarget {
	id: ShareTargetId
	label: string
	href: string
	origin: string
}

export const SHARE_LEVELS: { value: AccessLevel; label: string }[] = [
	{ value: 'reader', label: 'can view' },
	{ value: 'editor', label: 'can edit' },
	{ value: 'admin', label: 'can manage' },
]

export function queryString(values: Record<string, string>): string {
	return new URLSearchParams(values).toString()
}

export function resourceLabel(
	resourceType: ResourceAccessPayload['resourceType'] | undefined
): string {
	switch (resourceType) {
		case 'thread':
			return 'chat'
		case 'file':
			return 'file'
		case 'project':
			return 'project'
		case 'group':
			return 'group'
		case 'agent':
			return 'agent'
		case 'note':
			return 'note'
		case 'reminder_list':
			return 'list'
		case 'calendar':
			return 'calendar'
		default:
			return 'item'
	}
}

export function resourcePath(
	resourceType: ResourceAccessPayload['resourceType'],
	resourceId: string
): string {
	switch (resourceType) {
		case 'thread':
			return `/c/${resourceId}`
		case 'note':
			return `/notes/${resourceId}`
		case 'project':
			return `/projects/${resourceId}`
		case 'group':
			return `/social/groups/${resourceId}`
		case 'reminder_list':
			return `/reminders/lists/${resourceId}`
		case 'calendar':
			return '/calendar'
		case 'file':
			return '/library'
		case 'agent':
			return '/settings/ai'
	}
}

export function levelLabel(level: AccessLevel): string {
	return SHARE_LEVELS.find((option) => option.value === level)?.label ?? 'can view'
}

export function shareIconFailureKey(targetId: ShareTargetId, url: string): string {
	return `${targetId}:${url}`
}
