/**
 * shared type definitions for the chat module.
 * all chat-related types live here - types should not be defined in utility
 * modules like helpers.ts or attachments.ts.
 */

import type { CreateAndRunStreamDelta } from '$lib/api/streaming/chatStream'
import type { components } from '$lib/api/types'
import type { Thread } from '$lib/stores/chat.svelte'
import type { ToolCall, ToolExecution, ToolExecutionTracker } from '$lib/tools'
import type { SvelteMap, SvelteSet } from 'svelte/reactivity'

// --- API types ---

export type ApiMessage = components['schemas']['Message']
export type ApiCitation = components['schemas']['Citation']

// --- content part types ---

/** an image or video content part with resolved URL */
export interface MediaContentPart {
	type: 'image' | 'video' | 'audio'
	url: string
	filename?: string | null
	mediaType?: string | null
	fileId?: string
	attachmentStatus?: string
}

/** a non-media file content part */
export interface FileContentPart {
	type: 'file'
	url?: string | null
	filename?: string | null
	mediaType?: string | null
	fileId?: string
	attachmentStatus?: string
}

// --- attachment types ---

export type AttachmentMediaCategory = 'image' | 'audio' | 'video' | 'file'
export type AttachmentStatus = 'active' | 'reference'

/** a file that has been uploaded and is pending inclusion in the next message */
export interface PendingAttachment {
	fileId: string
	filename: string
	mediaType: string
	category: AttachmentMediaCategory
	/** local object URL for preview (images/video) - revoked after send */
	previewUrl?: string
	/** how this attachment was added - 'upload' = new file, 'resource' = existing resource */
	source: 'upload' | 'resource'
}

/** an attachment already present in the thread (derived from message content) */
export interface ThreadAttachment {
	fileId: string
	filename: string | null
	mediaType: string | null
	category: AttachmentMediaCategory
	status: AttachmentStatus
	/** the turn index where this attachment was first introduced */
	turn: number
}

/** modifiers toggled by the user in AddContext */
export interface RunModifiers {
	webSearch: boolean
	thinkLonger: boolean
	generateImage: boolean
	attachments: PendingAttachment[]
}

/** structured optimistic user message - mirrors what was sent to the API */
export interface OptimisticUserMessage {
	text: string
	attachments: PendingAttachment[]
	timestamp: Date
}

/** allowed tool_choice values that can be forced by the user */
export type ToolChoiceValue = 'web_search' | 'think' | 'generate_image'

// --- run/block types ---

export type RunItem =
	| { kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
	| { kind: 'optimistic_user'; text: string; attachments: PendingAttachment[]; timestamp: Date }
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

// --- chat state types ---

/**
 * reactive state proxy passed to all extracted chat module functions.
 * the coordinator creates this object with getters/setters that read/write
 * Svelte 5 $state variables, preserving fine-grained reactivity.
 */
export interface ChatContext {
	// thread
	thread: Thread | null

	// message tree
	readonly messageTree: SvelteMap<string, ApiMessage>
	readonly messageChildren: Map<string | null, string[]>
	currentLeafId: string | null
	readonly messages: ApiMessage[]

	// streaming
	isGenerating: boolean
	activeRun: number
	streamingAssistant: StreamingAssistantState | null
	streamingAssistantParentId: string | null
	streamingLeafId: string | null
	viewingStreamingBranch: boolean
	optimisticUserMessage: OptimisticUserMessage | null
	lastRunInput: string
	inputValue: string
	runAbortController: AbortController | null

	// paging
	messageSkip: number
	hasMoreMessages: boolean
	isLoadingOlderMessages: boolean

	// scroll
	readonly scrollContainer: HTMLElement | null
	autoScroll: boolean

	// tools (reactive tracker - no tick counter needed)
	readonly toolTracker: ToolExecutionTracker
	readonly fetchedToolEventMessageIds: SvelteSet<string>
	readonly toolEventsPendingIds: SvelteSet<string>
	toolEventsInFlight: boolean

	// delete confirmation
	confirmDeleteMessage: { id: string; preview: string } | null
	isDeletingMessage: boolean
	deleteMessageError: string | null

	// attachment tray
	readonly pendingActions: Map<string, 'reveal' | 'reference'>
	readonly attachmentStates: SvelteMap<string, AttachmentStatus>
	readonly threadAttachments: ThreadAttachment[]

	// citations (message-scoped, accumulated from citation.sources WS events)
	readonly citationSources: SvelteMap<string, ApiCitation[]>
	citationTargetMessageId: string | null
	addCitationSources(citations: ApiCitation[]): void
	flushCitationsToMessage(messageId: string): void

	// realtime
	readonly typingUsers: SvelteSet<string>

	// derived
	readonly isTemporaryChat: boolean
	readonly currentUserId: string | null

	// coordinator-owned methods
	incrementActiveRun(): number
	rebuildRunBlocks(): void
	queueScrollToBottom(behavior?: 'auto' | 'smooth'): Promise<void>
}

/**
 * full public state returned by createChatState().
 * extends ChatContext with page-specific UI state, derived values, and action methods.
 */
export interface ChatState extends ChatContext {
	// page-specific state
	isThreadLoading: boolean
	hasLoadedBranch: boolean
	inputOverlay: HTMLElement | null
	initialScrollDone: boolean
	lastThreadId: string | null
	inputOverlayHeight: number
	scrollContainer: HTMLElement | null

	// derived (readonly)
	readonly runBlocks: RunBlock[]
	readonly showThreadLoader: boolean
	readonly hasRenderableMessages: boolean
	readonly hasActiveStreamingToolCalls: boolean
	readonly agentNameById: Map<string, string>
	readonly agentAvatarById: Map<string, string | null>

	// scroll
	handleScroll(): void
	scrollToBottom(behavior?: 'auto' | 'smooth'): void

	// thread lifecycle
	setThread(t: Thread | null): void
	clearThread(): void

	// tools
	getToolExecution(toolCallId: string): ToolExecution | undefined

	// attachment tray
	toggleAttachmentStatus(fileId: string, action: 'reveal' | 'reference'): void

	// delegated actions
	loadTree(threadId: string): Promise<boolean>
	handleSendMessage(content: string, modifiers?: RunModifiers): Promise<void>
	handleRegenerateMessage(parentId?: string | null, prompt?: string | null): Promise<void>
	handleStopGeneration(): void
	handleSaveEditMessage(messageId: string, newContent: string): Promise<void>
	handleSaveAsCopyMessage(messageId: string, newContent: string): Promise<void>
	resumeCreateAndRun(
		stream: AsyncGenerator<CreateAndRunStreamDelta, void, unknown>,
		threadId: string
	): Promise<{ resolvedThreadId: string } | void>
	requestDeleteUserMessage(messageId: string): void
	deleteUserMessage(messageId: string): Promise<boolean>
	switchBranch(messageId: string, direction: 'prev' | 'next'): Promise<void>
	findRunUserMessage(block: RunBlock): string | null
	subscribeToChatEvents(threadId: string): () => void
	sendTypingEvent(threadId: string, typing: boolean): void
}

/** per-stream context for processDelta - tracks the assistant parent pointer */
export interface StreamDeltaContext {
	runId: number
	threadId: string
	getAssistantParentId(): string | null
	setAssistantParentId(id: string | null): void
}
