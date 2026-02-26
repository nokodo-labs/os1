/**
 * shared type definitions for the chat module.
 * ChatContext is the internal contract for extracted module functions.
 * ChatState extends it with everything the page UI needs.
 */

import type { ChatStreamDelta } from '$lib/api/streaming'
import type { Thread } from '$lib/stores/chat.svelte'
import type { ToolExecution, ToolExecutionTracker } from '$lib/tools'
import type { SvelteMap, SvelteSet } from 'svelte/reactivity'
import type { ApiMessage, RunBlock, StreamingAssistantState } from './helpers'

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
	optimisticUserMessage: { content: string; timestamp: Date } | null
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

	// realtime
	readonly typingUsers: SvelteSet<string>
	readonly activeAgentRuns: SvelteMap<
		string,
		{ threadId: string; runId: string; agentId: string }
	>

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

	// delegated actions
	loadTree(threadId: string): Promise<boolean>
	handleSendMessage(content: string): Promise<void>
	handleRegenerateMessage(parentId?: string | null, prompt?: string | null): Promise<void>
	handleStopGeneration(): void
	handleSaveEditMessage(messageId: string, newContent: string): Promise<void>
	handleSaveAsCopyMessage(messageId: string, newContent: string): Promise<void>
	resumeCreateAndRun(
		stream: AsyncGenerator<ChatStreamDelta, void, unknown>,
		threadId: string
	): Promise<void>
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
