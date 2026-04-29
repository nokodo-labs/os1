/**
 * pure utility functions for chat - no reactive state, no side effects.
 * types are defined in $lib/chat/types.ts, not here.
 */

import { parseToolCalls, parseToolResult, type ToolCall, type ToolResult } from '$lib/tools'
import type {
	ApiCitation,
	ApiMessage,
	AttachmentMediaCategory,
	AttachmentStatus,
	FileContentPart,
	MediaContentPart,
	OptimisticUserMessage,
	PendingAttachment,
	RunBlock,
	RunItem,
	StreamingAssistantState,
	ThreadAttachment,
} from './types'

export type {
	ApiMessage,
	FileContentPart,
	MediaContentPart,
	RunBlock,
	RunItem,
	StreamingAssistantState,
}

// message helpers

/**
 * convert message content parts to plain text.
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

// content part extraction

/**
 * extract renderable media parts (image/audio/video) from message content.
 * resolves file_id to a download URL when no direct url is present.
 */
export function extractMediaParts(
	parts: ApiMessage['content'],
	apiBaseUrl?: string
): MediaContentPart[] {
	if (!parts || parts.length === 0) return []
	const results: MediaContentPart[] = []
	for (const part of parts) {
		if (!part) continue
		if (part.type === 'image') {
			const fileId = part.metadata?.file_id as string | undefined
			const mediaType = part.media_type ?? 'image/png'
			const url =
				(fileId && apiBaseUrl ? `${apiBaseUrl}/v1/files/${fileId}/content` : undefined) ??
				part.url ??
				(part.base64 ? `data:${mediaType};base64,${part.base64}` : undefined)
			if (url) {
				results.push({
					type: 'image',
					url,
					filename: part.filename,
					mediaType: part.media_type,
					fileId,
					attachmentStatus: part.metadata?.attachment_status as string | undefined,
				})
			}
		} else if (part.type === 'file') {
			const mime = part.media_type ?? ''
			const isMedia = mime.startsWith('audio/') || mime.startsWith('video/')
			if (isMedia) {
				const fileId = part.metadata?.file_id as string | undefined
				const url =
					part.url ??
					(fileId && apiBaseUrl ? `${apiBaseUrl}/v1/files/${fileId}/content` : undefined)
				if (url) {
					results.push({
						type: mime.startsWith('audio/') ? 'audio' : 'video',
						url,
						filename: part.filename,
						mediaType: part.media_type,
						fileId,
						attachmentStatus: part.metadata?.attachment_status as string | undefined,
					})
				}
			}
		}
	}
	return results
}

/**
 * extract non-media file parts from message content.
 */
export function extractFileParts(
	parts: ApiMessage['content'],
	apiBaseUrl?: string
): FileContentPart[] {
	if (!parts || parts.length === 0) return []
	const results: FileContentPart[] = []
	for (const part of parts) {
		if (!part) continue
		if (part.type !== 'file') continue
		const mime = part.media_type ?? ''
		if (mime.startsWith('audio/') || mime.startsWith('video/')) continue
		const fileId = part.metadata?.file_id as string | undefined
		const url =
			part.url ??
			(fileId && apiBaseUrl ? `${apiBaseUrl}/v1/files/${fileId}/content` : undefined)
		results.push({
			type: 'file',
			url,
			filename: part.filename,
			mediaType: part.media_type,
			fileId,
			attachmentStatus: part.metadata?.attachment_status as string | undefined,
		})
	}
	return results
}

/**
 * check if a message has any media or file content parts (beyond text).
 */
export function hasAttachmentParts(parts: ApiMessage['content']): boolean {
	if (!parts || parts.length === 0) return false
	return parts.some((p) => p && (p.type === 'image' || p.type === 'file'))
}

function classifyMediaCategory(mime: string | null | undefined): AttachmentMediaCategory {
	if (!mime) return 'file'
	const lower = mime.toLowerCase()
	if (lower.startsWith('image/')) return 'image'
	if (lower.startsWith('audio/')) return 'audio'
	if (lower.startsWith('video/')) return 'video'
	return 'file'
}

