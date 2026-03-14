/**
 * friends store - manages friends list, incoming/outgoing requests
 * with WS-driven real-time updates.
 *
 * cache strategy:
 * - short TTL (5 min) with automatic refresh on API calls
 * - websocket events trigger refetch (WS is source of truth)
 * - stale data is still displayed while fetching
 */

import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'

export type FriendResponse = components['schemas']['FriendResponse']
export type FriendshipDetail = components['schemas']['FriendshipDetail']
export type FriendshipResponse = components['schemas']['FriendshipResponse']

type RelationshipKind = 'accepted' | 'pending_outgoing' | 'pending_incoming'

export interface Relationship {
	kind: RelationshipKind
	friendshipId: string
}

const CACHE_TTL_MS = 5 * 60 * 1000

const FRIEND_EVENT_TYPES = [
	'friend.request_sent',
	'friend.request_accepted',
	'friend.request_declined',
	'friend.removed',
]

// helpers

function getUserId(): string | null {
	const token = getAccessToken()
	if (!token) return null
	return getJwtUserId(token)
}

// friends store

class FriendsStore {
	list = $state<FriendResponse[]>([])
	incoming = $state<FriendshipDetail[]>([])
	outgoing = $state<FriendshipDetail[]>([])
	isReady = $state(false)

	#fetchedAt = 0
	#inFlight: Promise<void> | null = null
	#unsubscribe: (() => void) | null = null

	// derived

	readonly friendCount = $derived(this.list.length)
	readonly incomingCount = $derived(this.incoming.length)
	readonly outgoingCount = $derived(this.outgoing.length)
	readonly hasContent = $derived(
		this.list.length > 0 || this.incoming.length > 0 || this.outgoing.length > 0
	)

	// event stream integration

	init(): void {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleStreamEvent)
		}
		void this.load()
	}

	cleanup(): void {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	clear(): void {
		this.list = []
		this.incoming = []
		this.outgoing = []
		this.isReady = false
		this.#fetchedAt = 0
	}

	#handleStreamEvent = (message: StreamMessage): void => {
		if (FRIEND_EVENT_TYPES.includes(message.type)) {
			void this.load({ force: true })
		}
	}

	#isFresh(): boolean {
		return Date.now() - this.#fetchedAt < CACHE_TTL_MS
	}

	// reads

	/**
	 * look up the relationship between the current user and another user.
	 * used by AddFriendsModal to determine which button to show per search result.
	 */
	getRelationship(userId: string): Relationship | null {
		const friend = this.list.find((f) => f.id === userId)
		if (friend) return { kind: 'accepted', friendshipId: friend.friendship_id }

		const out = this.outgoing.find((r) => r.addressee_id === userId)
		if (out) return { kind: 'pending_outgoing', friendshipId: out.id }

		const inc = this.incoming.find((r) => r.requester_id === userId)
		if (inc) return { kind: 'pending_incoming', friendshipId: inc.id }

		return null
	}

	// load

	async load(options?: { force?: boolean }): Promise<void> {
		const force = options?.force ?? false
		if (!force && this.#isFresh()) return
		if (this.#inFlight) return void (await this.#inFlight)

		const userId = getUserId()
		if (!userId) return

		this.#inFlight = (async () => {
			try {
				const [friendsRes, incomingRes, outgoingRes] = await Promise.all([
					api.GET('/v1/users/{user_id}/friends', {
						params: { path: { user_id: userId } },
					}),
					api.GET('/v1/users/{user_id}/friends/requests/incoming', {
						params: { path: { user_id: userId } },
					}),
					api.GET('/v1/users/{user_id}/friends/requests/outgoing', {
						params: { path: { user_id: userId } },
					}),
				])
				this.list = friendsRes.data ?? []
				this.incoming = incomingRes.data ?? []
				this.outgoing = outgoingRes.data ?? []
				this.#fetchedAt = Date.now()
			} finally {
				this.isReady = true
			}
		})()

		try {
			await this.#inFlight
		} finally {
			this.#inFlight = null
		}
	}

	// mutations - return data for caller; WS delivers truth

	async sendRequest(addresseeId: string): Promise<FriendshipResponse | null> {
		const userId = getUserId()
		if (!userId) return null

		const { data, error } = await api.POST('/v1/users/{user_id}/friends/requests', {
			params: { path: { user_id: userId } },
			body: { addressee_id: addresseeId },
		})
		if (error || !data) return null
		return data
	}

	async acceptRequest(friendshipId: string): Promise<FriendshipResponse | null> {
		const userId = getUserId()
		if (!userId) return null

		const { data, error } = await api.POST(
			'/v1/users/{user_id}/friends/requests/{friendship_id}/accept',
			{
				params: { path: { user_id: userId, friendship_id: friendshipId } },
			}
		)
		if (error || !data) return null
		return data
	}

	async declineRequest(friendshipId: string): Promise<FriendshipResponse | null> {
		const userId = getUserId()
		if (!userId) return null

		const { data, error } = await api.POST(
			'/v1/users/{user_id}/friends/requests/{friendship_id}/decline',
			{
				params: { path: { user_id: userId, friendship_id: friendshipId } },
			}
		)
		if (error || !data) return null
		return data
	}

	async removeFriend(friendUserId: string): Promise<boolean> {
		const userId = getUserId()
		if (!userId) return false

		const { error } = await api.DELETE('/v1/users/{user_id}/friends/{friend_user_id}', {
			params: { path: { user_id: userId, friend_user_id: friendUserId } },
		})
		if (error) return false
		return true
	}

	// lifecycle

	invalidate(): void {
		this.#fetchedAt = 0
	}
}

// singleton export

export const friends = new FriendsStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			friends.init()
		} else {
			friends.cleanup()
			friends.clear()
		}
	})

	if (getAccessToken()) {
		friends.init()
	}
}
