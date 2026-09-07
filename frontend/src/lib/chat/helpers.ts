/**
 * pure utility functions for chat - no reactive state, no side effects.
 * types are defined in $lib/chat/types.ts, not here.
 */

import { parseToolCalls, parseToolResult, type ToolCall, type ToolResult } from '$lib/tools'
import { SvelteDate } from 'svelte/reactivity'
import { needsTimeHeader } from './chatTimestamps'
import type { ChatSystemEvent } from './systemEvents'
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
	RunFailureEntry,
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
 * ids a run bubble carries before the backend has given it a message.
 *
 * they name a bridge, never a message: the backend parses a splice parent as a
 * typeid, so sending one back is a 422 and poisons every later run on that
 * branch. nothing carrying one may become a durable leaf.
 */
const PLACEHOLDER_MESSAGE_ID_PREFIXES = ['pending-', 'resume-', 'local-steering-']

/** whether an id is a client-side placeholder rather than a persisted message. */
export function isPlaceholderMessageId(id: string | null | undefined): boolean {
	if (!id) return false
	return PLACEHOLDER_MESSAGE_ID_PREFIXES.some((prefix) => id.startsWith(prefix))
}

/**
 * the alternatives of one message: the children of its parent of the same kind.
 *
 * a user message forks into other user messages, a run's output into other
 * runs' output. counting across kinds makes a run's own user message look like
 * an alternative to the answer that run has not produced yet, which flashes a
 * phantom "2/2" branch badge on brand new messages.
 */
export function siblingIdsOfKind(
	parentId: string | null,
	kind: 'user' | 'response',
	messageChildren: ReadonlyMap<string | null, string[]>,
	messageTree: ReadonlyMap<string, ApiMessage>
): string[] {
	const children = messageChildren.get(parentId) ?? []
	return children.filter((id) => {
		const message = messageTree.get(id)
		if (!message) return false
		return (message.type === 'user') === (kind === 'user')
	})
}

/**
 * how many alternatives the branch switcher steps through at a fork.
 *
 * the branch page's own count is the truth - it reports every alternative while
 * carrying only the first few - so what is loaded is a floor, never the total.
 *
 * a shared thread's forks are its sub-threads and count exactly the same way:
 * thread kind never zeroes this.
 */
export function branchAlternativeCount(
	parentId: string | null,
	loadedSiblings: readonly string[],
	siblingCounts: ReadonlyMap<string, number>
): number {
	return Math.max(siblingCounts.get(parentId ?? '') ?? 0, loadedSiblings.length)
}

/**
 * persist the current streaming assistant's partial content into the message
 * tree (marked partial) so a transport failure or stop keeps whatever text was
 * already rendered instead of discarding it. callers typically follow this
 * with a fresh error bubble in a separate placeholder.
 *
 * a run that produced nothing has nothing to preserve, and writing an empty
 * placeholder for it would move the branch leaf onto an id no reload can
 * resolve - which is how a failed regeneration loses its branch switcher.
 */
