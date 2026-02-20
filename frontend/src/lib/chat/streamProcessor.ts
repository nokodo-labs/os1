/**
 * SSE stream processing — processDelta, consumeStream, runThreadStream, resumeCreateAndRun.
 */

import { runChatStream, type ChatStreamDelta, type UnknownSseEvent } from '$lib/api/streaming'
import { notifications } from '$lib/stores/notifications.svelte'
import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
import { hapticFeedback } from '$lib/utils/haptics'
import { SvelteDate } from 'svelte/reactivity'
import { syncCacheAfterRun } from './dataLoader'
import { sdkPartsToText, upsertToolCalls, type ApiMessage } from './helpers'
import type { ChatContext, StreamDeltaContext } from './types'

/**
 * process a single SSE delta event.
 * returns 'done' when the stream should stop, 'continue' otherwise.
 */
export function processDelta(
	delta: ChatStreamDelta,
	sctx: StreamDeltaContext,
	ctx: ChatContext
): 'done' | 'continue' {
	switch (delta.event) {
		case 'error':
			throw new Error(delta.data.message || 'generation failed')
		case 'done':
			return 'done'
		case 'message_created': {
			const msg = delta.data as unknown as ApiMessage
			if (msg.type === 'user') {
				ctx.optimisticUserMessage = null
			}
			ctx.messageTree.set(msg.id, msg)
			ctx.streamingLeafId = msg.id
			if (ctx.viewingStreamingBranch) {
				ctx.currentLeafId = msg.id
			}
			sctx.setAssistantParentId(msg.id)
			ctx.streamingAssistantParentId = msg.id
			return 'continue'
		}
		case 'delta': {
			const env = delta.data
			const d = env.delta as Record<string, unknown>
			const messageId = env.message_id

			// agent done sentinel
			if (d && d.done === true) return 'done'

			// tool results
			if (d && typeof d === 'object' && d.tool) {
				const tool = d.tool as Record<string, unknown>
				const toolCallId = typeof tool.tool_call_id === 'string' ? tool.tool_call_id : null
				const output = typeof tool.tool_output === 'string' ? tool.tool_output : ''
				const isError = tool.is_error === true
				if (toolCallId) {
					ctx.toolTracker.registerResult({ toolCallId, output, isError })
				}

				// add a tool message entry to the tree so the parent chain
				// stays intact when the next assistant message references it
				if (messageId && !ctx.messageTree.has(messageId)) {
					const deltaParent = typeof env.parent_id === 'string' ? env.parent_id : null
					const resolvedParent = deltaParent ?? sctx.getAssistantParentId()
					const now = new SvelteDate().toISOString()
					ctx.messageTree.set(messageId, {
						id: messageId,
						thread_id: sctx.threadId,
						parent_id: resolvedParent,
						type: 'tool',
						content: output ? [{ type: 'text', text: output }] : [],
						tool_calls: [],
						metadata_: toolCallId ? { tool_call_id: toolCallId } : undefined,
						sender_agent_id: null,
						sender_user_id: null,
						created_at: now,
						updated_at: now,
					} satisfies ApiMessage)
					ctx.streamingLeafId = messageId
					if (ctx.viewingStreamingBranch) {
						ctx.currentLeafId = messageId
					}
					sctx.setAssistantParentId(messageId)
					ctx.streamingAssistantParentId = messageId
				}
			}

			// assistant streaming
			if (d && typeof d === 'object' && d.chat && messageId) {
				const chat = d.chat as Record<string, unknown>
				const msg = (chat.message ?? null) as Record<string, unknown> | null
				const parts = msg ? msg.content : null
				const chunkText = sdkPartsToText(parts)
				const toolCalls = msg ? msg.tool_calls : null
				const isDone = chat.done === true

				const isNewStreamingMessage =
					!ctx.streamingAssistant || ctx.streamingAssistant.messageId !== messageId
				if (isNewStreamingMessage) {
					hapticFeedback()
					const runId = typeof env.run_id === 'string' ? env.run_id : null
					ctx.streamingAssistant = {
						runId,
						messageId,
						content: '',
						timestamp: new SvelteDate(),
						senderAgentId: selectedAgent.id,
						toolCalls: [],
						isError: false,
						errorMessage: null,
					}
					if (!ctx.messageTree.has(messageId)) {
						const now = new SvelteDate().toISOString()
						const deltaParent = typeof env.parent_id === 'string' ? env.parent_id : null
						const resolvedParent = deltaParent ?? sctx.getAssistantParentId()
						if (resolvedParent) {
							sctx.setAssistantParentId(resolvedParent)
							ctx.streamingAssistantParentId = resolvedParent
							ctx.currentLeafId = resolvedParent
						}
						ctx.messageTree.set(messageId, {
							id: messageId,
							thread_id: sctx.threadId,
							parent_id: resolvedParent,
							type: 'assistant',
							content: [],
							tool_calls: [],
							metadata_: runId ? { run_id: runId } : undefined,
							sender_agent_id: selectedAgent.id,
							sender_user_id: null,
							created_at: now,
							updated_at: now,
						} satisfies ApiMessage)
					}
					ctx.streamingLeafId = messageId
					// keep currentLeafId pointing to the streaming message so
					// the messages derived includes the entire branch
					if (ctx.viewingStreamingBranch) {
						ctx.currentLeafId = messageId
					}
				}
				const streaming = ctx.streamingAssistant
				if (!streaming) return 'continue'

				if (chunkText) streaming.content += chunkText

				let toolCallsChanged = false
				if (Array.isArray(toolCalls)) {
					const prev = streaming.toolCalls
					const next = upsertToolCalls(prev, toolCalls)
					toolCallsChanged =
						next.length !== prev.length || next.some((tc, i) => tc.id !== prev[i]?.id)
					streaming.toolCalls = next
					// register each tool call — the reactive tracker handles dedup + accumulation
					for (const tc of next) ctx.toolTracker.registerToolCall(tc)
				}

				if (isNewStreamingMessage || toolCallsChanged) {
					ctx.rebuildRunBlocks()
				}

				if (isDone) {
					const content = streaming.content.trim()
					const now = new SvelteDate().toISOString()
					const deltaParent = typeof env.parent_id === 'string' ? env.parent_id : null
					const resolvedParent = deltaParent ?? sctx.getAssistantParentId()
					const finalized = {
						id: streaming.messageId,
						thread_id: sctx.threadId,
						parent_id: resolvedParent,
						type: 'assistant',
						content: content ? [{ type: 'text', text: content }] : [],
						tool_calls: streaming.toolCalls.map((tc) => ({
							id: tc.id,
							name: tc.name,
							arguments: tc.arguments,
						})),
						metadata_: streaming.runId ? { run_id: streaming.runId } : undefined,
						sender_agent_id: streaming.senderAgentId,
						sender_user_id: null,
						created_at: now,
						updated_at: now,
					} satisfies ApiMessage
					ctx.messageTree.set(finalized.id, finalized)
					ctx.streamingLeafId = finalized.id
					if (ctx.viewingStreamingBranch) {
						ctx.currentLeafId = finalized.id
					}
					const parentId = finalized.id
					sctx.setAssistantParentId(parentId)
					ctx.streamingAssistantParentId = parentId

					if (streaming.toolCalls.length > 0) {
						ctx.streamingAssistant = {
							runId: streaming.runId,
							messageId: `pending-next-${sctx.runId}`,
							content: '',
							timestamp: new SvelteDate(),
							senderAgentId: streaming.senderAgentId,
							toolCalls: [],
							isError: false,
							errorMessage: null,
						}
					} else {
						ctx.streamingAssistant = null
					}
					ctx.rebuildRunBlocks()
				}
			}
			return 'continue'
		}
		case 'unknown': {
			// future-proofing: log and show transient banner for unrecognized events
			const unknownData = delta.data as UnknownSseEvent
			console.warn(`unknown SSE event: ${unknownData.eventType}`, unknownData.rawData)
			notifications.toasts = [
				...notifications.toasts,
				{
					id: `unknown-sse-${Date.now()}`,
					title: 'unknown event',
					body: `received unrecognized event: ${unknownData.eventType}`,
					iconUrl: null,
					addedAt: Date.now(),
				},
			]
			return 'continue'
		}
		default:
			return 'continue'
	}
}

