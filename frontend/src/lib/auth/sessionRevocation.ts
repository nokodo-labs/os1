/**
 * instant hard-logout when this user's sessions are revoked remotely
 * (admin revoke, password change from another session).
 *
 * two triggers, both server-authoritative:
 * - `user.sessions_revoked` / `user.password_changed` stream events
 * - websocket close codes 4001 / 4002 (socket kill channel)
 */

import { eventStreamClient } from '$lib/api/streaming'

import { logoutAndRedirect } from './logout'
import { getAccessToken } from './session.svelte'

const REVOCATION_EVENT_TYPES = ['user.sessions_revoked', 'user.password_changed'] as const

let started = false
let deferUntil = 0

/**
 * initiating tab of a credential change: delay a revocation-triggered logout
 * so the page can show its own confirmation and log out itself. call right
 * before the credential-change request.
 */
export function deferRevocationLogout(ms: number): void {
	deferUntil = Date.now() + ms
}

/** cancel a pending defer when the credential change did not go through. */
export function cancelRevocationLogoutDefer(): void {
	deferUntil = 0
}

function hardLogout(): void {
	if (!getAccessToken()) return
	const remaining = deferUntil - Date.now()
	if (remaining > 0) {
		// safety net behind the initiating page's own logout
		setTimeout(() => {
			// the window has been spent; a later revocation must not reuse it
			deferUntil = 0
			if (getAccessToken()) void logoutAndRedirect()
		}, remaining)
		return
	}
	void logoutAndRedirect()
}

/** start watching for remote session revocation. re-entrant. */
export function startSessionRevocationWatch(): void {
	if (started) return
	started = true
	eventStreamClient.subscribeTypes(REVOCATION_EVENT_TYPES, hardLogout)
	eventStreamClient.onSessionRevoked(hardLogout)
}
