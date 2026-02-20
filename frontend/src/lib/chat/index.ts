// $lib/chat barrel — re-exports from all chat modules

// state factory
export { createChatState } from './createChatState.svelte'

// types
export type { ChatContext, ChatState, StreamDeltaContext } from './types'

// helpers (pure functions + types)
export {
	AUTO_SCROLL_BUFFER_PX,
	blockHasStreamingAssistant,
	buildAgentLookup,
	buildMessageChildren,
	buildRunBlocks,
	computeIsAtBottom,
	contentPartsToText,
	getBlockFirstAssistant,
	getBlockResponseItems,
	getMessageCreatedAt,
	getRunId,
	sdkPartsToText,
	upsertToolCalls,
	type ApiMessage,
	type BuildRunBlocksInput,
	type BuildRunBlocksResult,
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
	fetchToolEventsForThread,
	ingestMessages,
	loadOlderMessages,
	loadTree,
	syncCacheAfterRun,
} from './dataLoader'

// user actions
export {
	deleteUserMessage,
	handleEditMessage,
	handleRegenerateMessage,
	handleSendMessage,
	handleStopGeneration,
	requestDeleteUserMessage,
} from './userActions'

// event subscriptions
export { sendTypingEvent, subscribeToChatEvents } from './eventSubscriptions'
