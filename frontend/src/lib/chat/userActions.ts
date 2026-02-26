/**
 * user-initiated chat actions - send, regenerate, stop, edit, delete.
 */

import { apiClient } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
import { SvelteDate } from 'svelte/reactivity'
import { syncCacheAfterRun } from './dataLoader'
import { computeIsAtBottom, contentPartsToText } from './helpers'
import { runThreadStream } from './streamProcessor'
import type { ChatContext } from './types'

/** send a new user message and stream the agent response */
export async function handleSendMessage(content: string, ctx: ChatContext): Promise<void> {
	const trimmed = content.trim()
	if (!trimmed) return
	if (!ctx.thread) return
	const runBaseMessage = trimmed
	if (!selectedAgent) {
		ctx.lastRunInput = runBaseMessage
		ctx.optimisticUserMessage = { content: runBaseMessage, timestamp: new SvelteDate() }
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
	ctx.lastRunInput = runBaseMessage
	ctx.inputValue = ''
	ctx.optimisticUserMessage = { content: runBaseMessage, timestamp: new SvelteDate() }
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

	try {
		await runThreadStream(
			{
				threadId: ctx.thread.id,
				agentId: selectedAgent.id,
				input: runBaseMessage,
				runId,
				parentId: ctx.currentLeafId,
			},
			ctx
		)
		if (runId !== ctx.activeRun) return
		ctx.optimisticUserMessage = null
		ctx.streamingAssistant = null
		ctx.rebuildRunBlocks()
		syncCacheAfterRun(ctx)
	} catch (e) {
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
		if (runId === ctx.activeRun) ctx.isGenerating = false
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

	const resolvedParent = parentId ?? ctx.currentLeafId
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
		await runThreadStream(
			{
				threadId: ctx.thread.id,
				agentId: selectedAgent.id,
				input: prompt ?? (ctx.optimisticUserMessage ? ctx.lastRunInput : null),
				runId,
				parentId: resolvedParent,
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
		if (runId === ctx.activeRun) ctx.isGenerating = false
	}
}

/** abort the current generation and reset streaming state */
export async function handleStopGeneration(ctx: ChatContext): Promise<void> {
	// capture run info before resetting state
	const runId = ctx.streamingAssistant?.runId
	const threadId = ctx.thread?.id

	ctx.runAbortController?.abort()
	ctx.activeRun++
	ctx.isGenerating = false
	ctx.viewingStreamingBranch = true
	ctx.streamingLeafId = null
	ctx.optimisticUserMessage = null
	ctx.streamingAssistant = null
	ctx.streamingAssistantParentId = null
	ctx.rebuildRunBlocks()

	// cancel signal to backend - authenticated request with proper error handling.
	// the SSE stream handles the run-stopped signal; this HTTP call provides
	// the error contract for status codes and potential retry.
	if (runId && threadId) {
		try {
			const { error } = await apiClient().POST(
				'/v1/threads/{thread_id}/runs/{run_id}/cancel',
				{
					params: { path: { thread_id: threadId, run_id: runId } },
				}
			)
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

	const { data: updated, error } = await apiClient().PATCH(
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

	const { data: newMessage, error } = await apiClient().POST('/v1/threads/{thread_id}/messages', {
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
	const preview = msg ? contentPartsToText(msg.content).trim() : ''
	ctx.confirmDeleteMessage = {
		id: messageId,
		preview: preview.length > 0 ? preview : 'this message',
	}
	ctx.deleteMessageError = null
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
		ctx.currentLeafId = start.parent_id ?? null
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
	ctx.currentLeafId = start.parent_id ?? null
	ctx.optimisticUserMessage = null
	ctx.streamingAssistant = null
	ctx.rebuildRunBlocks()

	const { response, error } = await apiClient().DELETE(
		'/v1/threads/{thread_id}/messages/{message_id}',
		{
			params: {
				path: {
					thread_id: ctx.thread.id,
					message_id: messageId,
				},
			},
		}
	)
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