/**
 * derive all unique file attachments from the current message branch
 * with status determined from the event-derived state map.
 *
 * attachmentStates is populated from backend events (attachment.decayed,
 * attachment.revealed) so the frontend displays authoritative state
 * rather than guessing decay client-side.
 *
 * attachments without an entry in attachmentStates default to 'active'
 * (newly uploaded files before the first run).
 */
export function computeThreadAttachments(
	messages: ApiMessage[],
	attachmentStates?: Map<string, AttachmentStatus>
): ThreadAttachment[] {
	// compute turn indices (same logic as backend _compute_turn_indices)
	const turnIndices: number[] = []
	let currentTurn = 0
	let sawUserInTurn = false

	for (const msg of messages) {
		if (msg.type === 'system') {
			turnIndices.push(currentTurn)
			continue
		}
		if (msg.type === 'user') {
			sawUserInTurn = true
			turnIndices.push(currentTurn)
			continue
		}
		if (msg.type === 'assistant') {
			turnIndices.push(currentTurn)
			if (sawUserInTurn) {
				currentTurn++
				sawUserInTurn = false
			}
			continue
		}
		// tool or unknown
		turnIndices.push(currentTurn)
	}

	// collect unique attachments (earliest occurrence)
	const seen = new Map<string, ThreadAttachment>()

	for (let i = 0; i < messages.length; i++) {
		const msg = messages[i]
		if (!msg.content) continue

		for (const part of msg.content) {
			if (!part || (part.type !== 'image' && part.type !== 'file')) continue
			const fileId = (part.metadata as Record<string, unknown> | undefined)?.file_id
			if (!fileId || typeof fileId !== 'string') continue
			if (seen.has(fileId)) continue

			const mime = part.media_type ?? null
			const category = classifyMediaCategory(mime)
			const turn = turnIndices[i] ?? 0

			// use event-derived state if available, else default to active
			const status = attachmentStates?.get(fileId) ?? 'active'

			seen.set(fileId, {
				fileId,
				filename: part.filename ?? null,
				mediaType: mime,
				category,
				status,
				turn,
			})
		}
	}

	return [...seen.values()]
}

/**
 * convert SDK message parts to plain text (used during streaming).
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
 * extract run_id from message metadata, or generate a legacy fallback.
 */
export function getRunId(msg: Pick<ApiMessage, 'metadata_' | 'id'>): string {
	const runId =
		msg.metadata_ && typeof msg.metadata_.run_id === 'string' ? msg.metadata_.run_id : null
	return runId ?? `legacy-${msg.id}`
}

/**
 * extract the agent id that produced a response message, if known.
 */
export function getMessageAgentId(
	msg: Pick<ApiMessage, 'sender_agent_id' | 'metadata_'>
): string | null {
	if (typeof msg.sender_agent_id === 'string' && msg.sender_agent_id) return msg.sender_agent_id
	return msg.metadata_ && typeof msg.metadata_.agent_id === 'string'
		? msg.metadata_.agent_id
		: null
}

/**
 * parse message created_at to Date.
 */
export function getMessageCreatedAt(msg: ApiMessage): Date {
	return msg.created_at ? new Date(msg.created_at) : new Date(0)
}

/**
 * buffer distance for auto-scroll detection.
 */
export const AUTO_SCROLL_BUFFER_PX = 5

/**
 * check if scroll container is at bottom (within buffer).
 */
export function computeIsAtBottom(element: HTMLElement): boolean {
	return element.scrollHeight - element.scrollTop <= element.clientHeight + AUTO_SCROLL_BUFFER_PX
}

// tool call helpers

/**
 * merge incoming tool call data into the existing list, creating or updating
 * entries by id. handles both object and string arguments from streaming.
 * string arguments are accumulated (appended) across chunks.
 * pure function - no reactive state.
 */
