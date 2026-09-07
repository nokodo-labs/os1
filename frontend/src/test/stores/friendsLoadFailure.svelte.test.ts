/**
 * a failed friends fetch must never present as "no friends".
 *
 * `load()` assigned `data ?? []` and flipped `hasLoaded` in a `finally`, so one
 * network blip wiped the list AND marked it loaded - the page then rendered its
 * empty state. the store now keeps the prior lists, leaves `hasLoaded` alone,
 * and surfaces `error` for the view to branch on.
 */

import type { components } from '$lib/api/types'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type FriendResponse = components['schemas']['FriendResponse']

let failing = false

vi.mock('$app/environment', () => ({ browser: false }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn((path: string) => {
			if (failing) {
				return Promise.resolve({ data: undefined, error: { detail: 'offline' } })
			}
			if (path === '/v1/users/{user_id}/friends') {
				return Promise.resolve({ data: [makeFriend('user_friend')], error: undefined })
			}
			return Promise.resolve({ data: [], error: undefined })
		}),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/auth/jwt', () => ({
	getJwtUserId: vi.fn(() => 'user_me'),
}))

vi.mock('$lib/stores/storeEvents', () => ({
	STORE_EVENT_TYPES: { friends: ['friendship.created'] },
	subscribeToStoreEvents: vi.fn(() => () => {}),
}))

const { friends } = await import('$lib/stores/friends.svelte')

function makeFriend(id: string): FriendResponse {
	return { id, friendship_id: `friendship_${id}`, display_name: id }
}

describe('friends.load() failure handling', () => {
	beforeEach(() => {
		failing = false
		friends.clear()
	})

	it('keeps the loaded list and reports the error when a refresh fails', async () => {
		await friends.load()
		expect(friends.list).toHaveLength(1)
		expect(friends.hasLoaded).toBe(true)

		failing = true
		await friends.load({ force: true })

		expect(friends.list).toHaveLength(1)
		expect(friends.hasLoaded).toBe(true)
		expect(friends.error).toBe('failed to load friends')
	})

	it('does not mark itself loaded when the first fetch fails', async () => {
		failing = true
		await friends.load()

		expect(friends.hasLoaded).toBe(false)
		expect(friends.hasContent).toBe(false)
		expect(friends.error).toBe('failed to load friends')
	})

	it('recovers on the next successful load', async () => {
		failing = true
		await friends.load()
		expect(friends.error).toBe('failed to load friends')

		failing = false
		await friends.load({ force: true })

		expect(friends.error).toBeNull()
		expect(friends.hasLoaded).toBe(true)
		expect(friends.list).toHaveLength(1)
	})

	it('clears the error signal on logout', async () => {
		failing = true
		await friends.load()
		expect(friends.error).toBe('failed to load friends')

		friends.clear()

		expect(friends.error).toBeNull()
		expect(friends.hasLoaded).toBe(false)
	})
})
