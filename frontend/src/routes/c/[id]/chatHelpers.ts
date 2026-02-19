/**
 * Pure utility functions for chat page - no reactive state, no side effects.
 */

import type { components } from '$lib/api/types'
import { parseToolCalls, parseToolResult, type ToolCall, type ToolResult } from '$lib/tools'

export type ApiMessage = components['schemas']['Message']

// ─────────────────────────────────────────────────────────────────────────────
// types
// ─────────────────────────────────────────────────────────────────────────────

export type RunItem =
	| { kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
	| { kind: 'optimistic_user'; content: string; timestamp: Date }
	| { kind: 'assistant'; message: ApiMessage }
	| { kind: 'tool'; toolCallId: string }
	| { kind: 'streaming_assistant' }
	| { kind: 'streaming_tool'; toolCallId: string }

export interface RunBlock {
	runId: string
	title: string
	startedAt: Date
	items: RunItem[]
	responseRootId: string | null
}

export interface StreamingAssistantState {
	runId: string | null
	messageId: string
	content: string
	timestamp: Date
	senderAgentId: string | null
	toolCalls: ToolCall[]
	isError: boolean
	errorMessage: string | null
}

// ─────────────────────────────────────────────────────────────────────────────
// message helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Convert message content parts to plain text.
 */
export function contentPartsToText(parts: ApiMessage['content']): string {
	if (!parts || parts.length === 0) return ''
	return parts
		.map((part): string | null => {
			if (!part) return null
			if (part.type === 'text') {
				return 'text' in part && typeof part.text === 'string' ? part.text : null
			}
			if (part.type === 'refusal') {
				return 'reason' in part && typeof part.reason === 'string' ? part.reason : null
			}
			if (part.type === 'json') {
				try {
					return 'data' in part ? JSON.stringify(part.data) : ''
				} catch {
					return null
				}
			}
			return null
		})
		.filter((v): v is string => v !== null)
		.join('\n')
}

/**
 * Convert SDK message parts to plain text (used during streaming).
 */
export function sdkPartsToText(parts: unknown): string {
	if (!Array.isArray(parts)) return ''
	return parts
		.map((p): string | null => {
			if (!p || typeof p !== 'object') return null
			const part = p as Record<string, unknown>
			const type = typeof part.type === 'string' ? part.type : ''
			if (type === 'text' && typeof part.text === 'string') return part.text
			if (type === 'refusal' && typeof part.reason === 'string') return part.reason
			if (type === 'json' && part.data != null) {
				try {
					return JSON.stringify(part.data)
				} catch {
					return null
				}
			}
			return null
		})
		.filter((v): v is string => v !== null)
		.join('\n')
}

/**
 * Extract run_id from message metadata, or generate a legacy fallback.
 */
export function getRunId(msg: Pick<ApiMessage, 'metadata_' | 'id'>): string {
	const runId =
		msg.metadata_ && typeof msg.metadata_.run_id === 'string' ? msg.metadata_.run_id : null
	return runId ?? `legacy-${msg.id}`
}

/**
 * Parse message created_at to Date.
 */
export function getMessageCreatedAt(msg: ApiMessage): Date {
	return msg.created_at ? new Date(msg.created_at) : new Date(0)
}

/**
 * Buffer distance for auto-scroll detection.
 */
export const AUTO_SCROLL_BUFFER_PX = 50

/**
 * Check if scroll container is at bottom (within buffer).
 */
export function computeIsAtBottom(element: HTMLElement): boolean {
	return element.scrollHeight - element.scrollTop <= element.clientHeight + AUTO_SCROLL_BUFFER_PX
}

// ─────────────────────────────────────────────────────────────────────────────
// tool call helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * merge incoming tool call data into the existing list, creating or updating
 * entries by id. pure function — no reactive state.
 */
export function upsertToolCalls(existing: ToolCall[], incoming: unknown): ToolCall[] {
	const out = new Map(existing.map((tc) => [tc.id, tc]))
	if (!Array.isArray(incoming)) return Array.from(out.values())
	for (const item of incoming) {
		if (!item || typeof item !== 'object') continue
		const tc = item as Record<string, unknown>
		const id = typeof tc.id === 'string' ? tc.id : null
		const name = typeof tc.name === 'string' ? tc.name : null
		const args =
			tc.arguments && typeof tc.arguments === 'object' && tc.arguments !== null
				? (tc.arguments as Record<string, unknown>)
				: {}
		if (!id || !name) continue
		out.set(id, { id, name, arguments: args })
	}
	return Array.from(out.values())
}

// ─────────────────────────────────────────────────────────────────────────────
// message children map
// ─────────────────────────────────────────────────────────────────────────────

/**
 * build a parent_id → child_id[] map from a message iterable.
 * children are sorted by created_at.
 */
export function buildMessageChildren(messages: Iterable<ApiMessage>): Map<string | null, string[]> {
	const map = new Map<string | null, string[]>()
	const lookup = new Map<string, ApiMessage>()
	for (const msg of messages) {
		lookup.set(msg.id, msg)
		const pid = msg.parent_id ?? null
		const existing = map.get(pid) ?? []
		existing.push(msg.id)
		map.set(pid, existing)
	}
	for (const [, kids] of map) {
		kids.sort((a, b) => {
			const ma = lookup.get(a)
			const mb = lookup.get(b)
			if (!ma || !mb) return 0
			return getMessageCreatedAt(ma).getTime() - getMessageCreatedAt(mb).getTime()
		})
	}
	return map
}

// ─────────────────────────────────────────────────────────────────────────────
// run block building
// ─────────────────────────────────────────────────────────────────────────────

export interface BuildRunBlocksInput {
	messages: ApiMessage[]
	userId: string | null
	streamingAssistant: StreamingAssistantState | null
	optimisticUserMessage: { content: string; timestamp: Date } | null
	viewingStreamingBranch: boolean
}

export interface BuildRunBlocksResult {
	blocks: RunBlock[]
	/** tool calls encountered during block building (caller should register them) */
	toolCalls: ToolCall[]
	/** tool results encountered during block building (caller should register them) */
	toolResults: ToolResult[]
}

/**
 * build run blocks from messages + streaming state.
 * pure function — no reactive state or side effects.
 */
export function buildRunBlocks(input: BuildRunBlocksInput): BuildRunBlocksResult {
	const { messages, userId, streamingAssistant, optimisticUserMessage, viewingStreamingBranch } =
		input

	const sorted = messages.slice().sort((a, b) => {
		return getMessageCreatedAt(a).getTime() - getMessageCreatedAt(b).getTime()
	})

	const blocks: RunBlock[] = []
	const byRun = new Map<string, RunBlock>()
	const seenToolCalls = new Map<string, Set<string>>()
	const collectedToolCalls: ToolCall[] = []
	const collectedToolResults: ToolResult[] = []

	const ensureBlock = (runId: string, startedAt: Date, title: string): RunBlock => {
		const existing = byRun.get(runId)
		if (existing) return existing
		const block: RunBlock = {
			runId,
			startedAt,
			title,
			items: [],
			responseRootId: null,
		}
		byRun.set(runId, block)
		blocks.push(block)
		return block
	}

	for (const msg of sorted) {
		if (streamingAssistant && msg.id === streamingAssistant.messageId) continue

		const runId = getRunId(msg)
		const block = ensureBlock(runId, getMessageCreatedAt(msg), 'assistant')
		let seen = seenToolCalls.get(runId)
		if (!seen) {
			seen = new Set()
			seenToolCalls.set(runId, seen)
		}

		if (msg.type === 'user') {
			const align: 'left' | 'right' =
				userId && msg.sender_user_id && msg.sender_user_id !== userId ? 'left' : 'right'
			block.items.push({ kind: 'user', message: msg, align })
			continue
		}

		if (block.responseRootId === null) {
			block.responseRootId = msg.id
		}

		if (msg.type === 'assistant') {
			const text = contentPartsToText(msg.content).trim()
			if (text.length > 0) block.items.push({ kind: 'assistant', message: msg })
			for (const tc of parseToolCalls(msg)) {
				collectedToolCalls.push(tc)
				if (!seen.has(tc.id)) {
					seen.add(tc.id)
					block.items.push({ kind: 'tool', toolCallId: tc.id })
				}
			}
			continue
		}

		if (msg.type === 'tool') {
			const result = parseToolResult(msg)
			if (result) collectedToolResults.push(result)
			continue
		}
	}

	if (streamingAssistant && viewingStreamingBranch) {
		const runId = streamingAssistant.runId ?? `legacy-${streamingAssistant.messageId}`
		const block = ensureBlock(runId, streamingAssistant.timestamp, 'assistant')

		if (optimisticUserMessage) {
			block.items.push({
				kind: 'optimistic_user',
				content: optimisticUserMessage.content,
				timestamp: optimisticUserMessage.timestamp,
			})
		}

		if (block.responseRootId === null) {
			block.responseRootId = streamingAssistant.messageId
		}

		let seen = seenToolCalls.get(runId)
		if (!seen) {
			seen = new Set()
			seenToolCalls.set(runId, seen)
		}
		block.items.push({ kind: 'streaming_assistant' })
		for (const tc of streamingAssistant.toolCalls) {
			collectedToolCalls.push(tc)
			if (!seen.has(tc.id)) {
				seen.add(tc.id)
				block.items.push({ kind: 'streaming_tool', toolCallId: tc.id })
			}
		}
	} else if (optimisticUserMessage && viewingStreamingBranch) {
		const runId = `pending-user-${optimisticUserMessage.timestamp.getTime()}`
		const block = ensureBlock(runId, optimisticUserMessage.timestamp, 'pending')
		block.items.push({
			kind: 'optimistic_user',
			content: optimisticUserMessage.content,
			timestamp: optimisticUserMessage.timestamp,
		})
	}

	return { blocks, toolCalls: collectedToolCalls, toolResults: collectedToolResults }
}

// ─────────────────────────────────────────────────────────────────────────────
// run block queries
// ─────────────────────────────────────────────────────────────────────────────

export function getBlockResponseItems(
	block: RunBlock
): Array<
	| { kind: 'assistant'; message: ApiMessage }
	| { kind: 'tool'; toolCallId: string }
	| { kind: 'streaming_assistant' }
	| { kind: 'streaming_tool'; toolCallId: string }
> {
	return block.items.filter(
		(
			item
		): item is Exclude<
			RunItem,
			| { kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
			| { kind: 'optimistic_user'; content: string; timestamp: Date }
		> => item.kind !== 'user' && item.kind !== 'optimistic_user'
	)
}

export function getBlockFirstAssistant(block: RunBlock): ApiMessage | null {
	const item = block.items.find((i) => i.kind === 'assistant')
	return item?.kind === 'assistant' ? item.message : null
}

export function blockHasStreamingAssistant(block: RunBlock): boolean {
	return block.items.some((item) => item.kind === 'streaming_assistant')
}

// ─────────────────────────────────────────────────────────────────────────────
// agent lookups
// ─────────────────────────────────────────────────────────────────────────────

/**
 * build a lookup map from agent id to a derived value.
 */
export function buildAgentLookup<A extends { id: string }, T>(
	list: A[],
	selector: (agent: A) => T
): Map<string, T> {
	return new Map(list.map((a) => [a.id, selector(a)]))
}