export function finalizeStreamingAssistantAsPartial(ctx: ChatContext): void {
	const streaming = ctx.streamingAssistant
	if (!streaming) return
	// a bridge is not a message. writing one into the tree moves the leaf onto an
	// id no reload can resolve, and every later splice naming it is a 422.
	if (isPlaceholderMessageId(streaming.messageId)) return
	// apply any buffered streamed tokens before snapshotting the partial content
	ctx.flushStreamingText()

	const existingMessage = ctx.messageTree.get(streaming.messageId)
	const content = streaming.content.trim() || contentPartsToText(existingMessage?.content).trim()
	if (!content && streaming.toolCalls.length === 0) return
	const createdAt = existingMessage?.created_at ?? new SvelteDate().toISOString()
	const updatedAt = new SvelteDate().toISOString()
	const parentId = existingMessage?.parent_id ?? ctx.streamingAssistantParentId
	const streamCitations = ctx.citationSources.get(streaming.messageId)
	const citedIndices = new Set(
		[...content.matchAll(/\[\^?(\d+)\]/g)].map((match) => Number(match[1]))
	)
	const citedSources = streamCitations?.filter((citation) => citedIndices.has(citation.index))
	const metadata: NonNullable<ApiMessage['metadata']> = {
		...(existingMessage?.metadata ?? {}),
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
		metadata: metadata,
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

/**
 * hand a dead run over to the backend's own events.
 *
 * the bridge bubble stays exactly where it is - it holds the text that already
 * streamed, and blanking it would flash - but it is marked dead so nothing
 * reads it as a live run. the persisted message and the durable `run.error`
 * replace it when they arrive over the WS; the client authors neither.
 */
export function markRunBridgeFailed(ctx: ChatContext, message: string): void {
	const bridge = ctx.streamingAssistant
	if (!bridge) return
	ctx.flushStreamingText()
	bridge.isError = true
	bridge.errorMessage = message
}

/**
 * the request never reached the backend: nothing was persisted and no event
 * will ever arrive, so the bridge goes away and the user's own bubble carries
 * the outcome instead. the message tree is left untouched.
 */
export function markRunNotDelivered(ctx: ChatContext): void {
	ctx.streamingAssistant = null
	ctx.streamingLeafId = null
	if (ctx.optimisticUserMessage) {
		ctx.optimisticUserMessage = { ...ctx.optimisticUserMessage, deliveryFailed: true }
	}
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
 * - streamed (SDK/delta) messages carry them in `metadata.attachments`.
 *
 * this reads both sources and de-dupes by `type:id`, so callers get one
 * uniform list regardless of which representation produced the message.
 */
export function extractAttachmentRefs(
	msg: Pick<ApiMessage, 'attachments' | 'metadata'>
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
	const metaRefs = msg.metadata?.attachments
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
/** block source for plain conversation messages, which belong to no run. */
const CONVERSATION_RUN = 'conversation'

export function hasRunId(msg: Pick<ApiMessage, 'metadata'>): boolean {
	return Boolean(msg.metadata && typeof msg.metadata.run_id === 'string')
}

export function getRunId(msg: Pick<ApiMessage, 'metadata' | 'id'>): string {
	const runId =
		msg.metadata && typeof msg.metadata.run_id === 'string' ? msg.metadata.run_id : null
	return runId ?? `legacy-${msg.id}`
}

/**
 * extract the agent id that produced a response message, if known.
 */
export function getMessageAgentId(
	msg: Pick<ApiMessage, 'sender_agent_id' | 'metadata'>
): string | null {
	if (typeof msg.sender_agent_id === 'string' && msg.sender_agent_id) return msg.sender_agent_id
	return msg.metadata && typeof msg.metadata.agent_id === 'string' ? msg.metadata.agent_id : null
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
	runFailures?: RunFailureEntry[]
	systemEvents?: ChatSystemEvent[]
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
		runFailures = [],
		systemEvents = [],
	} = input

	const blocks: RunBlock[] = []
	const collectedToolCalls: ToolCall[] = []
	const collectedToolResults: ToolResult[] = []
	type ActiveBlock = {
		block: RunBlock
		sourceRunId: string
		sourceAgentId: string | null
		author?: string | null
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

	// a failure renders after its anchor message. only the NEWEST failure per
	// anchor+agent is shown: retrying re-answers that same anchor, so a stack of
	// them would offer several buttons that all do the identical thing. the
	// older ones stay in the event log as history.
	const failuresByMessage = new Map<string, Map<string, RunFailureEntry>>()
	for (const failure of runFailures) {
		if (!failure.anchorMessageId) continue
		const perAgent = failuresByMessage.get(failure.anchorMessageId) ?? new Map()
		const existing = perAgent.get(failure.agentId)
		if (!existing || failure.createdAt.getTime() >= existing.createdAt.getTime()) {
			perAgent.set(failure.agentId, failure)
		}
		failuresByMessage.set(failure.anchorMessageId, perAgent)
	}
	const failuresFor = (messageId: string): RunFailureEntry[] => {
		const perAgent = failuresByMessage.get(messageId)
		if (!perAgent) return []
		return [...perAgent.values()].sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime())
	}

	const pushRunFailures = (block: RunBlock, messageId: string): void => {
		for (const failure of failuresFor(messageId)) {
			// a failure is the run's own output, so it names the block's agent.
			// without this the block renders the literal "assistant" fallback,
			// since a run that died produced no message to identify it by.
			if (!block.agentId) block.agentId = failure.agentId
			block.items.push({ kind: 'run_failure', failure })
		}
	}

	/**
	 * anchors whose failures are waiting for the answering agent's block.
	 *
	 * the failure describes the ANSWER, so it renders with the response rather
	 * than inside the user's own block.
	 */
	const pendingFailureAnchors: string[] = []

	const flushPendingFailures = (block: RunBlock): void => {
		if (pendingFailureAnchors.length === 0) return
		const anchors = pendingFailureAnchors.splice(0, pendingFailureAnchors.length)
		for (const anchor of anchors) pushRunFailures(block, anchor)
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

	// a system row is not a message: it sits BETWEEN the bubbles at its own
	// timestamp, in a block of its own, so a run of one author's bubbles breaks
	// around it the way imessage breaks around a grey row.
	const orderedSystemEvents = [...systemEvents].sort(
		(a, b) => a.createdAt.getTime() - b.createdAt.getTime()
	)
	let nextSystemEvent = 0
	const flushSystemEventsUpTo = (until: Date | null): void => {
		while (nextSystemEvent < orderedSystemEvents.length) {
			const event = orderedSystemEvents[nextSystemEvent]
			if (until && event.createdAt.getTime() > until.getTime()) break
			nextSystemEvent += 1
			blocks.push({
				runId: `system:${event.id}`,
				agentId: null,
				startedAt: event.createdAt,
				title: 'system',
				items: [{ kind: 'system_event', event }],
				responseRootId: null,
			})
			activeBlock = null
		}
	}

	for (const msg of messages) {
		flushSystemEventsUpTo(getMessageCreatedAt(msg))
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
			// consecutive messages from one author cluster into one block, whether or
			// not any of them started a run. the block follows the latest run so the
			// answer to its last message lands in the same block.
			const plain = !hasRunId(msg)
			const author = msg.sender_user_id ?? null
			// a long silence is not a cluster, however few words crossed it: the
			// header that dates it needs a seam between blocks to sit in.
			const continues =
				activeBlock !== null &&
				!hasResponseItems(activeBlock.block) &&
				activeBlock.author !== undefined &&
				activeBlock.author === author &&
				!needsTimeHeader(runBlockLatestAt(activeBlock.block), getMessageCreatedAt(msg))
			if (continues && activeBlock) {
				if (!plain) activeBlock.sourceRunId = sourceRunId
			} else {
				activeBlock = createBlock(
					plain ? CONVERSATION_RUN : sourceRunId,
					null,
					getMessageCreatedAt(msg),
					'assistant',
					msg.id
				)
				activeBlock.author = author
			}
			const align: 'left' | 'right' =
				userId && msg.sender_user_id && msg.sender_user_id !== userId ? 'left' : 'right'
			activeBlock.block.items.push({ kind: 'user', message: msg, align })
			pushRunActivities(activeBlock.block, msg.id)
			// a failure anchored on a user message is the ANSWER's outcome, so it
			// belongs to the responding agent's block - pushed here it would make
			// the user's own block look like a response and split it off alone.
			pendingFailureAnchors.push(msg.id)
			continue
		}

		const sourceAgentId = getMessageAgentId(msg)
		const blockState = ensureResponseBlock(sourceRunId, sourceAgentId, msg)
		const block = blockState.block

		if (block.responseRootId === null) {
			block.responseRootId = msg.id
		}

		flushPendingFailures(block)

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
			pushRunFailures(block, msg.id)
			continue
		}
	}

	// a run that never started produced no message to attach to, so its failure
	// still needs a block of its own - it is the only trace the run left.
	if (pendingFailureAnchors.length > 0) {
		const anchors = pendingFailureAnchors.splice(0, pendingFailureAnchors.length)
		for (const anchor of anchors) {
			const failures = failuresFor(anchor)
			if (failures.length === 0) continue
			const block = createBlock(
				`failure-${anchor}`,
				failures[0].agentId,
				failures[0].createdAt,
				'assistant',
				anchor
			).block
			for (const failure of failures) {
				block.items.push({ kind: 'run_failure', failure })
			}
		}
	}

	// anything that happened after the last message - a live arrival, most of
	// the time - lands at the tail, above whatever is still streaming.
	flushSystemEventsUpTo(null)

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
				deliveryFailed: optimisticUserMessage.deliveryFailed,
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
		const userMessagePending = optimisticUserMessage !== null
		if (
			hasStreamingText ||
			streamingAssistant.isError ||
			(!userMessagePending &&
				!hasUnresolvedPreviousToolCalls &&
				!hasUnresolvedStreamingToolCalls)
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
			deliveryFailed: optimisticUserMessage.deliveryFailed,
		})
	}

	return {
		blocks: withTimeHeaders(blocks.filter((block) => block.items.length > 0)),
		toolCalls: collectedToolCalls,
		toolResults: collectedToolResults,
	}
}

