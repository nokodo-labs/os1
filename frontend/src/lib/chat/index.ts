// $lib/chat barrel - re-exports from all chat modules

// state factory
export { createChatState } from './createChatState.svelte'

// types
export type {
	AttachmentStatus,
	ChatContext,
	ChatState,
	StreamDeltaContext,
	ThreadAttachment,
} from './types'

// helpers (pure functions + types)
export {
	AUTO_SCROLL_BUFFER_PX,
	blockHasStreamingAssistant,
	buildAgentLookup,
	buildMessageChildren,
	buildRunBlocks,
	computeIsAtBottom,
	computeThreadAttachments,
	contentPartsToText,
	extractFileParts,
	extractMediaParts,
	getBlockFirstAssistant,
	getBlockResponseItems,
	getMessageCreatedAt,
	getRunId,
	groupResponseItems,
	hasAttachmentParts,
	sdkPartsToText,
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

// tree navigation
export {
	findRunUserMessage,
	getLatestLeaf,
	isOnStreamingBranch,
	switchBranch,
} from './treeNavigation'

// data loading
export {
	fetchEventsForThread,
	ingestMessages,
	loadOlderMessages,
	loadTree,
	syncCacheAfterRun,
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
export { sendTypingEvent, subscribeToChatEvents } from './eventSubscriptions'