export function upsertToolCalls(existing: ToolCall[], incoming: unknown): ToolCall[] {
	const out = new Map(existing.map((tc) => [tc.id, tc]))
	if (!Array.isArray(incoming)) return Array.from(out.values())
	for (const item of incoming) {
		if (!item || typeof item !== 'object') continue
		const tc = item as Record<string, unknown>
		const id = typeof tc.id === 'string' ? tc.id : null
		const name = typeof tc.name === 'string' ? tc.name : null
		// skip only if both name is missing AND we haven't seen this ID before
		if (!id || (!name && !out.has(id))) continue

		const prev = out.get(id)
		const rawArgs = tc.arguments

		let args: Record<string, unknown> | string
		if (typeof rawArgs === 'string') {
			// streaming string fragment - accumulate with previous
			const prevStr = prev ? (typeof prev.arguments === 'string' ? prev.arguments : '') : ''
			args = prevStr + rawArgs
		} else if (rawArgs && typeof rawArgs === 'object' && rawArgs !== null) {
			args = rawArgs as Record<string, unknown>
		} else {
			args = prev?.arguments ?? {}
		}

		const resolvedName = name || prev?.name || ''
		out.set(id, { id, name: resolvedName, arguments: args })
	}
	return Array.from(out.values())
}

// message children map

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

// run block building

