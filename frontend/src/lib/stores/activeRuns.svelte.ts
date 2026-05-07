/**
 * global active runs store.
 * tracks all active agent runs across all threads for the current user
 * via the event stream. powers sidebar indicators and the run status orb.
 */

import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'

export interface ActiveRun {
	threadId: string
	runId: string
	agentId: string
	startedAt: number
}

export type GlobalRunState = 'idle' | 'running' | 'error'

class ActiveRunsStore {
	/** all currently active runs keyed by run_id */
	readonly runs = new SvelteMap<string, ActiveRun>()

	/** thread IDs that had a run error (cleared on next successful run or after timeout) */
	readonly errorThreadIds = new SvelteMap<string, number>()

	#unsubscribe: (() => void) | null = null
	#errorTimeouts = new Map<string, ReturnType<typeof setTimeout>>()

	/** overall run state for the current user */
	get state(): GlobalRunState {
		if (this.errorThreadIds.size > 0) return 'error'
		if (this.runs.size > 0) return 'running'
		return 'idle'
	}

	/** check if any run is active in a specific thread */
	hasActiveRuns(threadId: string): boolean {
		for (const run of this.runs.values()) {
			if (run.threadId === threadId) return true
		}
		return false
	}

	/** get active runs for a specific thread */
	getRunsForThread(threadId: string): ActiveRun[] {
		const result: ActiveRun[] = []
		for (const run of this.runs.values()) {
			if (run.threadId === threadId) result.push(run)
		}
		return result
	}

	/** get all thread IDs that have active runs */
	get activeThreadIds(): string[] {
		const ids: string[] = []
		for (const run of this.runs.values()) {
			if (!ids.includes(run.threadId)) {
				ids.push(run.threadId)
			}
		}
		return ids
	}

	init = (): void => {
		if (this.#unsubscribe) return
		this.#unsubscribe = eventStreamClient.subscribe(this.#handleEvent)
	}

	cleanup = (): void => {
		this.#unsubscribe?.()
		this.#unsubscribe = null
		this.runs.clear()
		this.errorThreadIds.clear()
		for (const t of this.#errorTimeouts.values()) clearTimeout(t)
		this.#errorTimeouts.clear()
	}

	#handleEvent = (msg: StreamMessage): void => {
		if (msg.type === 'runs.active') {
			const runs = ((msg as Record<string, unknown>).data ?? []) as Array<{
				thread_id: string
				run_id: string
				agent_id: string
			}>
			const activeRunIds = new SvelteSet<string>()
			for (const run of runs) {
				if (run.run_id && run.thread_id) {
					activeRunIds.add(run.run_id)
					this.runs.set(run.run_id, {
						threadId: run.thread_id,
						runId: run.run_id,
						agentId: run.agent_id,
						startedAt: Date.now(),
					})
				}
			}
			for (const runId of this.runs.keys()) {
				if (!activeRunIds.has(runId)) this.runs.delete(runId)
			}
		} else if (msg.type === 'run.started') {
			const data = ((msg as Record<string, unknown>).data ?? {}) as {
				thread_id?: string
				run_id?: string
				agent_id?: string
			}
			if (data.run_id && data.thread_id) {
				this.runs.set(data.run_id, {
					threadId: data.thread_id,
					runId: data.run_id,
					agentId: data.agent_id ?? '',
					startedAt: Date.now(),
				})
				// clear any error state for this thread since a new run started
				this.errorThreadIds.delete(data.thread_id)
				const t = this.#errorTimeouts.get(data.thread_id)
				if (t) {
					clearTimeout(t)
					this.#errorTimeouts.delete(data.thread_id)
				}
			}
		} else if (msg.type === 'run.completed') {
			const data = ((msg as Record<string, unknown>).data ?? {}) as {
				thread_id?: string
				run_id?: string
				status?: string
			}
			if (data.run_id) {
				this.runs.delete(data.run_id)
			}
		} else if (msg.type === 'run.error' || msg.type === 'run.failed') {
			const data = ((msg as Record<string, unknown>).data ?? {}) as {
				thread_id?: string
				run_id?: string
			}
			if (data.run_id) {
				const run = this.runs.get(data.run_id)
				const threadId = data.thread_id ?? run?.threadId
				this.runs.delete(data.run_id)
				if (threadId) {
					this.errorThreadIds.set(threadId, Date.now())
					// auto-clear error after 30s
					const prev = this.#errorTimeouts.get(threadId)
					if (prev) clearTimeout(prev)
					this.#errorTimeouts.set(
						threadId,
						setTimeout(() => {
							this.errorThreadIds.delete(threadId)
							this.#errorTimeouts.delete(threadId)
						}, 30_000)
					)
				}
			}
		}
	}
}

export const activeRunsStore = new ActiveRunsStore()
