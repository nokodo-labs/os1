/**
 * shared type definitions for the chat module.
 * all chat-related types live here - types should not be defined in utility
 * modules like helpers.ts or attachments.ts.
 */

import type {
	CreateAndRunStreamDelta,
	RunAttachmentType,
	RunInput,
} from '$lib/api/streaming/chatStream'
import type { components } from '$lib/api/types'
import type { ResourceItem } from '$lib/components/widgets/types'
import type { Thread } from '$lib/stores/chat.svelte'
import type { ToolCall, ToolExecution, ToolExecutionTracker } from '$lib/tools'
import type { SvelteMap, SvelteSet } from 'svelte/reactivity'
import type { LoadTreeOptions } from './dataLoader'
import type { MessageAuthor } from './participants'
import type { ChatSystemEvent } from './systemEvents'

// --- API types ---

export type ApiMessage = components['schemas']['Message']
export type ApiCitation = components['schemas']['Citation']
export type { ResourceAttachment } from '$lib/api/streaming/chatStream'

/**
 * opt-in for thread/message deletes: also delete the resources that originated
 * in the deleted messages. attached resources are never deleted.
 */
export type DeleteOriginatedOptions = {
	deleteOriginatedResources?: boolean
}

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
	/**
	 * message this one answers. a semantic anchor for the quote preview only:
	 * it never places the message in the tree, which is what `splice` does.
	 */
	replyToMessageId?: string | null
	/**
	 * agent explicitly armed for THIS send, which turns it into a run instead of
	 * a plain post. an invocation, never a mention, and never the composer's
	 * global selection - the user armed exactly one agent for exactly one send.
	 */
	invokeAgentId?: string | null
}

/** structured optimistic user message - mirrors what was sent to the API */
export interface OptimisticUserMessage {
	text: string
	attachments: PendingAttachment[]
	timestamp: Date
	/**
	 * the request never reached the backend, so nothing was persisted and no
	 * event will ever arrive. transient: the bubble says so instead of waiting
	 * forever on a reconciliation that cannot come.
	 */
	deliveryFailed?: boolean
}

/** the exact payload a queued steering message will be re-sent with. */
export type PendingRunInput = RunInput

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

/** why a run stopped without answering. closed set - render from it, never
 * display raw text. */
export type RunFailureReason = 'cancelled' | 'provider_error' | 'never_started' | 'not_delivered'

/**
 * a durable `run.error`, anchored to the message the agent was answering.
 *
 * immutable: whether it still stands is DERIVED from the conversation (did that
 * agent answer on that anchor afterwards), never stored. a retry that fails
 * again appends a second entry rather than rewriting this one.
 */
export interface RunFailureEntry {
	/** event id - the dedupe key, since the same failure arrives live and on reload. */
	id: string
	threadId: string
	agentId: string
	reason: RunFailureReason
	/** null when no run ever existed for the agent. */
	runId: string | null
	/** message the failure renders under. */
	anchorMessageId: string | null
	/** partial output the run produced; renders as a normal message. */
	partialMessageId: string | null
	createdAt: Date
}

