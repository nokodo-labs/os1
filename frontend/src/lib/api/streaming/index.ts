/**
 * Manual types and clients for streaming endpoints not covered by OpenAPI codegen.
 * - SSE: /threads/{id}/run/stream
 * - WebSocket: /events/stream
 */

export {
	runChatStream,
	type ChatStreamDelta,
	type ChatStreamOptions,
	type ContentPart,
	type StreamedMessage,
	type StreamError,
	type TextDelta,
} from './chatStream'
export {
	EventStreamClient,
	eventStreamClient,
	type StreamEvent,
	type StreamMessage,
} from './eventStream'
