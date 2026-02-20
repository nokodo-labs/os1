/**
 * shared type definitions for the chat module.
 * ChatContext bridges reactive $state in the coordinator to extracted modules.
 */

import type { Thread } from '$lib/stores/chat.svelte'
import type { ToolExecutionTracker } from '$lib/tools'
import type { SvelteMap, SvelteSet } from 'svelte/reactivity'
import type { ApiMessage, StreamingAssistantState } from './helpers'

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

	// tools
	readonly toolTracker: ToolExecutionTracker
	toolTick: number
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

/** per-stream context for processDelta — tracks the assistant parent pointer */
export interface StreamDeltaContext {
	runId: number
	threadId: string
	getAssistantParentId(): string | null
	setAssistantParentId(id: string | null): void
}
