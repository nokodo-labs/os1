/**
 * Reactive tool execution tracker using Svelte 5 runes.
 *
 * Each ToolExecution is a deeply reactive object ($state). Components that
 * read `execution.status`, `execution.toolCall.arguments`, etc. will
 * automatically re-render when those values change — no manual tick counter
 * or {#key} block destruction needed.
 *
 * String argument fragments from streaming are accumulated in `rawArguments`
 * and parsed into `toolCall.arguments` on every chunk, so tool cards can
 * read partial JSON as it streams in.
 */

import { SvelteDate, SvelteMap } from 'svelte/reactivity'
import type { ToolCall, ToolEvent, ToolExecution, ToolResult, ToolStatus } from './index'

// ── internal reactive execution state ────────────────────────────────────

/**
 * Reactive wrapper around ToolExecution.
 * All mutable fields are $state so Svelte tracks reads/writes automatically.
 */
class ReactiveToolExecution {
	// tool call identity + arguments
	id: string
	name = $state('')
	rawArguments = $state('')
	arguments = $state<Record<string, unknown>>({})

	// lifecycle
	status = $state<ToolStatus>('pending')
	events = $state<ToolEvent[]>([])
	startedAt = $state<Date | undefined>(undefined)
	completedAt = $state<Date | undefined>(undefined)
	progress = $state<number | undefined>(undefined)
	lastMessage = $state<string | undefined>(undefined)
	error = $state<string | undefined>(undefined)
	result = $state<ToolResult | undefined>(undefined)

	constructor(id: string, name: string, args: Record<string, unknown> | string) {
		this.id = id
		this.name = name
		if (typeof args === 'string') {
			this.rawArguments = args
			this.arguments = tryParseJson(args)
		} else {
			this.rawArguments = Object.keys(args).length > 0 ? JSON.stringify(args) : ''
			this.arguments = args
		}
		this.startedAt = new SvelteDate()
	}

	/** Snapshot into the plain ToolExecution interface for external consumers. */
	get snapshot(): ToolExecution {
		return {
			toolCall: {
				id: this.id,
				name: this.name,
				arguments: this.arguments,
			},
			status: this.status,
			events: this.events,
			startedAt: this.startedAt,
			completedAt: this.completedAt,
			progress: this.progress,
			lastMessage: this.lastMessage,
			error: this.error,
			result: this.result,
		}
	}
}

// ── public tracker ───────────────────────────────────────────────────────

/**
 * Manages tool execution state across multiple tool calls using Svelte 5 runes.
 *
 * Usage:
 * ```ts
 * const tracker = new ToolExecutionTracker()
 * // in template — reads are automatically tracked:
 * const exec = tracker.get(toolCallId)
 * // exec.status, exec.arguments, etc. are all reactive
 * ```
 */
export class ToolExecutionTracker {
	/** Reactive map — Svelte tracks .get(), .has(), iteration, etc. */
	private readonly executions = new SvelteMap<string, ReactiveToolExecution>()

	// ── registration ─────────────────────────────────────────────────────

	/**
	 * Register or update a tool call from the assistant message stream.
	 *
	 * Handles both:
	 * - Object arguments (from finalized messages / API responses)
	 * - String arguments (from streaming chunks — accumulated incrementally)
	 */
	registerToolCall(toolCall: ToolCall): void {
		const existing = this.executions.get(toolCall.id)

		if (existing) {
			// update name if provided
			if (toolCall.name) existing.name = toolCall.name

			// merge arguments
			const incomingArgs = toolCall.arguments
			if (typeof incomingArgs === 'string') {
				// streaming string fragment — append
				existing.rawArguments += incomingArgs
				existing.arguments = tryParseJson(existing.rawArguments)
			} else if (Object.keys(incomingArgs).length > 0) {
				// finalized object arguments (from persisted messages)
				existing.arguments = { ...existing.arguments, ...incomingArgs }
				existing.rawArguments = JSON.stringify(existing.arguments)
			}
			return
		}

		// new tool call
		const exec = new ReactiveToolExecution(toolCall.id, toolCall.name, toolCall.arguments)
		this.executions.set(toolCall.id, exec)
	}

	/**
	 * Register a tool call with raw string arguments from streaming.
	 * This is the preferred path for streaming chunks where arguments
	 * arrive as partial JSON string fragments.
	 */
	registerStreamingToolCall(id: string, name: string, rawArgs: string): void {
		const existing = this.executions.get(id)

		if (existing) {
			if (name) existing.name = name
			if (rawArgs) {
				existing.rawArguments += rawArgs
				existing.arguments = tryParseJson(existing.rawArguments)
			}
			return
		}

		const exec = new ReactiveToolExecution(id, name, rawArgs)
		this.executions.set(id, exec)
	}

	// ── events ───────────────────────────────────────────────────────────

