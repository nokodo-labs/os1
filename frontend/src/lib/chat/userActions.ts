/**
 * user-initiated chat actions - send, regenerate, stop, edit, delete.
 */

import { api } from '$lib/api/client'
import { StreamHttpError, type MessageSplice, type RunInput } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import {
	deriveToolChoice,
	originatedResourceRefs,
	toResourceRefs,
	type RunModifiers,
} from '$lib/chat/attachments'
import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { agents } from '$lib/stores/agents.svelte'
import { isPeopleThread } from '$lib/stores/chat.svelte'
import { modals, type ConfirmDeleteToggle } from '$lib/stores/modals.svelte'
import { showError } from '$lib/stores/notifications.svelte'
import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
import { SvelteDate } from 'svelte/reactivity'
import { loadTree, syncCacheAfterRun } from './dataLoader'
import {
	computeIsAtBottom,
	contentPartsToText,
	finalizeStreamingAssistantAsPartial,
	isPlaceholderMessageId,
	markRunBridgeFailed,
	markRunNotDelivered,
} from './helpers'
import { runReachedBackend, runThreadStream } from './streamProcessor'
import { getLatestLeaf } from './treeNavigation'
import type { ChatContext, DeleteOriginatedOptions, PendingRunInput } from './types'

function resolveLeafAfterDelete(startParentId: string | null, ctx: ChatContext): string | null {
	if (startParentId && ctx.messageTree.has(startParentId)) {
		return getLatestLeaf(startParentId, ctx)
	}

	const roots = ctx.messageChildren.get(null)
	if (roots && roots.length > 0) {
		return getLatestLeaf(roots[roots.length - 1], ctx)
	}

	return null
}

