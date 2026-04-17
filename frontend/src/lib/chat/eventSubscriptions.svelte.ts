/**
 * real-time event subscriptions - single unified listener that dispatches
 * tool, message, typing, attachment, and citation events by prefix.
 *
 * run lifecycle events (runs.active / run.started / run.completed / run.error
 * / run.failed) are NOT handled here - they are owned by the global
 * `activeRunsStore`, which tracks runs across all threads regardless of which
 * chat page is mounted. this module reacts to that store via `$effect.root`
 * to pick up any run for the current thread and resume its SSE stream.
 */

import { resumeRunStream } from '$lib/api/streaming/chatStream'
import { isOwnEvent } from '$lib/api/sessionId'
import {
	eventStreamClient,
	type StreamEvent,
	type StreamMessage,
} from '$lib/api/streaming/eventStream.svelte'
import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { parseToolEvent } from '$lib/tools'
import { SvelteDate, SvelteMap } from 'svelte/reactivity'
import { buildMessageChildren, type ApiMessage } from './helpers'
import { consumeStream } from './streamProcessor'
import { getLatestLeaf } from './treeNavigation'
import type { ApiCitation, ChatContext } from './types'

/**
 * subscribe to all real-time chat events for a thread through a single
 * event stream listener. dispatches by event type prefix for performance.
 * also watches the global `activeRunsStore` to auto-resume any run for this
 * thread (whether it started before or after this chat page mounted).
 * returns an unsubscribe function that cleans up all internal state.
 */
export function subscribeToChatEvents(threadId: string, ctx: ChatContext): () => void {
	// typing auto-expire timers
	const typingTimers = new SvelteMap<string, ReturnType<typeof setTimeout>>()
	// abort controllers for resume streams, keyed by run_id
	const resumeAborts = new SvelteMap<string, AbortController>()
	// run ids we've already kicked off a resume for - prevents duplicate
	// resumes when the store re-emits (e.g. run.started after runs.active).
	const attemptedResumes = new Set<string>()

	ctx.typingUsers.clear()

	// tool events

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
	}

	// message events (cross-device sync)

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
			const parentId = (data.parent_id as string | null | undefined) ?? null
			const msgId = (data.message_id as string) ?? ev.message_id
			if (deletedIds) {
				for (const id of deletedIds) ctx.messageTree.delete(id)
			} else if (msgId) {
				ctx.messageTree.delete(msgId)
			}
			// if the current leaf was deleted, find a new valid leaf
			if (ctx.currentLeafId && !ctx.messageTree.has(ctx.currentLeafId)) {
				if (parentId && ctx.messageTree.has(parentId)) {
					// walk from the deleted message's parent to the deepest remaining leaf
					ctx.currentLeafId = getLatestLeaf(parentId, ctx)
				} else {
					// fallback: find any tree root and walk to its deepest leaf
					const children = buildMessageChildren(ctx.messageTree.values())
					const roots = children.get(null)
					if (roots && roots.length > 0) {
						ctx.currentLeafId = getLatestLeaf(roots[roots.length - 1], ctx)
					} else {
						ctx.currentLeafId = null
					}
				}
			}
			ctx.rebuildRunBlocks()
		}
	}

	// typing events

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

	// run resumption (driven by the global activeRunsStore)

	/** attempt to resume a run's SSE stream and feed it into consumeStream */
	function tryResumeRun(runId: string, agentId: string): void {
		// skip if we're already streaming (initiator's own run)
		if (ctx.isGenerating) return
		// skip if already resuming this run
		if (resumeAborts.has(runId)) return
		// skip duplicates (store re-emits, etc.)
		if (attemptedResumes.has(runId)) return
		attemptedResumes.add(runId)

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
			.catch((err: unknown) => {
				// intentional abort (navigate away, run completed/errored) - ignore
				if (ac.signal.aborted) return
				if (ctx.activeRun !== runGen) return
				// real error reached us: surface it in the ghost assistant bubble
				const errorMessage =
					err instanceof Error && err.message
						? err.message
						: 'lost connection to the run'
				if (ctx.streamingAssistant?.messageId === `resume-${runId}`) {
					ctx.streamingAssistant.isError = true
					ctx.streamingAssistant.errorMessage = errorMessage
				}
			})
			.finally(() => {
				resumeAborts.delete(runId)
				if (ctx.activeRun === runGen) {
					ctx.toolTracker.closeAllActive()
					ctx.isGenerating = false
				}
			})
	}

	/** abort a resume stream when its run is removed from the global store. */
	function dropResumeForRun(runId: string): void {
		const ac = resumeAborts.get(runId)
		if (ac) {
			ac.abort()
			resumeAborts.delete(runId)
		}
		// clear ghost streaming assistant if it belonged to this run
		if (ctx.streamingAssistant?.messageId === `resume-${runId}`) {
			ctx.toolTracker.closeAllActive()
		}
	}

	// attachment events (state changes from backend)

	function handleAttachmentEvent(ev: StreamEvent): void {
		if (ev.thread_id !== threadId) return
		const data = (ev.data ?? {}) as Record<string, unknown>
		const fileId = data.file_id as string | undefined
		if (!fileId) return

		if (ev.type === 'attachment.decayed') {
			ctx.attachmentStates.set(fileId, 'reference')
		} else if (ev.type === 'attachment.revealed') {
			ctx.attachmentStates.set(fileId, 'active')
		}
	}

	// citation events

	function handleCitationEvent(ev: StreamEvent): void {
		if (ev.thread_id !== threadId) return
		const data = (ev.data ?? {}) as Record<string, unknown>
		const citations = data.citations as ApiCitation[] | undefined
		if (!Array.isArray(citations)) return
		const valid = citations.filter((c) => typeof c.index === 'number')
		if (valid.length > 0) {
			ctx.addCitationSources(valid)
		}
	}

	// single unified listener (no run.* handling - see activeRunsStore)

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
		} else if (ev.type.startsWith('attachment.')) {
			handleAttachmentEvent(ev as StreamEvent)
		} else if (ev.type.startsWith('citation.')) {
			handleCitationEvent(ev as StreamEvent)
		}
	})

	// reactive bridge to the global run store: any run for this thread that
	// exists in the store (now or in the future) is auto-resumed. this works
	// whether the run started before this page mounted (runs.active catch-up
	// from ws connect) or after (run.started broadcast).
	const disposeRunWatcher = $effect.root(() => {
		$effect(() => {
			for (const run of activeRunsStore.runs.values()) {
				if (run.threadId !== threadId) continue
				tryResumeRun(run.runId, run.agentId)
			}
			// drop any resume whose run no longer exists in the global store
			for (const runId of resumeAborts.keys()) {
				if (!activeRunsStore.runs.has(runId)) dropResumeForRun(runId)
			}
		})
	})

	return () => {
		unsub()
		disposeRunWatcher()
		// cleanup typing timers
		for (const t of typingTimers.values()) clearTimeout(t)
		typingTimers.clear()
		ctx.typingUsers.clear()
		// cleanup resume aborts
		for (const ac of resumeAborts.values()) ac.abort()
		resumeAborts.clear()
		attemptedResumes.clear()
	}
}

/** notify other sessions that this user started/stopped typing */
export function sendTypingEvent(threadId: string, typing: boolean): void {
	eventStreamClient.send({
		type: typing ? 'typing.start' : 'typing.stop',
		thread_id: threadId,
	})
}
