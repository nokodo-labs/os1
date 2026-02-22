/**
 * manual types and clients for streaming endpoints not covered by OpenAPI codegen.
 * - SSE: /runs (POST), /threads/create_and_run (POST), /runs/{run_id}/stream (GET)
 * - WebSocket: /events/stream
 */
export {
	resumeRunStream,
	runChatStream,
	runCreateAndRunStream,
	type ChatStreamDelta,
	type ChatStreamOptions,
	type ContentPart,
	type CreateAndRunStreamDelta,
	type CreateAndRunStreamOptions,
	type CreateAndRunThread,
	type ResumeRunStreamOptions,
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
export { searchStream, type SearchResult, type SearchStreamOptions } from './searchStream'
