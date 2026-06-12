/**
 * real-time event subscriptions - single unified listener that dispatches
 * tool, run activity, message, typing, attachment, and citation events by prefix.
 *
 * run lifecycle events (runs.active / run.started / run.completed / run.error
 * / run.failed) are NOT handled here - they are owned by the global
 * `activeRunsStore`, which tracks runs across all threads regardless of which
 * chat page is mounted. this module reacts to that store via `$effect.root`
 * to pick up any run for the current thread and resume its SSE stream.
 */

import { isOwnEvent } from '$lib/api/sessionId'
import { resumeRunStream, StreamHttpError } from '$lib/api/streaming/chatStream'
import {
    eventStreamClient,
    type StreamEvent,
    type StreamMessage,
} from '$lib/api/streaming/eventStream.svelte'
import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { parseToolEvent } from '$lib/tools'
import { SvelteDate, SvelteMap, SvelteSet } from 'svelte/reactivity'
import { buildMessageChildren, contentPartsToText, type ApiMessage } from './helpers'
import { parseRunActivityEvent, RUN_ACTIVITY_EVENT_PREFIX } from './runActivities'
import {
    getMessageClientSteeringId,
    getMessageSteeringRunId,
    getMessageSteeringState,
    type SteeringState,
} from './steering'
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
	const attemptedResumes = new SvelteSet<string>()

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

	/** apply live run activity events for this thread. */
	function handleRunActivityEvent(ev: StreamEvent): void {
		if (ev.thread_id !== threadId) return
		const activityEv = parseRunActivityEvent({
			id: ev.id,
			type: ev.type,
			data: (ev.data ?? {}) as Record<string, unknown>,
			created_at: ev.created_at ?? undefined,
			message_id: ev.message_id ?? undefined,
		})
		if (!activityEv) return
		ctx.processRunActivityEvent(activityEv)
	}

	// message events (cross-device sync)

	function seedMessageCitations(msg: ApiMessage): void {
		if (msg.type === 'assistant' && msg.citations?.length) {
			ctx.citationSources.set(msg.id, msg.citations)
		}
	}

	function mergeOwnAssistantConfirmation(newMsg: ApiMessage): boolean {
		if (newMsg.type !== 'assistant') return false
		if (ctx.streamingAssistant?.messageId === newMsg.id) return false
		const existing = ctx.messageTree.get(newMsg.id)
		if (!existing || existing.type !== 'assistant') return false
		const existingText = contentPartsToText(existing.content).trim()
		const newText = contentPartsToText(newMsg.content).trim()
		if (!newText && existingText) return true
		const confirmed = {
			...newMsg,
			parent_id: newMsg.parent_id ?? existing.parent_id,
		} satisfies ApiMessage
		ctx.messageTree.set(confirmed.id, confirmed)
		seedMessageCitations(confirmed)
		if (ctx.currentLeafId === existing.id || ctx.streamingLeafId === existing.id) {
			ctx.currentLeafId = confirmed.id
			ctx.streamingLeafId = confirmed.id
		}
		ctx.rebuildRunBlocks()
		return true
	}

	function handleMessageEvent(ev: StreamEvent): void {
		if (ev.thread_id !== threadId) return
		const data = (ev.data ?? {}) as Record<string, unknown>
		const ownEvent = isOwnEvent(ev)

		if (ev.type === 'message.created') {
			if (data.id && typeof data.id === 'string') {
				const newMsg = data as unknown as ApiMessage
				const steeringState = getMessageSteeringState(newMsg)
				if (newMsg.type === 'user' && steeringState === 'queued') {
					const runId = getMessageSteeringRunId(newMsg)
					const clientSteeringId = getMessageClientSteeringId(newMsg)
					const stashed = pendingSteeringStates.get(newMsg.id)
					if (stashed?.state === 'dropped') {
						pendingSteeringStates.delete(newMsg.id)
						ctx.removeQueuedSteeringMessage(newMsg.id)
						if (clientSteeringId) ctx.removeQueuedSteeringMessage(clientSteeringId)
						return
					}
					if (stashed?.state === 'injected') {
						if (clientSteeringId && runId) {
							ctx.confirmQueuedSteeringMessage(
								clientSteeringId,
								newMsg.id,
								runId,
								newMsg
							)
						}
						if (
							ctx.injectQueuedSteeringMessage(newMsg.id, newMsg, {
								runId: stashed.runId,
								parentId: stashed.parentId,
								createdAt: stashed.createdAt,
							})
						) {
							pendingSteeringStates.delete(newMsg.id)
							if (isInjectedSteeringTail(newMsg.id)) {
								ctx.setSteeringParentOverride(stashed.runId, newMsg.id)
								attachActiveAssistantAfterSteering(stashed.runId, newMsg.id)
							}
							ctx.rebuildRunBlocks()
						}
						return
					}
					const confirmed =
						clientSteeringId && runId
							? ctx.confirmQueuedSteeringMessage(
									clientSteeringId,
									newMsg.id,
									runId,
									newMsg
								)
							: false
					if (runId && !confirmed) {
						ctx.stageQueuedSteeringMessage({
							id: newMsg.id,
							clientSteeringId: clientSteeringId ?? undefined,
							runId,
							content: newMsg.content,
							text: '',
							attachments: [],
							createdAt: new SvelteDate(newMsg.created_at),
							message: newMsg,
						})
					}
					return
				}
				if (newMsg.type === 'user' && steeringState === 'dropped') return
				if (ownEvent && newMsg.type !== 'user') {
					if (mergeOwnAssistantConfirmation(newMsg)) return
					return
				}
				// defense-in-depth: if this is a user message that matches the
				// optimistic message, clear it to prevent double rendering
				if (newMsg.type === 'user' && ctx.optimisticUserMessage) {
					ctx.optimisticUserMessage = null
				}
				if (newMsg.type === 'user') {
					const runId = getMessageSteeringRunId(newMsg)
					void ctx.flushPendingSteeringMessages(runId, newMsg.id)
				}
				ctx.messageTree.set(newMsg.id, newMsg)
				seedMessageCitations(newMsg)
				// re-parent the not-yet-streamed assistant placeholder onto this
				// just-persisted user message. without this, a WS message.created
				// that beats the POST stream's own message_created frame leaves
				// the placeholder parented at the previous leaf, so the new user
				// message counts as its sibling and flashes a "2/2" branch badge.
				// idempotent: the later SSE frame sets the same parent.
				if (
					ownEvent &&
					newMsg.type === 'user' &&
					ctx.isGenerating &&
					ctx.streamingAssistant &&
					!ctx.messageTree.has(ctx.streamingAssistant.messageId) &&
					newMsg.parent_id != null &&
					newMsg.parent_id === ctx.streamingAssistantParentId
				) {
					ctx.streamingAssistantParentId = newMsg.id
				}
				// if a steering event arrived before this message.created,
				// re-apply the stashed state now that the message is known.
				const stashed = pendingSteeringStates.get(newMsg.id)
				if (stashed) {
					applySteeringState(newMsg.id, stashed.state, stashed.createdAt)
					pendingSteeringStates.delete(newMsg.id)
				}
				// if the new message extends the current branch, move leaf
				if (newMsg.parent_id === ctx.currentLeafId) {
					ctx.currentLeafId = newMsg.id
				}
				ctx.rebuildRunBlocks()
			}
		} else if (ownEvent) {
			return
		} else if (ev.type === 'message.updated') {
			const msgId = (data.id as string) ?? ev.message_id
			if (msgId && ctx.messageTree.has(msgId)) {
				const existing = ctx.messageTree.get(msgId)
				if (!existing) return
				const updated = { ...existing, ...data } as ApiMessage
				ctx.messageTree.set(msgId, updated)
				seedMessageCitations(updated)
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
		const resumeParentId = ctx.currentLeafId
		ctx.streamingAssistantParentId = resumeParentId
		ctx.streamingAssistant = {
			runId,
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

		consumeStream(stream, { runId: runGen, threadId, parentId: resumeParentId, agentId }, ctx)
			.catch((err: unknown) => {
				// intentional abort (navigate away, run completed/errored) - ignore
				if (ac.signal.aborted) return
				if (ctx.activeRun !== runGen) return
				// 404 = run already finished between store snapshot and our request.
				// not a real error - just clear the placeholder and move on.
				if (err instanceof StreamHttpError && err.status === 404) {
					activeRunsStore.forgetRun(runId)
					if (ctx.streamingAssistant?.messageId === `resume-${runId}`) {
						ctx.streamingAssistant = null
						ctx.streamingAssistantParentId = null
						ctx.rebuildRunBlocks()
					}
					return
				}
				// real error reached us: surface it in the ghost assistant bubble
				const errorMessage =
					err instanceof Error && err.message ? err.message : 'lost connection to the run'
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
		// clear ghost streaming assistant if it belonged to this run.
		// the run is gone from the global store, so any partial bubble we built
		// from replayed sse_log frames would be a stale ghost otherwise.
		if (ctx.streamingAssistant?.messageId === `resume-${runId}`) {
			ctx.toolTracker.closeAllActive()
			ctx.streamingAssistant = null
			ctx.streamingAssistantParentId = null
			ctx.rebuildRunBlocks()
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

	type PendingSteeringState = {
		state: SteeringState
		runId: string
		parentId: string | null
		createdAt: string | null
	}

	const pendingSteeringStates = new SvelteMap<string, PendingSteeringState>()

	function applySteeringState(
		messageId: string,
		state: SteeringState,
		createdAt: string | null
	): boolean {
		const existing = ctx.messageTree.get(messageId)
		if (!existing) return false
		const prevMeta = (existing.metadata_ ?? {}) as Record<string, unknown>
		const metadata: Record<string, unknown> = { ...prevMeta, steering_state: state }
		if (state === 'injected' && createdAt) metadata.steering_injected_at = createdAt
		if (state === 'dropped' && createdAt) metadata.steering_dropped_at = createdAt
		ctx.messageTree.set(messageId, {
			...existing,
			metadata_: metadata,
		} as ApiMessage)
		return true
	}

	function attachActiveAssistantAfterSteering(runId: string, messageId: string): boolean {
		const active = ctx.streamingAssistant
		if (!active || active.runId !== runId) return false
		const existing = ctx.messageTree.get(active.messageId)
		if (!existing) return false
		ctx.messageTree.set(active.messageId, { ...existing, parent_id: messageId })
		ctx.streamingAssistantParentId = messageId
		if (ctx.viewingStreamingBranch) ctx.currentLeafId = active.messageId
		return true
	}

	function isInjectedSteeringTail(messageId: string): boolean {
		for (const pending of pendingSteeringStates.values()) {
			if (pending.state === 'injected' && pending.parentId === messageId) return false
		}
		for (const message of ctx.messageTree.values()) {
			if (
				message.parent_id === messageId &&
				message.type === 'user' &&
				getMessageSteeringState(message) === 'injected'
			) {
				return false
			}
		}
		return true
	}

	function injectSteeringMessage(
		messageId: string,
		runId: string,
		parentId: string | null,
		createdAt: string | null
	): boolean {
		let injected = false
		const apply = () => {
			injected = ctx.injectQueuedSteeringMessage(messageId, undefined, {
				runId,
				parentId,
				createdAt,
			})
			if (!injected) return
			ctx.setSteeringParentOverride(runId, messageId)
			attachActiveAssistantAfterSteering(runId, messageId)
			ctx.rebuildRunBlocks()
		}

		const hasQueuedBubble = ctx.queuedSteeringMessages.some((msg) => msg.id === messageId)
		const start = document.startViewTransition
		if (hasQueuedBubble && start) {
			start.call(document, apply)
		} else {
			apply()
		}
		return injected
	}

	function handleSteeringEvent(ev: StreamEvent): void {
		const data = (ev.data ?? {}) as Record<string, unknown>
		const eventThreadId =
			typeof ev.thread_id === 'string'
				? ev.thread_id
				: typeof data.thread_id === 'string'
					? data.thread_id
					: null
		if (eventThreadId !== threadId) return
		const messageIds = (data.message_ids as string[] | undefined) ?? []
		if (messageIds.length === 0) return
		const runId = typeof data.run_id === 'string' ? data.run_id : null
		if (!runId) return
		const eventParentId = typeof data.parent_id === 'string' ? data.parent_id : null
		let nextState: SteeringState
		if (ev.type === 'run.steering.queued') nextState = 'queued'
		else if (ev.type === 'run.steering.injected') nextState = 'injected'
		else if (ev.type === 'run.steering.dropped') nextState = 'dropped'
		else return
		const steeringCreatedAt =
			nextState === 'queued' && typeof data.steering_enqueued_at === 'string'
				? data.steering_enqueued_at
				: nextState === 'injected' && typeof data.steering_injected_at === 'string'
					? data.steering_injected_at
					: nextState === 'dropped' && typeof data.steering_dropped_at === 'string'
						? data.steering_dropped_at
						: (ev.created_at ?? null)
		let droppedChanged = false
		let nextInjectedParentId = eventParentId ?? ctx.currentLeafId
		for (const mid of messageIds) {
			if (nextState === 'queued') {
				pendingSteeringStates.set(mid, {
					state: nextState,
					runId,
					parentId: null,
					createdAt: steeringCreatedAt,
				})
				continue
			}
			if (nextState === 'dropped') {
				ctx.removeQueuedSteeringMessage(mid)
				if (applySteeringState(mid, nextState, steeringCreatedAt)) droppedChanged = true
				pendingSteeringStates.set(mid, {
					state: nextState,
					runId,
					parentId: null,
					createdAt: steeringCreatedAt,
				})
				continue
			}

			const parentId = nextInjectedParentId
			const injected = injectSteeringMessage(mid, runId, parentId, steeringCreatedAt)
			nextInjectedParentId = mid
			if (injected) {
				pendingSteeringStates.delete(mid)
			} else {
				pendingSteeringStates.set(mid, {
					state: nextState,
					runId,
					parentId,
					createdAt: steeringCreatedAt,
				})
			}
		}
		if (nextState === 'injected') {
			ctx.setSteeringParentOverride(runId, messageIds[messageIds.length - 1])
		}
		if (droppedChanged) ctx.rebuildRunBlocks()
	}

	// single unified listener (no run.* lifecycle handling - see activeRunsStore)

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
		} else if (ev.type.startsWith('citation.')) {
			handleCitationEvent(ev as StreamEvent)
		} else if (ev.type.startsWith('run.steering.')) {
			handleSteeringEvent(ev as StreamEvent)
		} else if (ev.type.startsWith(RUN_ACTIVITY_EVENT_PREFIX)) {
			handleRunActivityEvent(ev as StreamEvent)
		}
	})

	// reactive bridge to the global run store: any run for this thread that
	// exists in the store (now or in the future) is auto-resumed. this works
	// whether the run started before this page mounted (runs.active catch-up
	// from ws connect) or after (run.started broadcast).
	const disposeRunWatcher = $effect.root(() => {
		$effect(() => {
			// also depend on isGenerating: tryResumeRun bails while a previous
			// resume is still wrapping up. when its finally clears isGenerating
			// we want this effect to re-fire and try again, otherwise the
			// placeholder bubble never appears on rapid navigate-away/back.
			void ctx.isGenerating
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
