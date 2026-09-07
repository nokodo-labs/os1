/**
 * the composer's outgoing typing signal.
 *
 * a receiver forgets a composer 8s after their last signal (`TYPING_TTL_MS` in
 * the chat store), so somebody who is still composing has to keep signalling:
 * every draft change re-signals, and a heartbeat carries the pauses between
 * keystrokes. the signal stops when the draft is cleared, sent, or blurred -
 * text sitting in an unfocused box is not somebody typing.
 */

/** how often a live composer re-signals, well inside the receiver's 8s TTL. */
export const TYPING_HEARTBEAT_MS = 3000

export interface TypingSignal {
	/**
	 * the composer changed. `draft` is the text as it now reads, so a deletion
	 * is activity exactly like a keystroke; `focused` is whether the composer
	 * still holds the user's cursor.
	 */
	update(draft: string, focused: boolean): void
	/** stop signalling now (send, teardown, losing write access). */
	stop(): void
}

export function createTypingSignal(
	send: (typing: boolean) => void,
	heartbeatMs: number = TYPING_HEARTBEAT_MS
): TypingSignal {
	let heartbeat: ReturnType<typeof setInterval> | null = null
	let lastSentAt = 0

	function emit(): void {
		lastSentAt = Date.now()
		send(true)
	}

	function stop(): void {
		if (heartbeat === null) return
		clearInterval(heartbeat)
		heartbeat = null
		send(false)
	}

	function update(draft: string, focused: boolean): void {
		if (!focused || draft.trim().length === 0) {
			stop()
			return
		}
		if (heartbeat === null) {
			emit()
			heartbeat = setInterval(emit, heartbeatMs)
			return
		}
		// the running heartbeat already holds the cadence; a change only sends
		// again once it has lapsed, which a backgrounded tab's clamped timers do.
		if (Date.now() - lastSentAt >= heartbeatMs) emit()
	}

	return { update, stop }
}