/**
 * consume any async generator of chat deltas, processing each through the
 * standard processDelta pipeline. decoupled from the HTTP transport so it
 * can be fed a generator from runChatStream, runCreateAndRunStream, or
 * any other source.
 */
export async function consumeStream(
	stream: AsyncGenerator<ChatStreamDelta, void, unknown>,
	opts: { runId: number; threadId: string; parentId: string | null },
	ctx: ChatContext
): Promise<void> {
	let assistantParentId = opts.parentId
	ctx.streamingAssistantParentId = assistantParentId

	const sctx: StreamDeltaContext = {
		runId: opts.runId,
		threadId: opts.threadId,
		getAssistantParentId: () => assistantParentId,
		setAssistantParentId: (id: string | null) => {
			assistantParentId = id
		},
	}

	for await (const delta of stream) {
		if (opts.runId !== ctx.activeRun) {
			ctx.runAbortController?.abort()
			return
		}

		const result = processDelta(delta, sctx, ctx)
		if (result === 'done') return
	}
}

/** run a chat stream for an existing thread */
export async function runThreadStream(
	opts: {
		threadId: string
		agentId: string
		input: string | null
		runId: number
		parentId?: string | null
	},
	ctx: ChatContext
): Promise<void> {
	ctx.runAbortController?.abort()
	ctx.runAbortController = new AbortController()

	const parentId = opts.parentId ?? ctx.currentLeafId

	// when retrying, switch view to parent so new response replaces old branch
	if (!opts.input) {
		if (parentId) ctx.currentLeafId = parentId
		else ctx.currentLeafId = null
	}

	const stream = runChatStream({
		threadId: opts.threadId,
		agentId: opts.agentId,
		input: opts.input,
		parentId,
		signal: ctx.runAbortController.signal,
	})

	await consumeStream(stream, { runId: opts.runId, threadId: opts.threadId, parentId }, ctx)
}