export type RunItem =
	| { kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
	| {
			kind: 'optimistic_user'
			text: string
			attachments: PendingAttachment[]
			timestamp: Date
			deliveryFailed?: boolean
	  }
	| { kind: 'run_activity'; activity: RunActivityState }
	| { kind: 'assistant'; message: ApiMessage }
	| { kind: 'tool'; toolCallId: string }
	| { kind: 'streaming_assistant' }
	| { kind: 'streaming_tool'; toolCallId: string }
	| { kind: 'run_failure'; failure: RunFailureEntry }
	/** a centered system row; it owns its block, so it never shares one with a bubble. */
	| { kind: 'system_event'; event: ChatSystemEvent }
	/** a centered time header, dropped where the conversation went quiet. */
	| { kind: 'time_header'; at: Date }

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
	/** whether this client queued the message as text steering (a ghost bubble). */
	ownsSteeringMessage(messageId: string): boolean
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

	// entrance animation marks: a message that arrived live from another
	// session is marked once by the WS handler, then consumed (once) by the
	// view to play the fallback entrance. history/branch/paging never mark.
	markMessageEntrance(id: string): void
	consumeMessageEntrance(id: string): boolean

	// paging
	messageSkip: number
	hasMoreMessages: boolean
	isLoadingOlderMessages: boolean
	/** whether the branch continues past the loaded window toward its leaf. */
	hasNewerMessages: boolean
	isLoadingNewerMessages: boolean

	/** cursor for the next page toward the branch root; null = root reached.
	 *
	 * depth is counted from the branch leaf, so every offset shifts the moment
	 * anyone appends. scroll with this, never with `skip`.
	 */
	branchCursorTowardRoot: string | null

	/** cursor for the next page toward the branch leaf; null = tail reached. */
	branchCursorTowardLeaf: string | null

	/** message this load opened at, for the view to reveal. null = live tail. */
	initialAnchorMessageId: string | null

	/** branch alternatives per forked message, from the loaded pages. */
	readonly siblingCounts: SvelteMap<string, number>

	// scroll
	readonly scrollContainer: HTMLElement | null
	autoScroll: boolean
	/** re-measure overflow after a content or viewport size change. */
	measureScrollable(): void

	// tools (reactive tracker - no tick counter needed)
	readonly toolTracker: ToolExecutionTracker
	readonly fetchedEventMessageIds: SvelteSet<string>
	readonly eventMessageIdsPending: SvelteSet<string>
	eventsInFlight: boolean

	// run activities
	readonly runActivities: SvelteMap<string, RunActivityState>
	processRunActivityEvent(event: RunActivityEvent): void

	/** durable run failures, keyed by event id (the dedupe key). */
	readonly runFailures: SvelteMap<string, RunFailureEntry>
	recordRunFailure(failure: RunFailureEntry): void

	/** inline system rows, keyed by event id - the same one arrives live and on reload. */
	readonly systemEvents: SvelteMap<string, ChatSystemEvent>
	recordSystemEvent(event: ChatSystemEvent): void

	// citations (message-scoped, accumulated from citation.sources WS events)
	readonly citationSources: SvelteMap<string, ApiCitation[]>
	citationTargetMessageId: string | null
	addCitationSources(citations: ApiCitation[]): void
	flushCitationsToMessage(messageId: string): void

	// derived
	readonly isTemporaryChat: boolean
	readonly currentUserId: string | null

	// coordinator-owned methods
	readonly threadLoadToken: number
	beginThreadLoad(threadId: string): number
	isThreadLoadCurrent(threadId: string, token: number): boolean
	incrementActiveRun(): number
	rebuildRunBlocks(): void
	// streaming text coalescing: buffer a token delta (flushed once per frame),
	// or flush the buffer synchronously before any read of streamingAssistant.content.
	appendStreamingText(text: string): void
	flushStreamingText(): void
	queueScrollToBottom(behavior?: 'auto' | 'smooth'): Promise<void>
	// suppress the auto-scroll pin from flipping due to an imminent programmatic
	// scroll / scrollTop write (e.g. pagination anchor restore).
	markProgrammaticScroll(behavior?: 'auto' | 'smooth'): void
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
	/** no text token has arrived for a while, so the placeholder comes back. */
	readonly isStreamingTextStalled: boolean
	readonly agentNameById: Map<string, string>
	readonly agentAvatarById: Map<string, string | null>
	/** agents on this thread's roster, keyed by agent id. */
	readonly threadAgentById: Map<string, MessageAuthor>
	/** human identities for this thread, keyed by user id. */
	readonly participantById: Map<string, MessageAuthor>

	// scroll
	/** whether the transcript overflows its viewport at all. */
	readonly canScroll: boolean
	handleScroll(): void
	scrollToBottom(behavior?: 'auto' | 'smooth'): void
	/** content height changed with no gesture; re-pins if the view sits at the bottom. */
	onContentResize(): void
	// record a genuine user scroll gesture (wheel/touch) so the pin detaches on
	// scroll-up and re-evaluates from position even during streaming.
	onUserScrollGesture(direction?: 'up' | 'down' | 'unknown'): void

	// thread lifecycle
	setThread(t: Thread | null): void
	clearThread(): void

	// tools
	getToolExecution(toolCallId: string): ToolExecution | undefined

	// delegated actions
	loadTree(threadId: string, options?: LoadTreeOptions): Promise<boolean>
	handleSendMessage(content: string, modifiers?: RunModifiers): Promise<void>
	handleRegenerateMessage(
		parentId?: string | null,
		prompt?: string | null,
		agentId?: string | null
	): Promise<void>
	handleStopGeneration(): void
	handleSaveEditMessage(messageId: string, newContent: string): Promise<void>
	handleSaveAsCopyMessage(messageId: string, newContent: string): Promise<void>
	resumeCreateAndRun(
		stream: AsyncGenerator<CreateAndRunStreamDelta, void, unknown>,
		threadId: string
	): Promise<{ resolvedThreadId: string } | void>
	requestDeleteUserMessage(messageId: string): void
	deleteUserMessage(messageId: string, options?: DeleteOriginatedOptions): Promise<boolean>
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