/** when one item happened, for the items that happen at a moment at all. */
function runItemAt(item: RunItem): Date | null {
	switch (item.kind) {
		case 'user':
		case 'assistant':
			return getMessageCreatedAt(item.message)
		case 'optimistic_user':
			return item.timestamp
		case 'run_activity':
			return item.activity.startedAt
		case 'run_failure':
			return item.failure.createdAt
		case 'system_event':
			return item.event.createdAt
		case 'time_header':
			return item.at
		default:
			return null
	}
}

/**
 * the latest moment a block renders.
 *
 * a run that thought for an hour ends where its answer landed, not where the
 * question was asked, so the next gap is measured from there - otherwise every
 * long run would be followed by a header nobody waited for.
 */
export function runBlockLatestAt(block: RunBlock): Date {
	let latest = block.startedAt
	for (const item of block.items) {
		const at = runItemAt(item)
		if (at && at.getTime() > latest.getTime()) latest = at
	}
	return latest
}

/**
 * drop a centered time header wherever the conversation went quiet long enough
 * to need dating.
 *
 * a header is a block of its own for the same reason a system row is: it sits
 * BETWEEN bubbles and breaks the run around it, the way imessage does. the
 * transcript's opening stamp is not one of these - see `needsTimeHeader`.
 */
export function withTimeHeaders(blocks: RunBlock[]): RunBlock[] {
	const out: RunBlock[] = []
	let previous: Date | null = null
	for (const block of blocks) {
		// only a bubble that lost its own date needs one hung above it: an agent
		// answer still carries its date on top, and a system row is prose about
		// the chat rather than something anyone said.
		const opensWithBubble =
			block.items[0]?.kind === 'user' || block.items[0]?.kind === 'optimistic_user'
		if (opensWithBubble && needsTimeHeader(previous, block.startedAt)) {
			out.push({
				runId: `time:${block.runId}`,
				agentId: null,
				startedAt: block.startedAt,
				title: 'time',
				items: [{ kind: 'time_header', at: block.startedAt }],
				responseRootId: null,
			})
		}
		out.push(block)
		previous = runBlockLatestAt(block)
	}
	return out
}

