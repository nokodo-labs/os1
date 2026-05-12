import type { components } from '$lib/api/types'

export type UserSummary = components['schemas']['UserSummary']
export const RESOURCE_META_DIVIDER = ' · '

type ResourceMetaValue = string | null | undefined | false

export interface UserIdentity {
	id?: string | null
	display_name?: string | null
	username?: string | null
	avatar_url?: string | null
}

export interface ResourceAuthor {
	id: string
	label: string
	avatarUrl: string | null
}

function cleanUserText(value: string | null | undefined): string | null {
	const text = value?.trim()
	return text ? text : null
}

export function userDisplayName(user: UserIdentity | null | undefined): string | null {
	if (!user) return null
	return (
		cleanUserText(user.display_name) ?? cleanUserText(user.username) ?? cleanUserText(user.id)
	)
}

export function userHandleOrId(user: UserIdentity | null | undefined): string | null {
	const username = cleanUserText(user?.username)
	if (username) return `@${username}`
	return cleanUserText(user?.id)
}

export function toResourceAuthor(user: UserSummary | null | undefined): ResourceAuthor | null {
	if (!user?.id) return null
	const label = userDisplayName(user)
	if (!label) return null
	return {
		id: user.id,
		label,
		avatarUrl: user.avatar_url ?? null,
	}
}

export function authorLabel(author: ResourceAuthor | null | undefined): string | null {
	return author?.label ?? null
}

export function byAuthor(label: string | null | undefined): string | null {
	return label ? `by ${label}` : null
}

export function metadataParts(...values: ResourceMetaValue[]): string[] {
	return values
		.map((value) => (typeof value === 'string' ? value.trim() : ''))
		.filter((value) => value.length > 0)
}

export function metadataLine(...values: ResourceMetaValue[]): string {
	return metadataParts(...values).join(RESOURCE_META_DIVIDER)
}
