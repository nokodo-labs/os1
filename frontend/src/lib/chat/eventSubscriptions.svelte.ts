/**
 * real-time event subscriptions - single unified listener that dispatches
 * tool, run activity, message, attachment, and citation events by prefix.
 *
 * typing signals are NOT handled here: they belong to every thread the viewer
 * can see, not only the open one, so the global `chat` store tracks them.
 *
 * run lifecycle events (runs.active / run.started / run.completed / run.error)
 * are NOT handled here - they are owned by the global
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
import { isPeopleThread } from '$lib/stores/chat.svelte'
import { parseToolEvent } from '$lib/tools'
import { SvelteDate, SvelteMap, SvelteSet } from 'svelte/reactivity'
import {
	buildMessageChildren,
	contentPartsToText,
	getRunId,
	hasRunId,
	isPlaceholderMessageId,
	type ApiMessage,
} from './helpers'
import { parseRunActivityEvent, RUN_ACTIVITY_EVENT_PREFIX } from './runActivities'
import { parseRunFailureEvent, RUN_ERROR_EVENT_TYPE } from './runFailures'
import {
	getMessageClientSteeringId,
	getMessageSteeringRunId,
	getMessageSteeringState,
	type SteeringState,
} from './steering'
import { consumeStream } from './streamProcessor'
import { CHAT_SYSTEM_EVENT_TYPES, parseChatSystemEvents } from './systemEvents'
import { getLatestLeaf, reparentSuccessors } from './treeNavigation'
import type { ApiCitation, ChatContext } from './types'

/**
 * subscribe to all real-time chat events for a thread through a single
 * event stream listener. dispatches by event type prefix for performance.
 * also watches the global `activeRunsStore` to auto-resume any run for this
 * thread (whether it started before or after this chat page mounted).
 * returns an unsubscribe function that cleans up all internal state.
 */
