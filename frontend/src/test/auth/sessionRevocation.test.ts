/**
 * remote revocation must log this tab out, and the initiating page's defer
 * window must not outlive the logout it delayed.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
	logoutAndRedirect: vi.fn(() => Promise.resolve()),
	revokedHandlers: [] as Array<() => void>,
}))

vi.mock('$lib/api/streaming', () => ({
	eventStreamClient: {
		subscribeTypes: vi.fn(() => () => {}),
		onSessionRevoked: vi.fn((handler: () => void) => {
			mocks.revokedHandlers.push(handler)
			return () => {}
		}),
	},
}))

vi.mock('$lib/auth/logout', () => ({
	logoutAndRedirect: mocks.logoutAndRedirect,
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
}))

import {
	cancelRevocationLogoutDefer,
	deferRevocationLogout,
	startSessionRevocationWatch,
} from '$lib/auth/sessionRevocation'

startSessionRevocationWatch()

/** the socket kill channel firing (close code 4001 / 4002). */
function revoke(): void {
	for (const handler of mocks.revokedHandlers) handler()
}

describe('session revocation logout', () => {
	beforeEach(() => {
		vi.useFakeTimers()
		mocks.logoutAndRedirect.mockClear()
		cancelRevocationLogoutDefer()
	})

	afterEach(() => {
		vi.useRealTimers()
	})

	it('logs out at once when no defer window is open', () => {
		revoke()

		expect(mocks.logoutAndRedirect).toHaveBeenCalledTimes(1)
	})

	it('waits out the initiating page window before logging out itself', () => {
		deferRevocationLogout(2000)
		revoke()

		expect(mocks.logoutAndRedirect).not.toHaveBeenCalled()

		vi.advanceTimersByTime(2000)

		expect(mocks.logoutAndRedirect).toHaveBeenCalledTimes(1)
	})

	it('spends the defer window when the deferred logout runs', () => {
		deferRevocationLogout(1000)
		revoke()
		// a second credential change re-arms the window while the first is pending
		deferRevocationLogout(5000)

		vi.advanceTimersByTime(1000)
		expect(mocks.logoutAndRedirect).toHaveBeenCalledTimes(1)

		// the spent window must not delay the revocation that lands next
		revoke()

		expect(mocks.logoutAndRedirect).toHaveBeenCalledTimes(2)
	})

	it('logs out at once after a cancelled defer', () => {
		deferRevocationLogout(2000)
		cancelRevocationLogoutDefer()
		revoke()

		expect(mocks.logoutAndRedirect).toHaveBeenCalledTimes(1)
	})
})