function createLocalSteeringMessageId(): string {
	if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
		return `local-steering-${crypto.randomUUID()}`
	}
	return `local-steering-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function cloneRunInput(input: RunInput): PendingRunInput {
	return {
		...input,
		content: input.content?.map((part) => ({ ...part })),
		attachments: input.attachments?.map((att) => ({ ...att })),
		originated_resources: input.originated_resources?.map((res) => ({ ...res })),
	}
}

/** a run's input is an ordinary user message, so text becomes one text part. */
function buildRunInput(
	text: string,
	attachments?: RunModifiers['attachments'],
	replyToMessageId?: string | null
): RunInput {
	const input: RunInput = { type: 'user' }
	if (text) input.content = [{ type: 'text', text }]
	if (attachments && attachments.length > 0) {
		input.attachments = toResourceRefs(attachments)
		const originated = originatedResourceRefs(attachments)
		if (originated.length > 0) input.originated_resources = originated
	}
	// a reply is a semantic anchor, never tree placement - that stays `splice`.
	if (replyToMessageId) input.reply_to_message_id = replyToMessageId
	return input
}

function steeringEnabledForAgent(agentId: string): boolean {
	const targetAgent = agents.get(agentId)
	const features = (
		targetAgent?.config as { features?: { steering?: { enabled?: boolean } } } | undefined
	)?.features
	return features?.steering?.enabled !== false
}

function resolveSteeringParentId(ctx: ChatContext, runId: string): string | null {
	const queuedParent = ctx.queuedSteeringMessages
		.filter((message) => message.runId === runId && message.deliveryState !== 'sending')
		.at(-1)
	if (queuedParent) return queuedParent.id

	const parentId = ctx.currentLeafId
	if (
		parentId &&
		ctx.messageTree.has(parentId) &&
		parentId !== ctx.streamingLeafId &&
		parentId !== ctx.streamingAssistant?.messageId
	) {
		return parentId
	}

	const streamingParentId = ctx.streamingAssistantParentId
	if (streamingParentId && ctx.messageTree.has(streamingParentId)) {
		return streamingParentId
	}
	return null
}

/** how long to wait before the single automatic retry of a busy-thread write. */
const BUSY_RETRY_DELAY_MS = 350

/**
 * whether a 409 means "the thread lock was contended, retry" rather than a
 * permanent rejection (e.g. "this message already has a sub-thread").
 *
 * every tree write serializes on a per-thread lock with a 5s cap; past that the
 * request returns 409 and NOTHING was written, so retrying is safe.
 */
function isThreadBusy(status: number, error: unknown): boolean {
	if (status !== 409) return false
	const detail =
		typeof error === 'object' && error !== null && 'detail' in error
			? (error as { detail: unknown }).detail
			: null
	return typeof detail === 'string' && detail.toLowerCase().includes('busy')
}

/**
 * post a message, retrying once if the thread lock was contended.
 *
 * only the WRITE is retried: it either took the lock or it did not, so no
 * partial state can exist to duplicate.
 */
async function postMessageWithBusyRetry(
	threadId: string,
	body: components['schemas']['MessageCreate']
) {
	const send = () =>
		api.POST('/v1/threads/{thread_id}/messages', {
			params: { path: { thread_id: threadId } },
			body,
		})

	const first = await send()
	if (!first.error || !isThreadBusy(first.response?.status ?? 0, first.error)) return first

	await new Promise((resolve) => setTimeout(resolve, BUSY_RETRY_DELAY_MS))
	return send()
}

/**
 * user-facing text for a failed run.
 *
 * a 503 is the one failure where the message DID commit: the write took the
 * lock and only the run failed to become ready, so retry the run rather than
 * re-sending (which would duplicate the message).
 */
function runFailureMessage(error: unknown): string {
	if (error instanceof StreamHttpError && error.status === 503) {
		return 'your message was sent, but the agent could not start. try again.'
	}
	return error instanceof Error ? error.message : 'something went wrong'
}

/** post a plain human message in a people conversation (no agent run). */
async function postConversationMessage(
	ctx: ChatContext,
	runInput: RunInput,
	displayText: string
): Promise<void> {
	if (!ctx.thread) return
	ctx.lastRunInput = displayText
	ctx.inputValue = ''
	const body: components['schemas']['MessageCreate'] = { ...runInput }
	const splice = resolveRunSplice(ctx, ctx.currentLeafId)
	if (splice) body.splice = splice
	const { data: message, error } = await postMessageWithBusyRetry(ctx.thread.id, body)
	if (error || !message) {
		console.error('failed to send message', error)
		showError('could not send message')
		return
	}
	ctx.messageTree.set(message.id, message)
	ctx.currentLeafId = message.id
	ctx.rebuildRunBlocks()
	ctx.autoScroll = true
	void ctx.queueScrollToBottom('smooth')
}

/**
 * placement is a tri-state: a splice names an explicit parent, and omitting it
 * entirely means "continue from the head". a null parent_id roots a NEW tree and
 * is a 400 in a shared thread, so an unknown parent must never collapse onto it.
 *
 * being in the tree is not enough to be sendable: a failed run leaves its own
 * placeholder there and the leaf pointing at it, and the backend parses a splice
 * parent as a typeid - so naming one 422s every run from then on.
 */
function resolveRunSplice(
	ctx: ChatContext,
	preferredParentId: string | null
): MessageSplice | undefined {
	const candidates = [
		preferredParentId,
		ctx.streamingAssistantParentId,
		ctx.thread?.current_message_id ?? null,
	]
	for (const candidate of candidates) {
		if (!candidate) continue
		if (candidate === ctx.streamingLeafId) continue
		if (candidate === ctx.streamingAssistant?.messageId) continue
		if (isPlaceholderMessageId(candidate)) continue
		if (ctx.messageTree.has(candidate)) return { parent_id: candidate }
	}
	return undefined
}

function stagePendingSteeringMessage(
	ctx: ChatContext,
	runId: string,
	displayText: string,
	modifiers: RunModifiers | undefined,
	runInput: RunInput
): void {
	const clientSteeringId = createLocalSteeringMessageId()
	ctx.stageQueuedSteeringMessage({
		id: clientSteeringId,
		clientSteeringId,
		runId,
		content: [],
		text: displayText,
		attachments: modifiers?.attachments ?? [],
		createdAt: new SvelteDate(),
		message: null,
		deliveryState: 'sending',
		input: cloneRunInput(runInput),
	})
}

/** send a new user message and stream the agent response */
export async function handleSendMessage(
	content: string,
	ctx: ChatContext,
	modifiers?: RunModifiers
): Promise<void> {
	const trimmed = content.trim()
	const hasAttachments = modifiers?.attachments && modifiers.attachments.length > 0
	if (!trimmed && !hasAttachments) return
	if (!ctx.thread) return

	// a message lands at the branch leaf, so a view still paging down from the
	// reader's last-read point has to catch up first: the window's leaf is not
	// the thread's, and posting against it would fork the conversation.
	if (ctx.hasNewerMessages) {
		await loadTree(ctx.thread.id, ctx, { anchorMessageId: null })
		if (!ctx.thread) return
	}

	const runInput = buildRunInput(trimmed, modifiers?.attachments, modifiers?.replyToMessageId)

	const displayText = trimmed || modifiers?.attachments.map((a) => a.filename).join(', ') || ''

	// with more than one writer, send only sends. invoking an agent is a
	// separate affordance, never a side effect of the send button, and a live
	// run is not steered just because it exists. the one exception is an agent
	// the user armed for THIS send, which is that separate affordance firing.
	if (isPeopleThread(ctx.thread)) {
		const invokeAgentId = modifiers?.invokeAgentId ?? null
		if (!invokeAgentId) {
			await postConversationMessage(ctx, runInput, displayText)
			return
		}
		await startAgentRun(ctx, invokeAgentId, runInput, displayText, trimmed, modifiers)
		return
	}

	// steering: queued messages stay outside the thread until the backend
	// broadcasts that the running agent has injected them.
	//
	// a failed run leaves its streamingAssistant in place so the error bubble
	// keeps rendering. that is presentation, not a live run - treating it as
	// one queues the next message as steering against a run that already died.
	const hasFailedRun = ctx.streamingAssistant?.isError === true
	const hasLocalRunInProgress =
		!hasFailedRun && (ctx.isGenerating || ctx.streamingAssistant !== null)
	const activeRuns = activeRunsStore.getRunsForThread(ctx.thread.id)
	const activeRun = activeRuns[activeRuns.length - 1] ?? null
	const streamingRunId = ctx.streamingAssistant?.runId ?? null
	const targetRunId = hasLocalRunInProgress ? (activeRun?.runId ?? streamingRunId) : null
	const targetAgentId =
		activeRun?.agentId ?? ctx.streamingAssistant?.senderAgentId ?? selectedAgent?.id ?? null
	const canQueueForUnconfirmedRun =
		hasLocalRunInProgress && ctx.streamingAssistant !== null && !targetRunId
	if (targetRunId || canQueueForUnconfirmedRun) {
		// gate: if the run's agent has steering disabled, fall through to
		// starting a new run (concurrent runs) instead of attempting to steer.
		// the backend exposes config as a free-form dict; the structured
		// shape is documented in api/schemas/agent_config.py (regenerate
		// types after the schema is migrated to AgentConfig).
		const steeringAgentId = targetAgentId || selectedAgent?.id || null
		const steeringEnabled = steeringAgentId ? steeringEnabledForAgent(steeringAgentId) : true
		if (!steeringEnabled) {
			// fall through - skip the steering branch
		} else {
			ctx.lastRunInput = displayText
			ctx.inputValue = ''
			if (canQueueForUnconfirmedRun) {
				stagePendingSteeringMessage(
					ctx,
					targetRunId ?? '',
					displayText,
					modifiers,
					runInput
				)
				return
			}
			if (!targetRunId) return
			stagePendingSteeringMessage(ctx, targetRunId, displayText, modifiers, runInput)
			void ctx.flushPendingSteeringMessages(
				targetRunId,
				resolveSteeringParentId(ctx, targetRunId)
			)
			return
		}
	}

	// a run creates the user message and the agent reply together.
	const composeAgentId = selectedAgent?.id ?? null
	if (!composeAgentId) {
		ctx.lastRunInput = displayText
		ctx.optimisticUserMessage = {
			text: trimmed,
			attachments: modifiers?.attachments ?? [],
			timestamp: new SvelteDate(),
		}
		ctx.viewingStreamingBranch = true
		ctx.streamingAssistant = {
			runId: null,
			messageId: 'pending-no-agent',
			content: '',
			timestamp: new SvelteDate(),
			senderAgentId: null,
			toolCalls: [],
			isError: true,
			errorMessage: 'select an agent to generate a response.',
		}
		ctx.rebuildRunBlocks()
		return
	}
	await startAgentRun(ctx, composeAgentId, runInput, displayText, trimmed, modifiers)
}

/**
 * start a run: the user message and the agent reply are created together.
 *
 * shared by the solo composer and by an explicit invocation in a people thread,
 * so both get the same optimistic bubble, the same failure bubble, and the same
 * 503 reload - a 503 means the message committed and only the run failed, so it
 * is reloaded rather than re-sent.
 */
async function startAgentRun(
	ctx: ChatContext,
	agentId: string,
	runInput: RunInput,
	displayText: string,
	trimmed: string,
	modifiers: RunModifiers | undefined
): Promise<void> {
	const thread = ctx.thread
	if (!thread) return
	ctx.lastRunInput = displayText
	ctx.inputValue = ''
	ctx.optimisticUserMessage = {
		text: trimmed,
		attachments: modifiers?.attachments ?? [],
		timestamp: new SvelteDate(),
	}
	const shouldAutoScroll = ctx.scrollContainer ? computeIsAtBottom(ctx.scrollContainer) : true
	ctx.isGenerating = true
	ctx.streamingAssistant = null
	ctx.viewingStreamingBranch = true
	ctx.streamingLeafId = null
	ctx.streamingAssistant = {
		runId: null,
		messageId: `pending-${ctx.activeRun + 1}`,
		content: '',
		timestamp: new SvelteDate(),
		senderAgentId: agentId,
		toolCalls: [],
		isError: false,
		errorMessage: null,
	}
	const runId = ctx.incrementActiveRun()
	ctx.rebuildRunBlocks()
	if (shouldAutoScroll) {
		ctx.autoScroll = true
		void ctx.queueScrollToBottom('smooth')
	}

	const toolChoice = modifiers ? deriveToolChoice(modifiers) : null
	const extraPlugins = modifiers?.extraPlugins ?? []

	try {
		await runThreadStream(
			{
				threadId: thread.id,
				agentId,
				input: runInput,
				runId,
				splice: resolveRunSplice(ctx, ctx.currentLeafId),
				toolChoice,
				extraPlugins,
			},
			ctx
		)
		if (runId !== ctx.activeRun) return
		ctx.optimisticUserMessage = null
		ctx.streamingAssistant = null
		ctx.rebuildRunBlocks()
		syncCacheAfterRun(ctx)
	} catch (e) {
		// intentional abort (e.g. clearThread on navigate-away) - run is over,
		// no error UI needed. backend will broadcast run.completed.
		if (e instanceof DOMException && e.name === 'AbortError') return
		console.error('failed to run thread', e)
		if (runId === ctx.activeRun) {
			// the backend owns the outcome of a run that exists: it persisted
			// whatever streamed and will broadcast that message and its
			// `run.error`. the bridge only has to survive until they land.
			if (runReachedBackend(e, ctx)) {
				markRunBridgeFailed(ctx, runFailureMessage(e))
			} else {
				markRunNotDelivered(ctx)
				showError('your message was not delivered')
			}
		}
		ctx.rebuildRunBlocks()
	} finally {
		if (runId === ctx.activeRun) {
			ctx.toolTracker.closeAllActive()
			ctx.isGenerating = false
		}
	}
}

/** regenerate the agent response from a given parent message.
 * if prompt is provided, it is sent as an additional instruction. */
export async function handleRegenerateMessage(
	parentId: string | null,
	ctx: ChatContext,
	prompt?: string | null,
	/** agent to re-run; defaults to the composer's. a retry must re-run the
	 *  agent that actually failed, which is not always the selected one. */
	agentId?: string | null
): Promise<void> {
	if (!ctx.thread) return
	const runAgentId = agentId || selectedAgent.id
	if (!runAgentId) return
	// where the reader was before the retry moved them off it, so a run that
	// produces nothing can put them back instead of stranding them on a branch
	// with no answer and no way back to the one they had.
	const leafBeforeRetry = ctx.currentLeafId
	ctx.isGenerating = true
	ctx.viewingStreamingBranch = true
	ctx.streamingLeafId = null

	// a retry re-answers an exact message, so its splice must name THAT parent
	// rather than fall back to the current leaf: with no input the splice places
	// the run's own output, and the new answer belongs beside the failed one.
	const resolvedSplice: MessageSplice | undefined =
		parentId && !isPlaceholderMessageId(parentId) && ctx.messageTree.has(parentId)
			? { parent_id: parentId }
			: resolveRunSplice(ctx, parentId ?? ctx.currentLeafId)
	const resolvedParent = resolvedSplice?.parent_id ?? null
	ctx.streamingAssistantParentId = resolvedParent

	// switch view to parent so old response leaves the visible branch
	if (resolvedParent) ctx.currentLeafId = resolvedParent

	ctx.streamingAssistant = {
		runId: null,
		messageId: `pending-${ctx.activeRun + 1}`,
		content: '',
		timestamp: new SvelteDate(),
		senderAgentId: runAgentId,
		toolCalls: [],
		isError: false,
		errorMessage: null,
	}
	const runId = ctx.incrementActiveRun()
	ctx.rebuildRunBlocks()

	try {
		// a regeneration answers an existing message, so it carries no input.
		const regenText = prompt ?? (ctx.optimisticUserMessage ? ctx.lastRunInput : null)

		await runThreadStream(
			{
				threadId: ctx.thread.id,
				agentId: runAgentId,
				input: regenText ? buildRunInput(regenText) : null,
				runId,
				splice: resolvedSplice,
			},
			ctx
		)
		if (runId !== ctx.activeRun) return
		ctx.optimisticUserMessage = null
		ctx.streamingAssistant = null
		ctx.streamingAssistantParentId = null
		ctx.rebuildRunBlocks()
		syncCacheAfterRun(ctx)
	} catch (e) {
		// intentional abort (e.g. clearThread on navigate-away) - run is over.
		if (e instanceof DOMException && e.name === 'AbortError') return
		console.error('failed to retry run', e)
		if (runId === ctx.activeRun) {
			// a retry that produced nothing leaves this branch with no answer on
			// it, so go back to the one it moved off - otherwise the previous
			// answer and its branch switcher stay unreachable until a reload.
			if (leafBeforeRetry && ctx.currentLeafId === resolvedParent) {
				ctx.currentLeafId = leafBeforeRetry
			}
			if (runReachedBackend(e, ctx)) {
				markRunBridgeFailed(ctx, e instanceof Error ? e.message : 'something went wrong')
			} else {
				markRunNotDelivered(ctx)
				showError('the retry was not delivered')
			}
		}
		ctx.rebuildRunBlocks()
	} finally {
		if (runId === ctx.activeRun) {
			ctx.toolTracker.closeAllActive()
			ctx.isGenerating = false
		}
	}
}

/** abort the current generation and reset streaming state */
export async function handleStopGeneration(ctx: ChatContext): Promise<void> {
	// capture run info before resetting state
	const runId = ctx.streamingAssistant?.runId

	ctx.runAbortController?.abort()
	// drop the run from the global store FIRST: the page's resume watcher wakes
	// on isGenerating going false and would re-join a run the user just stopped,
	// replacing the restored action row with a fresh ghost bubble that then
	// fails.
	if (runId) activeRunsStore.forgetRun(runId)
	ctx.activeRun++
	ctx.isGenerating = false
	ctx.viewingStreamingBranch = true
	ctx.optimisticUserMessage = null
	finalizeStreamingAssistantAsPartial(ctx)
	ctx.streamingAssistant = null
	// close any pending/running tool executions directly - incrementing
	// activeRun above causes the finally-block safety net in handleSendMessage/
	// handleRegenerateMessage to skip cleanup, so we must do it here.
	ctx.toolTracker.closeAllActive()
	ctx.rebuildRunBlocks()

	// cancel signal to backend - authenticated request with proper error handling.
	// the SSE stream handles the run-stopped signal; this HTTP call provides
	// the error contract for status codes and potential retry.
	if (runId) {
		try {
			const { error } = await api.POST('/v1/runs/{run_id}/cancel', {
				params: { path: { run_id: runId } },
			})
			if (error) {
				console.error('cancel run failed', error)
			}
		} catch (err) {
			console.error('cancel run request failed', err)
		}
	}
}

/** update a user message's content in place (no regeneration) */
export async function handleSaveEditMessage(
	messageId: string,
	newContent: string,
	ctx: ChatContext
): Promise<void> {
	if (!ctx.thread) return
	const msg = ctx.messages.find((m) => m.id === messageId)
	if (!msg) return

	// the patch carries only what the edit changed: an omitted field is left
	// alone, while a sent `attachments` list replaces every link and the derived
	// access with it. the bubble editor cannot touch attachments, so the key
	// stays omitted until an editor that can appears.
	const body: components['schemas']['MessageUpdate'] = {}
	if (newContent !== contentPartsToText(msg.content).trim()) body.content = newContent
	if (body.content === undefined) return

	const { data: updated, error } = await api.PATCH(
		'/v1/threads/{thread_id}/messages/{message_id}',
		{
			params: { path: { thread_id: ctx.thread.id, message_id: messageId } },
			body,
		}
	)

	if (error || !updated) {
		console.error('failed to update message', error)
		return
	}

	ctx.messageTree.set(updated.id, updated)
	ctx.rebuildRunBlocks()
}

/** create a new branch with edited content and regenerate the response */
export async function handleSaveAsCopyMessage(
	messageId: string,
	newContent: string,
	ctx: ChatContext
): Promise<void> {
	if (!ctx.thread) return
	const msg = ctx.messages.find((m) => m.id === messageId)
	if (!msg) return

	// an edited copy forks at the original's parent, so the splice is explicit.
	const body: components['schemas']['MessageCreate'] = {
		...buildRunInput(newContent),
		splice: { parent_id: msg.parent_id ?? null },
	}

	const { data: newMessage, error } = await postMessageWithBusyRetry(ctx.thread.id, body)

	if (error || !newMessage) {
		console.error('failed to create edited message branch', error)
		showError('could not save the edited message')
		return
	}

	ctx.messageTree.set(newMessage.id, newMessage)
	ctx.currentLeafId = newMessage.id
	ctx.rebuildRunBlocks()

	await handleRegenerateMessage(newMessage.id, ctx)
}

/** opt-in switch offered when confirming a message delete. */
const MESSAGE_ORIGINATED_TOGGLE: ConfirmDeleteToggle = {
	label: 'also delete what was created here',
	description:
		'notes, reminders, files and events created in this turn get deleted too. anything only attached to it is kept.',
}

/** set up the delete confirmation dialog for a user message */
export function requestDeleteUserMessage(messageId: string, ctx: ChatContext): void {
	const msg = ctx.messages.find((m) => m.id === messageId)
	const preview = msg ? contentPartsToText(msg.content).trim().replace(/\s+/g, ' ') : ''
	const quoted = preview.length > 120 ? `${preview.slice(0, 120)}...` : preview
	const target = quoted.length > 0 ? `"${quoted}"` : 'this message'
	modals.open('confirm-delete', {
		title: 'delete message?',
		description: `delete ${target}? this will also delete all replies and branches below it.`,
		toggle: MESSAGE_ORIGINATED_TOGGLE,
		onDelete: (deleteOriginatedResources) =>
			deleteUserMessage(messageId, ctx, { deleteOriginatedResources }),
	})
}

/** delete a user message (local-only for temp chats, API for persisted) */
export async function deleteUserMessage(
	messageId: string,
	ctx: ChatContext,
	options: DeleteOriginatedOptions = {}
): Promise<boolean> {
	if (!ctx.thread) return false
	if (ctx.isTemporaryChat) {
		const start = ctx.messageTree.get(messageId)
		if (!start || start.type !== 'user') return false

		const idsToDelete: string[] = []
		const stack: string[] = [messageId]
		while (stack.length > 0) {
			const id = stack.pop()
			if (!id) continue
			idsToDelete.push(id)
			const kids = ctx.messageChildren.get(id) ?? []
			for (const childId of kids) stack.push(childId)
		}

		for (const id of idsToDelete) ctx.messageTree.delete(id)
		ctx.currentLeafId = resolveLeafAfterDelete(start.parent_id ?? null, ctx)
		ctx.rebuildRunBlocks()
		return true
	}

	// collect all IDs to delete (message + every descendant)
	const start = ctx.messageTree.get(messageId)
	if (!start || start.type !== 'user') return false

	const idsToDelete: string[] = []
	const stack: string[] = [messageId]
	while (stack.length > 0) {
		const id = stack.pop()
		if (!id) continue
		idsToDelete.push(id)
		const kids = ctx.messageChildren.get(id) ?? []
		for (const childId of kids) stack.push(childId)
	}

	// snapshot for rollback
	const snapshotEntries = idsToDelete
		.map((id) => [id, ctx.messageTree.get(id)] as const)
		.filter(([, v]) => v !== undefined)
	const snapshotLeafId = ctx.currentLeafId

	// optimistic removal
	for (const id of idsToDelete) ctx.messageTree.delete(id)
	ctx.currentLeafId = resolveLeafAfterDelete(start.parent_id ?? null, ctx)
	ctx.optimisticUserMessage = null
	ctx.streamingAssistant = null
	ctx.rebuildRunBlocks()

	const { response, error } = await api.DELETE('/v1/threads/{thread_id}/messages/{message_id}', {
		params: {
			path: {
				thread_id: ctx.thread.id,
				message_id: messageId,
			},
			query: options.deleteOriginatedResources
				? { delete_originated_resources: true }
				: undefined,
		},
	})
	if (!response.ok || error) {
		console.error('failed to delete user message', error)
		// rollback
		for (const [id, msg] of snapshotEntries) ctx.messageTree.set(id, msg!)
		ctx.currentLeafId = snapshotLeafId
		ctx.rebuildRunBlocks()
		return false
	}

	return true
}
