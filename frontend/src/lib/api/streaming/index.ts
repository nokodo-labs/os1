/**
 * manual types and clients for streaming endpoints not covered by OpenAPI codegen.
 * - SSE: /runs (POST), /threads/create_and_run (POST), /runs/{run_id}/stream (GET)
 * - WebSocket: /events/stream
 */
export type { ToolChoiceValue } from '$lib/chat/types'
export {
	resumeRunStream,
	runChatStream,
	runCreateAndRunStream,
	StreamHttpError,
	type ChatStreamDelta,
	type ChatStreamOptions,
	type ContentPart,
	type CreateAndRunStreamDelta,
	type CreateAndRunStreamOptions,
	type CreateAndRunThread,
	type ResourceAttachment,
	type ResumeRunStreamOptions,
	type RunAttachmentType,
	type RunInput,
	type StreamedMessage,
	type StreamError,
	type TextDelta,
	type ToolResultDelta,
	type UnknownSseEvent,
} from './chatStream'
export {
	EventStreamClient,
	eventStreamClient,
	type ConnectionStatus,
	type StreamEvent,
	type StreamMessage,
} from './eventStream.svelte'
export {
	SEARCH_RESOURCE_TYPES,
	searchStream,
	type SearchResourceType,
	type SearchResult,
	type SearchResultParent,
	type SearchResultType,
	type SearchStreamOptions,
} from './searchStream'
export { streamTask, type TaskStreamDelta } from './taskStream'
