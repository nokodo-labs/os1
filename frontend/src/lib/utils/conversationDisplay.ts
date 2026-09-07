import type { components } from '$lib/api/types'
import { threadKind } from '$lib/stores/chat.svelte'
import { userDisplayName } from '$lib/utils/resourceAuthors'

export type Thread = components['schemas']['Thread']
/** discriminated union member (user | agent | group), robust to schema naming. */
export type ThreadParticipant = NonNullable<Thread['participants']>[number]

export interface ConversationFace {
	id: string
	label: string
	avatarUrl: string | null
	isAgent: boolean
}

export interface ConversationDisplay {
	title: string
	subtitle: string | null
	faces: ConversationFace[]
	humanCount: number
	isGroup: boolean
}

function participantLabel(p: ThreadParticipant): string {
	if (p.kind === 'user') {
		return (
			userDisplayName({
				display_name: p.user.display_name,
				username: p.user.username,
				id: p.user.id,
			}) ?? 'someone'
		)
	}
	if (p.kind === 'agent') return p.agent.name
	return p.group.name
}

function participantId(p: ThreadParticipant): string {
	if (p.kind === 'user') return p.user.id
	if (p.kind === 'agent') return p.agent.id
	return p.group.id
}

/** one participant as a face, for rosters that list everybody rather than a summary. */
export function participantFace(p: ThreadParticipant): ConversationFace {
	const avatarUrl =
		p.kind === 'user'
			? (p.user.avatar_url ?? null)
			: p.kind === 'agent'
				? (p.agent.profile_image_url ?? null)
				: null
	return {
		id: participantId(p),
		label: participantLabel(p),
		avatarUrl,
		isAgent: p.kind === 'agent',
	}
}

/**
 * derive how a people conversation should be presented to the current user:
 * a DM shows the other person, a group shows its title plus member faces.
 */
export function conversationDisplay(
	thread: Thread,
	currentUserId: string | null
): ConversationDisplay {
	const participants = thread.participants ?? []
	const humans = participants.filter((p) => p.kind === 'user')
	const nonHumans = participants.filter((p) => p.kind !== 'user')
	const others = humans.filter((p) => participantId(p) !== currentUserId)
	const isGroup = threadKind(thread) === 'group'

	if (!isGroup && others.length === 1) {
		const other = others[0]
		const username = other.kind === 'user' ? other.user.username : null
		return {
			title: thread.title?.trim() || participantLabel(other),
			subtitle: username ? `@${username}` : null,
			faces: [participantFace(other)],
			humanCount: humans.length,
			isGroup: false,
		}
	}

	const faces = [...others, ...nonHumans].map(participantFace)
	const names = others.map(participantLabel)
	const subtitle =
		names.length > 0
			? `${names.slice(0, 3).join(', ')}${names.length > 3 ? ` +${names.length - 3}` : ''}`
			: null
	return {
		title: thread.title?.trim() || names.join(', ') || 'group',
		subtitle,
		faces: faces.slice(0, 4),
		humanCount: humans.length,
		isGroup: true,
	}
}