export function subscribeToChatEvents(threadId: string, ctx: ChatContext): () => void {
	// abort controllers for resume streams, keyed by run_id
	const resumeAborts = new SvelteMap<string, AbortController>()
	// run ids we've already kicked off a resume for - prevents duplicate
	// resumes when the store re-emits (e.g. run.started after runs.active).
	const attemptedResumes = new SvelteSet<string>()

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

	/** apply a durable run failure for this thread. deduped by event id. */
	function handleRunFailureEvent(ev: StreamEvent): void {
		if (ev.thread_id !== threadId) return
		const failure = parseRunFailureEvent({
			id: ev.id,
			type: ev.type,
			data: (ev.data ?? {}) as Record<string, unknown>,
			created_at: ev.created_at ?? undefined,
			message_id: ev.message_id ?? undefined,
		})
		if (!failure) return
		ctx.recordRunFailure(failure)
	}

	/**
	 * apply an inline system row for this thread.
	 *
	 * `thread.updated` names no actor - its `user_id` is the thread owner, not
	 * whoever renamed it - so only the reader's OWN rename is attributed, and
	 * anyone else's renders without a name rather than crediting the wrong one.
	 */
	function handleSystemEvent(ev: StreamEvent): void {
		const data = (ev.data ?? {}) as Record<string, unknown>
		const eventThreadId =
			ev.thread_id ??
			(typeof data.thread_id === 'string' ? data.thread_id : null) ??
			(typeof data.resource_id === 'string' ? data.resource_id : null)
		if (eventThreadId !== threadId) return
		const events = parseChatSystemEvents(
			{
				id: ev.id,
				type: ev.type,
				data,
				created_at: ev.created_at ?? undefined,
				message_id: ev.message_id ?? undefined,
				thread_id: eventThreadId,
			},
			{
				selfActorUserId: isOwnEvent(ev) ? ctx.currentUserId : null,
				renameRows: ctx.thread ? isPeopleThread(ctx.thread) : false,
			}
		)
		for (const systemEvent of events) ctx.recordSystemEvent(systemEvent)
	}

	// message events (cross-device sync)

	function seedMessageCitations(msg: ApiMessage): void {
		if (msg.type === 'assistant' && msg.citations?.length) {
			ctx.citationSources.set(msg.id, msg.citations)
		}
	}

	/**
	 * retire the client-side bridge once the run's real message is in the tree.
	 *
	 * a bridge stands in for a message the backend had not persisted yet, so the
	 * moment the real one lands every pointer that named the bridge moves to the
	 * real id and the placeholder goes away. a live run is left alone: the delta
	 * path owns its bubble until that run ends or dies.
	 */
	function retireBridgeFor(newMsg: ApiMessage): void {
		const bridge = ctx.streamingAssistant
		if (!bridge || !isPlaceholderMessageId(bridge.messageId)) return
		if (ctx.isGenerating && !bridge.isError) return
		if (bridge.runId && hasRunId(newMsg) && getRunId(newMsg) !== bridge.runId) return
		if (ctx.streamingLeafId === null || isPlaceholderMessageId(ctx.streamingLeafId)) {
			ctx.streamingLeafId = newMsg.id
		}
		if (
			ctx.viewingStreamingBranch &&
			(ctx.currentLeafId === null || isPlaceholderMessageId(ctx.currentLeafId))
		) {
			ctx.currentLeafId = newMsg.id
		}
		ctx.streamingAssistantParentId = newMsg.id
		ctx.streamingAssistant = null
	}

	/**
	 * apply the canonical message the backend persisted for a run this session
	 * started - including the partial a failed run leaves behind.
	 *
	 * dropping it (which is what "we already rendered our own copy" used to mean)
	 * left the run's output on whatever id the client had invented, so the leaf
	 * never reached a message the backend has. the live bubble is the one
	 * exception: the run stream owns it and upserts the row itself.
	 */
	function applyOwnRunMessage(newMsg: ApiMessage): void {
		const bridge = ctx.streamingAssistant
		if (bridge?.messageId === newMsg.id && !bridge.isError) return
		const existing = ctx.messageTree.get(newMsg.id)
		if (existing) {
			const existingText = contentPartsToText(existing.content).trim()
			const newText = contentPartsToText(newMsg.content).trim()
			// a late empty confirmation must never blank text already rendered
			if (!newText && existingText) return
		}
		const confirmed = existing
			? ({
					...existing,
					...newMsg,
					parent_id: newMsg.parent_id ?? existing.parent_id,
				} satisfies ApiMessage)
			: newMsg
		ctx.messageTree.set(confirmed.id, confirmed)
		seedMessageCitations(confirmed)
		if (confirmed.parent_id !== null && confirmed.parent_id === ctx.currentLeafId) {
			ctx.currentLeafId = confirmed.id
		}
		retireBridgeFor(confirmed)
		ctx.rebuildRunBlocks()
	}

	function handleMessageEvent(ev: StreamEvent): void {
		if (ev.thread_id !== threadId) return
		const data = (ev.data ?? {}) as Record<string, unknown>
		const ownEvent = isOwnEvent(ev)

		if (ev.type === 'message.created') {
			if (data.id && typeof data.id === 'string') {
				const newMsg = data as unknown as ApiMessage
				// text steering writes steering_state onto the row it creates; an
				// invocation catch-up writes nothing and only names the ordinary
				// message it handed over. so the persisted state IS the
				// discriminator, and a catch-up renders as the message it is.
				const steeringState = getMessageSteeringState(newMsg)
				const clientSteeringId = getMessageClientSteeringId(newMsg)
				if (newMsg.type === 'user' && steeringState === 'queued') {
					const runId = getMessageSteeringRunId(newMsg)
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
					applyOwnRunMessage(newMsg)
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
				// if a steering event arrived before this message.created, re-apply
				// the stashed state now that the message is known - but only onto a
				// ghost bubble. for an ordinary message a catch-up named, the stash
				// was run progress, never a restyle.
				const stashed = pendingSteeringStates.get(newMsg.id)
				if (stashed) {
					pendingSteeringStates.delete(newMsg.id)
					if (steeringState != null || ctx.ownsSteeringMessage(newMsg.id)) {
						applySteeringState(newMsg.id, stashed.state, stashed.createdAt)
					}
				}
				// if the new message extends the current branch, move leaf
				if (newMsg.parent_id === ctx.currentLeafId) {
					// a user message that arrived live from another session and
					// lands on the visible tail plays the fallback entrance once.
					// own sends already animated via the optimistic send path.
					if (!ownEvent && newMsg.type === 'user') {
						ctx.markMessageEntrance(newMsg.id)
					}
					ctx.currentLeafId = newMsg.id
				}
				ctx.rebuildRunBlocks()
			}
		} else if (ev.type === 'message.updated') {
			const msgId = (data.id as string) ?? ev.message_id
			if (!msgId || !ctx.messageTree.has(msgId)) return
			const existing = ctx.messageTree.get(msgId)
			if (!existing) return
			// a run's reparent is fanned out from the session that started it, so
			// the structural move must apply regardless of `ownEvent`.
			const nextParentId = typeof data.parent_id === 'string' ? data.parent_id : null
			const reparented =
				nextParentId !== null && nextParentId !== (existing.parent_id ?? null)
			const moved = reparented ? reparentSuccessors(ctx, nextParentId, [msgId]) : false
			if (ownEvent) {
				// own content was applied optimistically; re-merging would undo a
				// newer local edit.
				if (moved) ctx.rebuildRunBlocks()
				return
			}
			const updated = { ...existing, ...data } as ApiMessage
			ctx.messageTree.set(msgId, updated)
			seedMessageCitations(updated)
			ctx.rebuildRunBlocks()
		} else if (ownEvent) {
			return
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
		const prevMeta = (existing.metadata ?? {}) as Record<string, unknown>
		const metadata: Record<string, unknown> = { ...prevMeta, steering_state: state }
		if (state === 'injected' && createdAt) metadata.steering_injected_at = createdAt
		if (state === 'dropped' && createdAt) metadata.steering_dropped_at = createdAt
		ctx.messageTree.set(messageId, {
			...existing,
			metadata: metadata,
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
				// invocation is server-owned, so this event also fires for an
				// ordinary message the user wrote and a run was caught up with.
				// only a ghost bubble may be restyled as dropped; a real message
				// stays exactly what it is. a catch-up is server-authorized and
				// cannot be retracted anyway.
				if (
					ctx.ownsSteeringMessage(mid) &&
					applySteeringState(mid, nextState, steeringCreatedAt)
				) {
					droppedChanged = true
				}
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
			// advance the chain cursor for EVERY message, even a deferred one: the
			// next link records this id as its parent and the deferred message is
			// injected later (via its own message.created) under the right parent.
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
		} else if (ev.type.startsWith('citation.')) {
			handleCitationEvent(ev as StreamEvent)
		} else if (ev.type.startsWith('run.steering.')) {
			handleSteeringEvent(ev as StreamEvent)
		} else if (ev.type.startsWith(RUN_ACTIVITY_EVENT_PREFIX)) {
			handleRunActivityEvent(ev as StreamEvent)
		} else if (ev.type === RUN_ERROR_EVENT_TYPE) {
			handleRunFailureEvent(ev as StreamEvent)
		} else if ((CHAT_SYSTEM_EVENT_TYPES as readonly string[]).includes(ev.type)) {
			handleSystemEvent(ev as StreamEvent)
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