// run block queries

/** items a run block renders as the agent's response - everything a bubble is not. */
export type ResponseRunItem = Extract<
	RunItem,
	{
		kind:
			| 'run_activity'
			| 'assistant'
			| 'tool'
			| 'streaming_assistant'
			| 'streaming_tool'
			| 'run_failure'
	}
>

const RESPONSE_ITEM_KINDS: ReadonlySet<RunItem['kind']> = new Set([
	'run_activity',
	'assistant',
	'tool',
	'streaming_assistant',
	'streaming_tool',
	'run_failure',
])

export function getBlockResponseItems(block: RunBlock): ResponseRunItem[] {
	return block.items.filter((item): item is ResponseRunItem => RESPONSE_ITEM_KINDS.has(item.kind))
}

/** the system rows a block carries; a system block carries nothing else. */
export function getBlockSystemEvents(block: RunBlock): ChatSystemEvent[] {
	return block.items.flatMap((item) => (item.kind === 'system_event' ? [item.event] : []))
}

/** the moment a header block dates, or null for every other kind of block. */
export function getBlockTimeHeader(block: RunBlock): Date | null {
	const item = block.items.find((entry) => entry.kind === 'time_header')
	return item?.kind === 'time_header' ? item.at : null
}

export function getBlockFirstAssistant(block: RunBlock): ApiMessage | null {
	const item = block.items.find((i) => i.kind === 'assistant')
	return item?.kind === 'assistant' ? item.message : null
}

export function blockHasStreamingAssistant(block: RunBlock): boolean {
	return block.items.some(
		(item) => item.kind === 'streaming_assistant' || item.kind === 'streaming_tool'
	)
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
	| { type: 'run_failure'; failure: RunFailureEntry }

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
			} else if (item.kind === 'run_failure') {
				segments.push({ type: 'run_failure', failure: item.failure })
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
