/**
 * pure utility functions for chat - no reactive state, no side effects.
 * types are defined in $lib/chat/types.ts, not here.
 */

import { parseToolCalls, parseToolResult, type ToolCall, type ToolResult } from '$lib/tools'
import { SvelteDate } from 'svelte/reactivity'
import type {
	ApiCitation,
	ApiMessage,
	ChatContext,
	FileContentPart,
	MediaContentPart,
	OptimisticUserMessage,
	PendingAttachment,
	ResourceAttachment,
	RunActivityState,
	RunBlock,
	RunItem,
	StreamingAssistantState,
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

/**
 * persist the current streaming assistant's partial content into the message
 * tree (marked partial) so a transport failure or stop keeps whatever text was
 * already rendered instead of discarding it. callers typically follow this
 * with a fresh error bubble in a separate placeholder.
 */
export function finalizeStreamingAssistantAsPartial(ctx: ChatContext): void {
	const streaming = ctx.streamingAssistant
	if (!streaming) return

	const existingMessage = ctx.messageTree.get(streaming.messageId)
	const content = streaming.content.trim() || contentPartsToText(existingMessage?.content).trim()
	const createdAt = existingMessage?.created_at ?? new SvelteDate().toISOString()
	const updatedAt = new SvelteDate().toISOString()
	const parentId = existingMessage?.parent_id ?? ctx.streamingAssistantParentId
	const streamCitations = ctx.citationSources.get(streaming.messageId)
	const citedIndices = new Set(
		[...content.matchAll(/\[\^?(\d+)\]/g)].map((match) => Number(match[1]))
	)
	const citedSources = streamCitations?.filter((citation) => citedIndices.has(citation.index))
	const metadata: NonNullable<ApiMessage['metadata_']> = {
		...(existingMessage?.metadata_ ?? {}),
		partial: true,
		partial_reason: 'cancelled',
	}
	if (streaming.runId) metadata.run_id = streaming.runId

	const finalized = {
		id: streaming.messageId,
		thread_id: existingMessage?.thread_id ?? ctx.thread?.id ?? '',
		parent_id: parentId,
		type: 'assistant',
		content: content ? [{ type: 'text', text: content }] : [],
		tool_calls: streaming.toolCalls.map((toolCall) => ({
			id: toolCall.id,
			name: toolCall.name,
			arguments: toolCall.arguments,
		})),
		citations: citedSources?.length ? citedSources : existingMessage?.citations,
		metadata_: metadata,
		sender_agent_id: streaming.senderAgentId,
		sender_user_id: null,
		created_at: createdAt,
		updated_at: updatedAt,
	} satisfies ApiMessage

	ctx.messageTree.set(finalized.id, finalized)
	ctx.citationTargetMessageId = finalized.id
	ctx.streamingLeafId = finalized.id
	if (ctx.viewingStreamingBranch) ctx.currentLeafId = finalized.id
	ctx.streamingAssistantParentId = finalized.id
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

function isAttachmentRefType(value: unknown): value is ResourceAttachment['type'] {
	return (
		value === 'file' ||
		value === 'note' ||
		value === 'thread' ||
		value === 'project' ||
		value === 'reminder' ||
		value === 'reminder_list' ||
		value === 'calendar_event' ||
		value === 'calendar'
	)
}

/**
 * extract attachment resource refs ({type, id}) from a message.
 *
 * refs live in two places depending on the message representation:
 * - complete (ORM) messages carry them in the dedicated `attachments` column.
 * - streamed (SDK/delta) messages carry them in `metadata_.attachments`.
 *
 * this reads both sources and de-dupes by `type:id`, so callers get one
 * uniform list regardless of which representation produced the message.
 */
export function extractAttachmentRefs(
	msg: Pick<ApiMessage, 'attachments' | 'metadata_'>
): ResourceAttachment[] {
	const seen = new Set<string>()
	const refs: ResourceAttachment[] = []

	const push = (value: unknown): void => {
		if (!value || typeof value !== 'object') return
		const ref = value as Record<string, unknown>
		const { type, id } = ref
		if (!isAttachmentRefType(type) || typeof id !== 'string') return
		const key = `${type}:${id}`
		if (seen.has(key)) return
		seen.add(key)
		refs.push({ type, id })
	}

	for (const ref of msg.attachments ?? []) push(ref)
	const metaRefs = msg.metadata_?.attachments
	if (Array.isArray(metaRefs)) for (const ref of metaRefs) push(ref)

	return refs
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

function getUserRunItemAuthor(item: RunItem): string | null {
	if (item.kind === 'user') return item.message.sender_user_id ?? `align:${item.align}`
	if (item.kind === 'optimistic_user') return 'optimistic:user'
	return null
}

function getUserRunItemCreatedAt(item: RunItem): Date | null {
	if (item.kind === 'user') return getMessageCreatedAt(item.message)
	if (item.kind === 'optimistic_user') return item.timestamp
	return null
}

export function getUserRunItemTimestamp(
	item: RunItem,
	previousItem: RunItem | undefined
): Date | undefined {
	const timestamp = getUserRunItemCreatedAt(item)
	if (!timestamp) return undefined
	if (!previousItem) return timestamp

	const previousTimestamp = getUserRunItemCreatedAt(previousItem)
	if (!previousTimestamp) return timestamp
	if (timestamp.getTime() !== previousTimestamp.getTime()) return timestamp
	if (getUserRunItemAuthor(item) !== getUserRunItemAuthor(previousItem)) return timestamp
	return undefined
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
	runActivities?: RunActivityState[]
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
	const {
		messages,
		userId,
		streamingAssistant,
		optimisticUserMessage,
		viewingStreamingBranch,
		runActivities = [],
	} = input

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
	const activitiesByMessage = new Map<string, RunActivityState[]>()
	for (const activity of runActivities) {
		const current = activitiesByMessage.get(activity.messageId) ?? []
		current.push(activity)
		activitiesByMessage.set(activity.messageId, current)
	}
	for (const activities of activitiesByMessage.values()) {
		activities.sort((a, b) => a.startedAt.getTime() - b.startedAt.getTime())
	}
	/** place run activities immediately after their timeline anchor message. */
	const pushRunActivities = (block: RunBlock, messageId: string): void => {
		for (const activity of activitiesByMessage.get(messageId) ?? []) {
			block.items.push({ kind: 'run_activity', activity })
		}
	}

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
			if (activeBlock.sourceAgentId === sourceAgentId) return activeBlock
			if (!activeBlock.sourceAgentId && sourceAgentId) {
				activeBlock.sourceAgentId = sourceAgentId
				activeBlock.block.agentId = sourceAgentId
				return activeBlock
			}
			if (!hasResponseItems(activeBlock.block)) return activeBlock
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
			pushRunActivities(blockState.block, msg.id)
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
			pushRunActivities(activeBlock.block, msg.id)
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
			pushRunActivities(block, msg.id)
			continue
		}
	}

	if (streamingAssistant && viewingStreamingBranch) {
		const sourceRunId = streamingAssistant.runId ?? `legacy-${streamingAssistant.messageId}`
		const sourceAgentId = streamingAssistant.senderAgentId
		const completedToolCallIds = new Set(
			collectedToolResults.map((result) => result.toolCallId)
		)
		if (
			!activeBlock ||
			activeBlock.sourceRunId !== sourceRunId ||
			(hasResponseItems(activeBlock.block) &&
				activeBlock.sourceAgentId !== null &&
				activeBlock.sourceAgentId !== sourceAgentId)
		) {
			activeBlock = createBlock(
				sourceRunId,
				sourceAgentId,
				streamingAssistant.timestamp,
				'assistant',
				streamingAssistant.messageId
			)
		} else if (!activeBlock.sourceAgentId && sourceAgentId) {
			activeBlock.sourceAgentId = sourceAgentId
			activeBlock.block.agentId = sourceAgentId
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

		const hasStreamingText = streamingAssistant.content.trim().length > 0
		const hasUnresolvedPreviousToolCalls = Array.from(targetBlockState.seenToolCalls).some(
			(toolCallId) => !completedToolCallIds.has(toolCallId)
		)
		// only unresolved streaming tool calls suppress the text placeholder.
		// once a tool result arrives, the placeholder must reappear so the
		// "thinking" animation shows again before the model's next token.
		const hasUnresolvedStreamingToolCalls = streamingAssistant.toolCalls.some(
			(toolCall) => !completedToolCallIds.has(toolCall.id)
		)
		if (
			hasStreamingText ||
			(!hasUnresolvedPreviousToolCalls && !hasUnresolvedStreamingToolCalls)
		) {
			targetBlock.items.push({ kind: 'streaming_assistant' })
		}
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

export function getBlockResponseItems(block: RunBlock): Array<
	Exclude<
		RunItem,
		| { kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
		| {
				kind: 'optimistic_user'
				text: string
				attachments: PendingAttachment[]
				timestamp: Date
		  }
	>
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
	| { type: 'run_activity'; activity: RunActivityState }
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
			} else if (item.kind === 'run_activity') {
				segments.push({ type: 'run_activity', activity: item.activity })
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