	/** Process a real-time tool event (progress, custom, notification). */
	processEvent(event: ToolEvent): void {
		let exec = this.executions.get(event.toolCallId)

		if (!exec) {
			exec = new ReactiveToolExecution(event.toolCallId, event.toolName, {})
			this.executions.set(event.toolCallId, exec)
		}

		exec.events = [...exec.events, event]

		// backfill name from event
		if (!exec.name && event.toolName) exec.name = event.toolName

		// merge event-provided arguments
		if (event.data.toolCallArgs && Object.keys(event.data.toolCallArgs).length > 0) {
			exec.arguments = { ...event.data.toolCallArgs, ...exec.arguments }
		}

		// update status
		switch (event.type) {
			case 'tool.progress':
				exec.status = 'running'
				if (event.data.progress !== undefined) exec.progress = event.data.progress
				if (event.data.message) exec.lastMessage = event.data.message
				break
			case 'tool.custom':
				if (exec.status === 'pending') exec.status = 'running'
				if (event.data.description) exec.lastMessage = event.data.description
				break
			case 'tool.notification':
				if (event.data.description) exec.lastMessage = event.data.description
				break
		}
	}

	// ── results ──────────────────────────────────────────────────────────

	/** Register a tool result (tool message). */
	registerResult(result: ToolResult): void {
		const exec = this.executions.get(result.toolCallId)
		if (!exec) return

		exec.result = result
		exec.completedAt = new SvelteDate()

		if (result.isError) {
			exec.status = 'error'
			exec.error = result.output
		} else {
			exec.status = 'completed'
		}
	}

	// ── queries ──────────────────────────────────────────────────────────

	/**
	 * Get a reactive execution for a tool call.
	 * The returned object is deeply reactive — reading any property in a
	 * Svelte template will create a fine-grained subscription.
	 *
	 * Returns `ToolExecution`-shaped object (the ReactiveToolExecution class
	 * satisfies the interface via its public $state fields).
	 */
	get(toolCallId: string): ToolExecution | undefined {
		const exec = this.executions.get(toolCallId)
		if (!exec) return undefined
		// return the reactive object directly — components read $state fields
		return {
			get toolCall() {
				return {
					id: exec.id,
					name: exec.name,
					arguments: exec.arguments,
				}
			},
			get status() {
				return exec.status
			},
			get events() {
				return exec.events
			},
			get startedAt() {
				return exec.startedAt
			},
			get completedAt() {
				return exec.completedAt
			},
			get progress() {
				return exec.progress
			},
			get lastMessage() {
				return exec.lastMessage
			},
			get error() {
				return exec.error
			},
			get result() {
				return exec.result
			},
		}
	}

	/**
	 * Get the raw arguments string for a tool call (for streaming display).
	 * This is the accumulated raw JSON string before parsing.
	 */
	getRawArguments(toolCallId: string): string {
		return this.executions.get(toolCallId)?.rawArguments ?? ''
	}

	/** @deprecated Use get() instead. Kept for migration compatibility. */
	getExecution(toolCallId: string): ToolExecution | undefined {
		return this.get(toolCallId)
	}

	/** Get all executions as plain snapshots. */
	getAllExecutions(): ToolExecution[] {
		return Array.from(this.executions.values()).map((e) => e.snapshot)
	}

	/** Check if a tool call exists and is in a running/pending state. */
	isActive(toolCallId: string): boolean {
		const exec = this.executions.get(toolCallId)
		return exec !== undefined && (exec.status === 'pending' || exec.status === 'running')
	}

	/** Check if any tool call is active. */
	get hasActive(): boolean {
		for (const exec of this.executions.values()) {
			if (exec.status === 'pending' || exec.status === 'running') return true
		}
		return false
	}

	/** Number of tracked executions. */
	get size(): number {
		return this.executions.size
	}

	/** Clear all tracked executions. */
	clear(): void {
		this.executions.clear()
	}
}

// ── helpers ──────────────────────────────────────────────────────────────

/**
 * Try to parse a (possibly incomplete) JSON string into an object.
 * Returns empty object if the string is unparseable.
 * Streaming chunks often produce partial JSON like `{"tho` — this
 * gracefully handles that case.
 */
function tryParseJson(raw: string): Record<string, unknown> {
	if (!raw) return {}
	try {
		const parsed = JSON.parse(raw)
		if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
			return parsed as Record<string, unknown>
		}
	} catch {
		// partial JSON — attempt to extract complete key-value pairs
		return extractPartialJsonFields(raw)
	}
	return {}
}

/**
 * Extract fully-formed key-value pairs from a partial JSON string.
 * Example: `{"thought": "let me think", "next` → { thought: "let me think" }
 *
 * This allows tool cards to start rendering individual fields as soon as
 * their values are complete, even while the overall JSON is still streaming.
 */
function extractPartialJsonFields(raw: string): Record<string, unknown> {
	const result: Record<string, unknown> = {}

	// match complete "key": value pairs
	// supports string, number, boolean, null values
	const pairRegex =
		/"([^"\\]*(?:\\.[^"\\]*)*)"\s*:\s*(?:("(?:[^"\\]*(?:\\.[^"\\]*)*)")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|true|false|null)/g

	let match: RegExpExecArray | null
	while ((match = pairRegex.exec(raw)) !== null) {
		const key = match[1]
		const fullMatch = match[0]
		const colonIdx = fullMatch.indexOf(':')
		const valueStr = fullMatch.slice(colonIdx + 1).trim()

		if (match[2] !== undefined) {
			// string value — unescape
			try {
				result[key] = JSON.parse(match[2])
			} catch {
				result[key] = match[2].slice(1, -1)
			}
		} else if (match[3] !== undefined) {
			result[key] = Number(match[3])
		} else if (valueStr === 'true') {
			result[key] = true
		} else if (valueStr === 'false') {
			result[key] = false
		} else if (valueStr === 'null') {
			result[key] = null
		}
	}

	return result
}