export interface BuildRunBlocksInput {
	messages: ApiMessage[]
	userId: string | null
	streamingAssistant: StreamingAssistantState | null
	optimisticUserMessage: OptimisticUserMessage | null
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
 * pure function - no reactive state or side effects.
 */
export function buildRunBlocks(input: BuildRunBlocksInput): BuildRunBlocksResult {
	const { messages, userId, streamingAssistant, optimisticUserMessage, viewingStreamingBranch } =
		input

	const blocks: RunBlock[] = []
	const collectedToolCalls: ToolCall[] = []
	const collectedToolResults: ToolResult[] = []
	type ActiveBlock = {
		block: RunBlock
		sourceRunId: string
		sourceAgentId: string | null
		seenToolCalls: Set<string>
	}
	let activeBlock: ActiveBlock | null = null

	const createBlock = (
		sourceRunId: string,
		sourceAgentId: string | null,
		startedAt: Date,
		title: string,
		anchorId: string
	): ActiveBlock => {
		const block: RunBlock = {
			runId: `${sourceRunId}:${anchorId}`,
			agentId: sourceAgentId,
			startedAt,
			title,
			items: [],
			responseRootId: null,
		}
		blocks.push(block)
		return { block, sourceRunId, sourceAgentId, seenToolCalls: new Set() }
	}

	const hasResponseItems = (block: RunBlock): boolean =>
		block.items.some((item) => item.kind !== 'user' && item.kind !== 'optimistic_user')

	const ensureResponseBlock = (
		sourceRunId: string,
		sourceAgentId: string | null,
		msg: ApiMessage
	): ActiveBlock => {
		if (activeBlock && activeBlock.sourceRunId === sourceRunId) {
			if (!hasResponseItems(activeBlock.block)) {
				activeBlock.sourceAgentId = sourceAgentId
				activeBlock.block.agentId = sourceAgentId
				return activeBlock
			}
			if (activeBlock.sourceAgentId === sourceAgentId) return activeBlock
		}
		activeBlock = createBlock(
			sourceRunId,
			sourceAgentId,
			getMessageCreatedAt(msg),
			'assistant',
			msg.id
		)
		return activeBlock
	}

	for (const msg of messages) {
		if (streamingAssistant && msg.id === streamingAssistant.messageId) continue

		// tool results don't contribute visible items to blocks - handle early
		// to avoid creating empty trailing blocks that break isLastMessage checks
		if (msg.type === 'tool') {
			const result = parseToolResult(msg)
			if (result) collectedToolResults.push(result)
			const sourceRunId = getRunId(msg)
			const sourceAgentId =
				activeBlock && activeBlock.sourceRunId === sourceRunId
					? activeBlock.sourceAgentId
					: null
			const blockState = ensureResponseBlock(sourceRunId, sourceAgentId, msg)
			if (blockState.block.responseRootId === null) {
				blockState.block.responseRootId = msg.id
			}
			continue
		}

		const sourceRunId = getRunId(msg)

		if (msg.type === 'user') {
			if (
				!activeBlock ||
				activeBlock.sourceRunId !== sourceRunId ||
				hasResponseItems(activeBlock.block)
			) {
				activeBlock = createBlock(
					sourceRunId,
					null,
					getMessageCreatedAt(msg),
					'assistant',
					msg.id
				)
			}
			const align: 'left' | 'right' =
				userId && msg.sender_user_id && msg.sender_user_id !== userId ? 'left' : 'right'
			activeBlock.block.items.push({ kind: 'user', message: msg, align })
			continue
		}

		const sourceAgentId = getMessageAgentId(msg)
		const blockState = ensureResponseBlock(sourceRunId, sourceAgentId, msg)
		const block = blockState.block

		if (block.responseRootId === null) {
			block.responseRootId = msg.id
		}

		if (msg.type === 'assistant') {
			const text = contentPartsToText(msg.content).trim()
			if (text.length > 0) block.items.push({ kind: 'assistant', message: msg })
			for (const tc of parseToolCalls(msg)) {
				collectedToolCalls.push(tc)
				if (!blockState.seenToolCalls.has(tc.id)) {
					blockState.seenToolCalls.add(tc.id)
					block.items.push({ kind: 'tool', toolCallId: tc.id })
				}
			}
			continue
		}
	}

	if (streamingAssistant && viewingStreamingBranch) {
		const sourceRunId = streamingAssistant.runId ?? `legacy-${streamingAssistant.messageId}`
		const sourceAgentId = streamingAssistant.senderAgentId
		if (
			!activeBlock ||
			activeBlock.sourceRunId !== sourceRunId ||
			(hasResponseItems(activeBlock.block) && activeBlock.sourceAgentId !== sourceAgentId)
		) {
			activeBlock = createBlock(
				sourceRunId,
				sourceAgentId,
				streamingAssistant.timestamp,
				'assistant',
				streamingAssistant.messageId
			)
		} else if (!hasResponseItems(activeBlock.block)) {
			activeBlock.sourceAgentId = sourceAgentId
			activeBlock.block.agentId = sourceAgentId
		}
		const block = activeBlock.block

		if (optimisticUserMessage) {
			if (hasResponseItems(block)) {
				activeBlock = createBlock(
					sourceRunId,
					sourceAgentId,
					optimisticUserMessage.timestamp,
					'pending',
					`optimistic-${optimisticUserMessage.timestamp.getTime()}`
				)
			}
			const targetBlock = activeBlock.block
			targetBlock.items.push({
				kind: 'optimistic_user',
				text: optimisticUserMessage.text,
				attachments: optimisticUserMessage.attachments,
				timestamp: optimisticUserMessage.timestamp,
			})
		}

		const targetBlockState = activeBlock
		const targetBlock = targetBlockState.block
		if (targetBlock.responseRootId === null) {
			targetBlock.responseRootId = streamingAssistant.messageId
		}

		targetBlock.items.push({ kind: 'streaming_assistant' })
		for (const tc of streamingAssistant.toolCalls) {
			collectedToolCalls.push(tc)
			if (!targetBlockState.seenToolCalls.has(tc.id)) {
				targetBlockState.seenToolCalls.add(tc.id)
				targetBlock.items.push({ kind: 'streaming_tool', toolCallId: tc.id })
			}
		}
	} else if (optimisticUserMessage && viewingStreamingBranch) {
		const runId = `pending-user-${optimisticUserMessage.timestamp.getTime()}`
		const block = createBlock(
			runId,
			null,
			optimisticUserMessage.timestamp,
			'pending',
			`optimistic-${optimisticUserMessage.timestamp.getTime()}`
		).block
		block.items.push({
			kind: 'optimistic_user',
			text: optimisticUserMessage.text,
			attachments: optimisticUserMessage.attachments,
			timestamp: optimisticUserMessage.timestamp,
		})
	}

	return {
		blocks: blocks.filter((block) => block.items.length > 0),
		toolCalls: collectedToolCalls,
		toolResults: collectedToolResults,
	}
}

// run block queries

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
			| {
					kind: 'optimistic_user'
					text: string
					attachments: PendingAttachment[]
					timestamp: Date
			  }
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

/** convert pending attachments to media parts for optimistic rendering before the real message arrives */
export function pendingAttachmentsToMediaParts(
	attachments: PendingAttachment[]
): MediaContentPart[] {
	return attachments
		.filter(
			(
				a
			): a is PendingAttachment & {
				category: 'image' | 'audio' | 'video'
				previewUrl: string
			} => a.category !== 'file' && typeof a.previewUrl === 'string'
		)
		.map((a) => ({
			type: a.category,
			url: a.previewUrl,
			filename: a.filename,
			mediaType: a.mediaType,
			fileId: a.fileId,
		}))
}

/** convert pending attachments to file parts for optimistic rendering before the real message arrives */
export function pendingAttachmentsToFileParts(attachments: PendingAttachment[]): FileContentPart[] {
	return attachments
		.filter((a) => a.category === 'file')
		.map((a) => ({
			type: 'file' as const,
			filename: a.filename,
			mediaType: a.mediaType,
			fileId: a.fileId,
		}))
}

// response item grouping

type ResponseItem = ReturnType<typeof getBlockResponseItems>[number]

export type ResponseSegment =
	| { type: 'assistant'; item: { kind: 'assistant'; message: ApiMessage } }
	| { type: 'streaming_assistant'; item: { kind: 'streaming_assistant' } }
	| { type: 'tool_group'; toolCallIds: string[] }

/**
 * group consecutive tool/streaming_tool items into tool groups.
 * non-tool items are passed through individually.
 */
export function groupResponseItems(items: ResponseItem[]): ResponseSegment[] {
	const segments: ResponseSegment[] = []
	let pendingToolIds: string[] = []

	function flushTools() {
		if (pendingToolIds.length > 0) {
			segments.push({ type: 'tool_group', toolCallIds: [...pendingToolIds] })
			pendingToolIds = []
		}
	}

	for (const item of items) {
		if (item.kind === 'tool' || item.kind === 'streaming_tool') {
			pendingToolIds.push(item.toolCallId)
		} else {
			flushTools()
			if (item.kind === 'assistant') {
				segments.push({ type: 'assistant', item })
			} else if (item.kind === 'streaming_assistant') {
				segments.push({ type: 'streaming_assistant', item })
			}
		}
	}
	flushTools()
	return segments
}

// agent lookups

/**
 * build a lookup map from agent id to a derived value.
 */
export function buildAgentLookup<A extends { id: string }, T>(
	list: A[],
	selector: (agent: A) => T
): Map<string, T> {
	return new Map(list.map((a) => [a.id, selector(a)]))
}

// citation helpers

/**
 * compute the cited-only citations for a run block's sources pill.
 * gathers all available sources from the citationSources map, then
 * filters to only indices actually referenced in the block's content.
 */
export function computeBlockCitations(
	responseItems: ReturnType<typeof getBlockResponseItems>,
	streamingAssistant: StreamingAssistantState | null,
	citationSources: ReadonlyMap<string, ApiCitation[]>
): ApiCitation[] {
	const allSources: ApiCitation[] = []
	const seen = new Set<number>()
	for (const item of responseItems) {
		if (item.kind !== 'assistant') continue
		for (const c of citationSources.get(item.message.id) ?? []) {
			if (!seen.has(c.index)) {
				seen.add(c.index)
				allSources.push(c)
			}
		}
	}
	if (streamingAssistant) {
		for (const c of citationSources.get(streamingAssistant.messageId) ?? []) {
			if (!seen.has(c.index)) {
				seen.add(c.index)
				allSources.push(c)
			}
		}
	}
	if (allSources.length === 0) return []
	let combined = responseItems
		.filter((i): i is { kind: 'assistant'; message: ApiMessage } => i.kind === 'assistant')
		.map((i) => contentPartsToText(i.message.content))
		.join('\n')
	if (streamingAssistant) combined += '\n' + streamingAssistant.content
	const cited = new Set([...combined.matchAll(/\[\^?(\d+)\]/g)].map((m) => Number(m[1])))
	return allSources.filter((c) => cited.has(c.index))
}
