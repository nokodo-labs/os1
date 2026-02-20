/**
 * real-time event subscriptions — single unified listener that dispatches
 * tool, message, typing, and run events by prefix for performance.
 */

import { isOwnEvent } from '$lib/api/sessionId'
import {
	eventStreamClient,
	resumeRunStream,
	type StreamEvent,
	type StreamMessage,
} from '$lib/api/streaming'
import { parseToolEvent } from '$lib/tools'
import { SvelteDate, SvelteMap } from 'svelte/reactivity'
import { getMessageCreatedAt, type ApiMessage } from './helpers'
import { consumeStream } from './streamProcessor'
import type { ChatContext } from './types'

/** lightweight pointer for a run signal received over WS */
interface RunSignal {
	thread_id: string
	run_id: string
	agent_id: string
}

/**
 * subscribe to all real-time chat events for a thread through a single
 * event stream listener. dispatches by event type prefix for performance.
 * returns an unsubscribe function that cleans up all internal state.
 */
export function subscribeToChatEvents(threadId: string, ctx: ChatContext): () => void {
	// typing auto-expire timers
	const typingTimers = new SvelteMap<string, ReturnType<typeof setTimeout>>()
	// abort controllers for resume streams, keyed by run_id
	const resumeAborts = new SvelteMap<string, AbortController>()

	ctx.typingUsers.clear()
	ctx.activeAgentRuns.clear()

	// ── tool events ──────────────────────────────────────────────────────

	function handleToolEvent(ev: StreamEvent): void {
		if (ev.thread_id !== threadId) return
		const toolEv = parseToolEvent({
			id: ev.id,
			type: ev.type,
			data: (ev.data ?? {}) as Record<string, unknown>,
			created_at: ev.created_at ?? undefined,
			message_id: ev.message_id ?? undefined,
		})
		if (!toolEv) return
		ctx.toolTracker.processEvent(toolEv)
		ctx.toolTick++
	}

	// ── message events (cross-device sync) ───────────────────────────────

	function handleMessageEvent(ev: StreamEvent): void {
		if (ev.thread_id !== threadId) return
		if (isOwnEvent(ev)) return

		const data = (ev.data ?? {}) as Record<string, unknown>

		if (ev.type === 'message.created') {
			if (data.id && typeof data.id === 'string') {
				const newMsg = data as unknown as ApiMessage
				// defense-in-depth: if this is a user message that matches the
				// optimistic message, clear it to prevent double rendering
				if (newMsg.type === 'user' && ctx.optimisticUserMessage) {
					ctx.optimisticUserMessage = null
				}
				ctx.messageTree.set(newMsg.id, newMsg)
				// if the new message extends the current branch, move leaf
				if (newMsg.parent_id === ctx.currentLeafId) {
					ctx.currentLeafId = newMsg.id
				}
				ctx.rebuildRunBlocks()
			}
		} else if (ev.type === 'message.updated') {
			const msgId = (data.id as string) ?? ev.message_id
			if (msgId && ctx.messageTree.has(msgId)) {
				const existing = ctx.messageTree.get(msgId)!
				ctx.messageTree.set(msgId, { ...existing, ...data } as ApiMessage)
				ctx.rebuildRunBlocks()
			}
		} else if (ev.type === 'message.deleted') {
			const deletedIds = data.deleted_ids as string[] | undefined
			const msgId = (data.message_id as string) ?? ev.message_id
			if (deletedIds) {
				for (const id of deletedIds) ctx.messageTree.delete(id)
			} else if (msgId) {
				ctx.messageTree.delete(msgId)
			}
			// if the current leaf was deleted, walk up to find a valid one
			if (ctx.currentLeafId && !ctx.messageTree.has(ctx.currentLeafId)) {
				let validLeaf: string | null = null
				for (const m of ctx.messageTree.values()) {
					if (!validLeaf) {
						validLeaf = m.id
						continue
					}
					if (
						getMessageCreatedAt(m).getTime() >=
						getMessageCreatedAt(ctx.messageTree.get(validLeaf)!).getTime()
					) {
						validLeaf = m.id
					}
				}
				ctx.currentLeafId = validLeaf
			}
			ctx.rebuildRunBlocks()
		}
	}

	// ── typing events ────────────────────────────────────────────────────

	function handleTypingEvent(ev: StreamEvent): void {
		const data = (ev.data ?? {}) as Record<string, unknown>
		if (data.thread_id !== threadId) return
		if (isOwnEvent(ev)) return

		const userId = data.user_id as string | undefined
		if (!userId) return

		if (ev.type === 'typing.start' || ev.type === 'typing.user.start') {
			ctx.typingUsers.add(userId)
			// auto-expire after 8s if no further typing events arrive
			const prev = typingTimers.get(userId)
			if (prev) clearTimeout(prev)
			typingTimers.set(
				userId,
				setTimeout(() => {
					ctx.typingUsers.delete(userId)
					typingTimers.delete(userId)
				}, 8000)
			)
		} else if (ev.type === 'typing.stop' || ev.type === 'typing.user.stop') {
			ctx.typingUsers.delete(userId)
			const prev = typingTimers.get(userId)
			if (prev) clearTimeout(prev)
			typingTimers.delete(userId)
		}
	}

	// ── run events (run started/completed + active runs catchup) ─────────

	/** attempt to resume a run's SSE stream and feed it into consumeStream */
	function tryResumeRun(runId: string, agentId: string): void {
		// skip if we're already streaming (initiator's own run)
		if (ctx.isGenerating) return
		// skip if already resuming this run
		if (resumeAborts.has(runId)) return

		const ac = new AbortController()
		resumeAborts.set(runId, ac)

		const runGen = ctx.incrementActiveRun()
		ctx.isGenerating = true
		ctx.viewingStreamingBranch = true
		ctx.streamingLeafId = null
		ctx.streamingAssistantParentId = ctx.currentLeafId
		ctx.streamingAssistant = {
			runId: null,
			messageId: `resume-${runId}`,
			content: '',
			timestamp: new SvelteDate(),
			senderAgentId: agentId,
			toolCalls: [],
			isError: false,
			errorMessage: null,
		}

		const stream = resumeRunStream({
			runId,
			signal: ac.signal,
		})

		consumeStream(stream, { runId: runGen, threadId, parentId: null }, ctx)
			.catch(() => {
				// aborted or network error — expected on navigate-away
			})
			.finally(() => {
				resumeAborts.delete(runId)
				if (ctx.activeRun === runGen) {
					ctx.isGenerating = false
				}
			})
	}

	function handleRunEvent(ev: StreamMessage): void {
		// handle active runs signal (single message with list of run pointers)
		if (ev.type === 'runs.active') {
			const runs = ((ev as Record<string, unknown>).data ?? []) as RunSignal[]
			for (const run of runs) {
				if (run.thread_id !== threadId) continue
				if (run.run_id && run.agent_id) {
					ctx.activeAgentRuns.set(run.run_id, {
						threadId,
						runId: run.run_id,
						agentId: run.agent_id,
					})
					tryResumeRun(run.run_id, run.agent_id)
				}
			}
			return
		}

		// handle run.started
		if (ev.type === 'run.started') {
			const data = ((ev as Record<string, unknown>).data ?? {}) as RunSignal
			if (data.thread_id !== threadId) return
			if (!data.run_id || !data.agent_id) return
			ctx.activeAgentRuns.set(data.run_id, {
				threadId,
				runId: data.run_id,
				agentId: data.agent_id,
			})
			tryResumeRun(data.run_id, data.agent_id)
			return
		}

		// handle run.completed
		if (ev.type === 'run.completed') {
			const data = ((ev as Record<string, unknown>).data ?? {}) as RunSignal
			if (data.thread_id !== threadId) return
			if (!data.run_id) return
			ctx.activeAgentRuns.delete(data.run_id)
			// abort any active resume for this run (if SSE hasn't ended yet)
			const runAc = resumeAborts.get(data.run_id)
			if (runAc) {
				runAc.abort()
				resumeAborts.delete(data.run_id)
			}
			return
		}
	}

	// ── single unified listener ──────────────────────────────────────────

	const unsub = eventStreamClient.subscribe((msg) => {
		if (!msg || typeof msg !== 'object') return
		const ev = msg as StreamEvent & StreamMessage
		if (!ev.type || typeof ev.type !== 'string') return

		if (ev.type.startsWith('tool.')) {
			handleToolEvent(ev as StreamEvent)
		} else if (ev.type.startsWith('message.')) {
			handleMessageEvent(ev as StreamEvent)
		} else if (ev.type.startsWith('typing.')) {
			handleTypingEvent(ev as StreamEvent)
		} else if (
			ev.type === 'runs.active' ||
			ev.type === 'run.started' ||
			ev.type === 'run.completed'
		) {
			handleRunEvent(ev as StreamMessage)
		}
	})

	return () => {
		unsub()
		// cleanup typing timers
		for (const t of typingTimers.values()) clearTimeout(t)
		typingTimers.clear()
		ctx.typingUsers.clear()
		// cleanup resume aborts
		for (const ac of resumeAborts.values()) ac.abort()
		resumeAborts.clear()
		ctx.activeAgentRuns.clear()
	}
}

/** notify other sessions that this user started/stopped typing */
export function sendTypingEvent(threadId: string, typing: boolean): void {
	eventStreamClient.send({
		type: typing ? 'typing.start' : 'typing.stop',
		thread_id: threadId,
	})
}
