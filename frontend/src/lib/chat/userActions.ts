/**
 * user-initiated chat actions - send, regenerate, stop, edit, delete.
 */

import { api } from '$lib/api/client'
import type { RunInput } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { deriveToolChoice, type RunModifiers } from '$lib/chat/attachments'
import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { agents } from '$lib/stores/agents.svelte'
import { modals } from '$lib/stores/modals.svelte'
import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
import { SvelteDate } from 'svelte/reactivity'
import { syncCacheAfterRun } from './dataLoader'
import { computeIsAtBottom, contentPartsToText } from './helpers'
import { runThreadStream } from './streamProcessor'
import { getLatestLeaf } from './treeNavigation'
import type { ChatContext, PendingRunInput } from './types'

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
		text: input.text ?? null,
		attachment_ids: input.attachment_ids ? [...input.attachment_ids] : undefined,
		attachment_actions: input.attachment_actions ? { ...input.attachment_actions } : undefined,
	}
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

function resolveRunParentId(ctx: ChatContext, preferredParentId: string | null): string | null {
	const candidates = [
		preferredParentId,
		ctx.streamingAssistantParentId,
		ctx.thread?.current_message_id ?? null,
	]
	for (const candidate of candidates) {
		if (!candidate) continue
		if (candidate === ctx.streamingLeafId) continue
		if (candidate === ctx.streamingAssistant?.messageId) continue
		if (ctx.messageTree.has(candidate)) return candidate
	}
	return null
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

	const runInput: RunInput = { text: trimmed || null }
	if (hasAttachments) {
		runInput.attachment_ids = modifiers.attachments.map((a) => a.fileId)
	}

	// include user attachment actions (reveals/references)
	if (ctx.pendingActions.size > 0) {
		runInput.attachment_actions = Object.fromEntries(ctx.pendingActions)
	}

	const displayText = trimmed || modifiers?.attachments.map((a) => a.filename).join(', ') || ''

	// steering: queued messages stay outside the thread until the backend
	// broadcasts that the running agent has injected them.
	const hasLocalRunInProgress = ctx.isGenerating || ctx.streamingAssistant !== null
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

	if (!selectedAgent) {
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
		senderAgentId: selectedAgent.id,
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

	try {
		await runThreadStream(
			{
				threadId: ctx.thread.id,
				agentId: selectedAgent.id,
				input: runInput,
				runId,
				parentId: resolveRunParentId(ctx, ctx.currentLeafId),
				toolChoice,
			},
			ctx
		)
		if (runId !== ctx.activeRun) return
		ctx.optimisticUserMessage = null
		ctx.streamingAssistant = null
		// clear pending actions - they've been persisted as events by the backend
		ctx.pendingActions.clear()
		ctx.rebuildRunBlocks()
		syncCacheAfterRun(ctx)
	} catch (e) {
		// intentional abort (e.g. clearThread on navigate-away) - run is over,
		// no error UI needed. backend will broadcast run.completed.
		if (e instanceof DOMException && e.name === 'AbortError') return
		console.error('failed to run thread', e)
		if (runId === ctx.activeRun && ctx.streamingAssistant) {
			ctx.streamingAssistant = {
				...ctx.streamingAssistant,
				isError: true,
				errorMessage: e instanceof Error ? e.message : 'something went wrong',
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
	prompt?: string | null
): Promise<void> {
	if (!ctx.thread) return
	if (!selectedAgent.id) return
	ctx.isGenerating = true
	ctx.viewingStreamingBranch = true
	ctx.streamingLeafId = null

	const resolvedParent = resolveRunParentId(ctx, parentId ?? ctx.currentLeafId)
	ctx.streamingAssistantParentId = resolvedParent

	// switch view to parent so old response leaves the visible branch
	if (resolvedParent) ctx.currentLeafId = resolvedParent

	ctx.streamingAssistant = {
		runId: null,
		messageId: `pending-${ctx.activeRun + 1}`,
		content: '',
		timestamp: new SvelteDate(),
		senderAgentId: selectedAgent.id,
		toolCalls: [],
		isError: false,
		errorMessage: null,
	}
	const runId = ctx.incrementActiveRun()
	ctx.rebuildRunBlocks()

	try {
		const regenInput: RunInput = prompt
			? { text: prompt }
			: ctx.optimisticUserMessage
				? { text: ctx.lastRunInput }
				: {}

		// include pending attachment actions with the regeneration
		if (ctx.pendingActions.size > 0) {
			regenInput.attachment_actions = Object.fromEntries(ctx.pendingActions)
		}

		await runThreadStream(
			{
				threadId: ctx.thread.id,
				agentId: selectedAgent.id,
				input: Object.keys(regenInput).length > 0 ? regenInput : null,
				runId,
				parentId: resolvedParent,
			},
			ctx
		)
		if (runId !== ctx.activeRun) return
		ctx.optimisticUserMessage = null
		ctx.streamingAssistant = null
		ctx.streamingAssistantParentId = null
		ctx.pendingActions.clear()
		ctx.rebuildRunBlocks()
		syncCacheAfterRun(ctx)
	} catch (e) {
		// intentional abort (e.g. clearThread on navigate-away) - run is over.
		if (e instanceof DOMException && e.name === 'AbortError') return
		console.error('failed to retry run', e)
		if (runId === ctx.activeRun && ctx.streamingAssistant) {
			ctx.streamingAssistant = {
				...ctx.streamingAssistant,
				isError: true,
				errorMessage: e instanceof Error ? e.message : 'something went wrong',
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
	ctx.activeRun++
	ctx.isGenerating = false
	ctx.viewingStreamingBranch = true
	ctx.streamingLeafId = null
	ctx.optimisticUserMessage = null
	ctx.streamingAssistant = null
	ctx.streamingAssistantParentId = null
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

	const { data: updated, error } = await api.PATCH(
		'/v1/threads/{thread_id}/messages/{message_id}',
		{
			params: { path: { thread_id: ctx.thread.id, message_id: messageId } },
			body: { content: newContent },
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

	const body = {
		content: newContent,
		type: 'user',
		parent_id: msg.parent_id ?? null,
	} satisfies components['schemas']['MessageCreate']

	const { data: newMessage, error } = await api.POST('/v1/threads/{thread_id}/messages', {
		params: { path: { thread_id: ctx.thread.id } },
		body,
	})

	if (error || !newMessage) {
		console.error('failed to create edited message branch', error)
		return
	}

	ctx.messageTree.set(newMessage.id, newMessage)
	ctx.currentLeafId = newMessage.id
	ctx.rebuildRunBlocks()

	await handleRegenerateMessage(newMessage.id, ctx)
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
		onDelete: () => deleteUserMessage(messageId, ctx),
	})
}

/** delete a user message (local-only for temp chats, API for persisted) */
export async function deleteUserMessage(messageId: string, ctx: ChatContext): Promise<boolean> {
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
