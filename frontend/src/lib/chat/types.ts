/**
 * shared type definitions for the chat module.
 * all chat-related types live here - types should not be defined in utility
 * modules like helpers.ts or attachments.ts.
 */

import type {
    CreateAndRunStreamDelta,
    ResourceAttachment,
    RunAttachmentType,
} from '$lib/api/streaming/chatStream'
import type { components } from '$lib/api/types'
import type { ResourceItem } from '$lib/components/widgets/types'
import type { Thread } from '$lib/stores/chat.svelte'
import type { ToolCall, ToolExecution, ToolExecutionTracker } from '$lib/tools'
import type { SvelteMap, SvelteSet } from 'svelte/reactivity'

// --- API types ---

export type ApiMessage = components['schemas']['Message']
export type ApiCitation = components['schemas']['Citation']
export type { ResourceAttachment } from '$lib/api/streaming/chatStream'

// --- content part types ---

/** an image or video content part with resolved URL */
export interface MediaContentPart {
	type: 'image' | 'video' | 'audio'
	url: string
	filename?: string | null
	mediaType?: string | null
	fileId?: string
}

/** a non-media file content part */
export interface FileContentPart {
	type: 'file'
	url?: string | null
	filename?: string | null
	mediaType?: string | null
	fileId?: string
}

// --- attachment types ---

export type AttachmentMediaCategory = 'image' | 'audio' | 'video' | 'file'

/** a file that has been uploaded and is pending inclusion in the next message */
export interface PendingAttachment {
	fileId: string
	resourceType: RunAttachmentType
	filename: string
	mediaType: string
	category: AttachmentMediaCategory
	/** local object URL for preview (images/video) - revoked after send */
	previewUrl?: string
	/** how this attachment was added - 'upload' = new file, 'resource' = existing resource */
	source: 'upload' | 'resource'
	/** rich display resource captured at attach time (resource picks) for tray rendering */
	resource?: ResourceItem
}

/** modifiers toggled by the user in AddContext */
export interface RunModifiers {
	webSearch: boolean
	thinkLonger: boolean
	generateImage: boolean
	extraPlugins: string[]
	attachments: PendingAttachment[]
}

/** structured optimistic user message - mirrors what was sent to the API */
export interface OptimisticUserMessage {
	text: string
	attachments: PendingAttachment[]
	timestamp: Date
}

export interface PendingRunInput {
	text?: string | null
	attachments?: ResourceAttachment[]
}

export type SteeringState = 'queued' | 'injected' | 'dropped'

export interface QueuedSteeringMessage {
	id: string
	clientSteeringId?: string
	runId: string
	content: ApiMessage['content']
	text: string
	attachments: PendingAttachment[]
	createdAt: Date
	message: ApiMessage | null
	deliveryState?: 'sending' | 'queued'
	input?: PendingRunInput
}

/** allowed tool_choice values that can be forced by the user */
export type ToolChoiceValue = 'agentic_web_search' | 'think' | 'generate_image'

// --- run/block types ---

export type RunActivityPhase = 'started' | 'progress' | 'ended'
export type RunActivityOutcome = 'success' | 'error' | 'cancelled'
export type RunActivityStatus = 'running' | RunActivityOutcome

export interface RunActivityEvent {
	id: string
	type: string
	phase: RunActivityPhase
	messageId: string
	runId: string
	activityId: string
	activityType: string
	status: RunActivityStatus
	timestamp: Date
	title?: string
	message?: string
	progress?: number
	outcome?: RunActivityOutcome
	error?: string
}

export interface RunActivityState extends Omit<RunActivityEvent, 'type' | 'phase' | 'timestamp'> {
	key: string
	eventIds: string[]
	startedAt: Date
	updatedAt: Date
	endedAt?: Date
}

export type RunItem =
	| { kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
	| { kind: 'optimistic_user'; text: string; attachments: PendingAttachment[]; timestamp: Date }
	| { kind: 'run_activity'; activity: RunActivityState }
	| { kind: 'assistant'; message: ApiMessage }
	| { kind: 'tool'; toolCallId: string }
	| { kind: 'streaming_assistant' }
	| { kind: 'streaming_tool'; toolCallId: string }

export interface RunBlock {
	runId: string
	agentId: string | null
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
	readonly queuedSteeringMessages: QueuedSteeringMessage[]
	lastRunInput: string
	inputValue: string
	runAbortController: AbortController | null
	stageQueuedSteeringMessage(message: QueuedSteeringMessage): void
	removeQueuedSteeringMessage(messageId: string): void
	confirmQueuedSteeringMessage(
		clientSteeringId: string,
		messageId: string,
		runId: string,
		message?: ApiMessage
	): boolean
	flushPendingSteeringMessages(runId: string | null, parentId: string | null): Promise<void>
	injectQueuedSteeringMessage(
		messageId: string,
		message?: ApiMessage,
		options?: { runId?: string; parentId?: string | null; createdAt?: string | null }
	): boolean
	setSteeringParentOverride(runId: string, parentId: string): void
	consumeSteeringParentOverride(runId: string | null): string | null

	// paging
	messageSkip: number
	hasMoreMessages: boolean
	isLoadingOlderMessages: boolean

	// scroll
	readonly scrollContainer: HTMLElement | null
	autoScroll: boolean

	// tools (reactive tracker - no tick counter needed)
	readonly toolTracker: ToolExecutionTracker
	readonly fetchedEventMessageIds: SvelteSet<string>
	readonly eventMessageIdsPending: SvelteSet<string>
	eventsInFlight: boolean

	// run activities
	readonly runActivities: SvelteMap<string, RunActivityState>
	processRunActivityEvent(event: RunActivityEvent): void

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
	readonly threadLoadToken: number
	beginThreadLoad(threadId: string): number
	isThreadLoadCurrent(threadId: string, token: number): boolean
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
	dropSteering(runId: string, messageId: string): Promise<void>
	switchBranch(messageId: string, direction: 'prev' | 'next'): Promise<void>
	findRunUserMessage(block: RunBlock): string | null
	subscribeToChatEvents(threadId: string): () => void
	sendTypingEvent(threadId: string, typing: boolean): void
}

/** per-stream context for processDelta - tracks the assistant parent pointer */
export interface StreamDeltaContext {
	runId: number
	threadId: string
	agentId: string | null
	getAssistantParentId(): string | null
	setAssistantParentId(id: string | null): void
	/**
	 * when set, this stream is a catchup replay (resume after a transport drop)
	 * that re-sends frames from the start. assistant text is reconstructed into
	 * `replayContent` per message and reconciled against the already-rendered
	 * content so the bubble is never blanked - it only changes when the replay
	 * extends past or diverges from what is shown.
	 */
	replayContent?: Map<string, string>
}