/**
 * resume a create_and_run stream that was started on another page.
 * the generator has already yielded `thread_created` — this consumes
 * the remaining run deltas (message_created, delta, done, etc).
 */
export async function resumeCreateAndRun(
	stream: AsyncGenerator<ChatStreamDelta, void, unknown>,
	threadId: string,
	ctx: ChatContext
): Promise<void> {
	ctx.runAbortController?.abort()
	ctx.runAbortController = new AbortController()

	const runId = ctx.incrementActiveRun()
	ctx.isGenerating = true
	ctx.viewingStreamingBranch = true
	ctx.streamingLeafId = null
	ctx.streamingAssistant = {
		runId: null,
		messageId: `pending-${runId}`,
		content: '',
		timestamp: new SvelteDate(),
		senderAgentId: selectedAgent.id,
		toolCalls: [],
		isError: false,
		errorMessage: null,
	}
	ctx.rebuildRunBlocks()

	try {
		await consumeStream(stream, { runId, threadId, parentId: ctx.currentLeafId }, ctx)
		if (runId !== ctx.activeRun) return
		ctx.optimisticUserMessage = null
		ctx.streamingAssistant = null
		ctx.rebuildRunBlocks()
		syncCacheAfterRun(ctx)
	} catch (e) {
		console.error('failed to resume create_and_run stream', e)
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
