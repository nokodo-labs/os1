// $lib/chat barrel - re-exports from all chat modules

// state factory
export { createChatState } from './createChatState.svelte'

// types
export type {
	ChatContext,
	ChatState,
	OptimisticUserMessage,
	QueuedSteeringMessage,
	RunActivityEvent,
	RunActivityOutcome,
	RunActivityPhase,
	RunActivityState,
	RunActivityStatus,
	SteeringState,
	StreamDeltaContext,
} from './types'

// helpers (pure functions + types)
export {
	AUTO_SCROLL_BUFFER_PX,
	blockHasStreamingAssistant,
	branchAlternativeCount,
	buildAgentLookup,
	buildMessageChildren,
	buildRunBlocks,
	computeBlockCitations,
	computeIsAtBottom,
	contentPartsToText,
	extractAttachmentRefs,
	extractFileParts,
	extractMediaParts,
	getBlockFirstAssistant,
	getBlockResponseItems,
	getBlockSystemEvents,
	getBlockTimeHeader,
	getMessageCreatedAt,
	getRunId,
	getUserRunItemTimestamp,
	groupResponseItems,
	hasAttachmentParts,
	isPlaceholderMessageId,
	pendingAttachmentsToFileParts,
	pendingAttachmentsToMediaParts,
	sdkPartsToText,
	siblingIdsOfKind,
	upsertToolCalls,
	type ApiMessage,
	type BuildRunBlocksInput,
	type BuildRunBlocksResult,
	type FileContentPart,
	type MediaContentPart,
	type ResponseSegment,
	type RunBlock,
	type RunItem,
	type StreamingAssistantState,
} from './helpers'

// stream processing
export { consumeStream, processDelta, resumeCreateAndRun, runThreadStream } from './streamProcessor'

export {
	parseRunActivityEvent,
	reduceRunActivityEvent,
	RUN_ACTIVITY_EVENT_PREFIX,
	runActivityKey,
} from './runActivities'

// durable run failures
export {
	isFailureOutstanding,
	parseRunFailureEvent,
	RUN_ERROR_EVENT_TYPE,
	runFailureLabel,
} from './runFailures'

// inline system rows (membership, renames) + the beginning-of-chat header
export {
	beginningOfChatSegments,
	CHAT_SYSTEM_EVENT_TYPES,
	parseChatSystemEvents,
	systemEventSegments,
	systemEventUserIds,
	type BeginningOfChatInput,
	type ChatSystemEvent,
	type ChatSystemEventKind,
	type SystemNameResolver,
	type SystemRowSegment,
} from './systemEvents'

// transcript time headers + the time a receipt carries
export {
	clockTime,
	dayStamp,
	formatTimeHeader,
	needsTimeHeader,
	receiptStamp,
	RECEIPT_STAMP_GAP_MS,
	timeHeaderSegments,
	TIME_HEADER_GAP_MS,
} from './chatTimestamps'

// message-author identity, resolved from the thread roster
export {
	buildParticipantIndex,
	composingFaces,
	resolveMessageAuthor,
	type MessageAuthor,
} from './participants'

// read receipts, derived from live read cursors
export {
	cursorCoversMessage,
	messageReadState,
	messageReceipt,
	readBy,
	readCompletedAt,
	receiptAudience,
	type MessageReadState,
	type MessageReceipt,
	type ReadCursor,
} from './readReceipts'

// tree navigation
export {
	findRunUserMessage,
	getLatestLeaf,
	isOnStreamingBranch,
	reparentSuccessors,
	switchBranch,
} from './treeNavigation'

// data loading
export {
	fetchEventsForThread,
	fetchThreadAccessLevel,
	ingestMessages,
	loadOlderMessages,
	loadTree,
	syncCacheAfterRun,
	ThreadNotFoundError,
} from './dataLoader'

// user actions
export {
	deleteUserMessage,
	handleRegenerateMessage,
	handleSaveAsCopyMessage,
	handleSaveEditMessage,
	handleSendMessage,
	handleStopGeneration,
	requestDeleteUserMessage,
} from './userActions'

// event subscriptions
export { sendTypingEvent, subscribeToChatEvents } from './eventSubscriptions.svelte'

// outgoing typing signal
export { createTypingSignal, TYPING_HEARTBEAT_MS, type TypingSignal } from './typingSignal'

// thread actions
export { deleteThread, unarchiveThread, updateThread } from './threadActions'
