<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Ban,
		Circle,
		CircleCheck,
		Clock3,
		LoaderCircle,
		RefreshCw,
		TriangleAlert,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'
	import { untrack } from 'svelte'

	type Task = Schemas['Task']
	type TaskStatus = Schemas['TaskStatus']

	type Props = {
		open: boolean
		taskId: string | null
		initialTask?: Task | null
		onUpdated?: (task: Task) => void
	}

	let { open = $bindable(false), taskId, initialTask = null, onUpdated }: Props = $props()

	let task = $state<Task | null>(null)
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let isCancelling = $state(false)
	let actionError = $state<string | null>(null)
	let reloadToken = $state(0)
	let loadRequestId = 0

	function close() {
		open = false
		actionError = null
	}

	function refresh() {
		reloadToken += 1
	}

	function isActiveStatus(statusValue: TaskStatus): boolean {
		return statusValue === 'pending' || statusValue === 'running'
	}

	function formatDate(value: string | null | undefined): string {
		if (!value) return 'never'
		const date = new Date(value)
		if (Number.isNaN(date.getTime())) return 'unknown'
		return date.toLocaleString()
	}

	function jsonText(value: unknown): string {
		if (value === null || value === undefined) return '{}'
		return JSON.stringify(value, null, 2)
	}

	function metadataString(key: string): string | null {
		const value = task?.metadata_?.[key]
		return typeof value === 'string' && value.trim() ? value : null
	}

	function taskName(value: Task): string {
		return metadataString('task_name') ?? value.task_type.replaceAll('_', ' ')
	}

	function statusClass(statusValue: TaskStatus): string {
		if (statusValue === 'running') return 'border-lime-500/20 bg-lime-500/10 text-lime-300'
		if (statusValue === 'pending') return 'border-sky-500/20 bg-sky-500/10 text-sky-300'
		if (statusValue === 'complete')
			return 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300'
		if (statusValue === 'failed') return 'border-red-500/20 bg-red-500/10 text-red-300'
		return 'border-zinc-600/40 bg-zinc-700/40 text-zinc-300'
	}

	async function cancelTask() {
		if (!task || !isActiveStatus(task.status)) return
		isCancelling = true
		actionError = null
		try {
			const updated = unwrap(
				await api.POST('/v1/tasks/{task_id}/cancel', {
					params: { path: { task_id: task.id } },
					body: { reason: 'cancelled from console' },
				})
			)
			task = updated
			onUpdated?.(updated)
		} catch (err) {
			actionError = err instanceof Error ? err.message : 'failed to cancel task'
		} finally {
			isCancelling = false
		}
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!taskId) return
		const currentTaskId = taskId
		const currentReloadToken = reloadToken
		void currentReloadToken
		const requestId = ++loadRequestId
		let cancelled = false
		task = untrack(() => initialTask)
		isLoading = true
		error = null
		actionError = null
		api.GET('/v1/tasks/{task_id}', { params: { path: { task_id: currentTaskId } } })
			.then((result) => unwrap(result))
			.then((loaded) => {
				if (cancelled || requestId !== loadRequestId) return
				task = loaded
				untrack(() => onUpdated?.(loaded))
			})
			.catch((err: unknown) => {
				if (cancelled || requestId !== loadRequestId) return
				error = err instanceof Error ? err.message : 'failed to load task'
			})
			.finally(() => {
				if (cancelled || requestId !== loadRequestId) return
				isLoading = false
			})
		return () => {
			cancelled = true
		}
	})
</script>

<Dialog.Root
	bind:open
	onOpenChange={(next) => {
		if (!next) close()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-[min(980px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-xl"
		>
			<div
				class="flex shrink-0 items-start justify-between gap-4 border-b border-zinc-800 px-5 py-4"
			>
				<div class="min-w-0 flex-1">
					<Dialog.Title class="truncate text-base font-semibold">
						{task ? taskName(task) : 'task details'}
					</Dialog.Title>
					<Dialog.Description class="mt-1 truncate text-xs text-zinc-500">
						{taskId ?? ''}
					</Dialog.Description>
				</div>
				<div class="flex shrink-0 items-center gap-2">
					<Button
						variant="ghost"
						size="icon"
						class="rounded-xl"
						onclick={refresh}
						disabled={isLoading}
					>
						<RefreshCw class="h-4 w-4 {isLoading ? 'animate-spin' : ''}" />
					</Button>
					<Button variant="ghost" size="icon" class="rounded-xl" onclick={close}>
						<X class="h-4 w-4" />
					</Button>
				</div>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
				{#if isLoading && !task}
					<div class="flex items-center justify-center py-16">
						<NokodoLoader />
					</div>
				{:else if error}
					<div
						class="rounded-xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				{:else if task}
					<div class="space-y-4">
						<div
							class="flex flex-col gap-3 rounded-xl border border-zinc-800 bg-zinc-900 p-4 md:flex-row md:items-center md:justify-between"
						>
							<div class="flex min-w-0 items-center gap-3">
								<div
									class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-950 text-zinc-300"
								>
									{#if task.status === 'running'}
										<LoaderCircle class="h-5 w-5 animate-spin text-lime-400" />
									{:else if task.status === 'pending'}
										<Clock3 class="h-5 w-5 text-sky-400" />
									{:else if task.status === 'complete'}
										<CircleCheck class="h-5 w-5 text-emerald-400" />
									{:else if task.status === 'failed'}
										<TriangleAlert class="h-5 w-5 text-red-400" />
									{:else}
										<Ban class="h-5 w-5 text-zinc-400" />
									{/if}
								</div>
								<div class="min-w-0">
									<div class="truncate text-sm font-medium text-zinc-100">
										{taskName(task)}
									</div>
									<div class="mt-1 truncate text-xs text-zinc-500">
										{task.task_type.replaceAll('_', ' ')}
									</div>
								</div>
							</div>
							<div class="flex shrink-0 flex-wrap items-center gap-2">
								<span
									class="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs {statusClass(
										task.status
									)}"
								>
									<Circle class="h-3 w-3" />
									{task.status}
								</span>
								{#if isActiveStatus(task.status)}
									<Button
										variant="outline"
										class="rounded-xl border-red-900/60 text-red-200 hover:bg-red-950/40"
										onclick={cancelTask}
										disabled={isCancelling}
									>
										<Ban class="mr-1.5 h-4 w-4" />
										{isCancelling ? 'cancelling...' : 'cancel'}
									</Button>
								{/if}
							</div>
						</div>

						{#if actionError}
							<div
								class="rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-sm text-red-200"
							>
								{actionError}
							</div>
						{/if}

						<div class="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
							<div class="space-y-4">
								<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
									<div class="text-sm font-medium text-zinc-100">fields</div>
									<div
										class="mt-3 grid gap-2 text-xs text-zinc-400 sm:grid-cols-2 lg:grid-cols-1"
									>
										<div class="break-all">
											<span class="text-zinc-500">id:</span>
											{task.id}
										</div>
										<div class="break-all">
											<span class="text-zinc-500">user:</span>
											{task.user_id}
										</div>
										<div class="break-all">
											<span class="text-zinc-500">thread:</span>
											{task.spawned_thread_id ?? 'none'}
										</div>
										<div>
											<span class="text-zinc-500">stage:</span>
											{task.stage ?? 'none'}
										</div>
										<div>
											<span class="text-zinc-500">progress:</span>
											{task.progress ?? 0}%
										</div>
									</div>
								</div>

								<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
									<div class="text-sm font-medium text-zinc-100">timeline</div>
									<div class="mt-3 grid gap-2 text-xs text-zinc-400">
										<div>
											<span class="text-zinc-500">created:</span>
											{formatDate(task.created_at)}
										</div>
										<div>
											<span class="text-zinc-500">started:</span>
											{formatDate(task.started_at)}
										</div>
										<div>
											<span class="text-zinc-500">last event:</span>
											{formatDate(task.last_event_at)}
										</div>
										<div>
											<span class="text-zinc-500">updated:</span>
											{formatDate(task.updated_at)}
										</div>
										<div>
											<span class="text-zinc-500">completed:</span>
											{formatDate(task.completed_at)}
										</div>
										<div>
											<span class="text-zinc-500">cancelled:</span>
											{formatDate(task.cancelled_at)}
										</div>
									</div>
								</div>
							</div>

							<div class="grid gap-4">
								<div class="rounded-xl border border-zinc-800 bg-zinc-900">
									<div
										class="border-b border-zinc-800 px-4 py-3 text-sm font-medium text-zinc-100"
									>
										metadata
									</div>
									<pre
										class="max-h-72 overflow-auto p-4 font-mono text-xs break-all whitespace-pre-wrap text-zinc-300">{jsonText(
											task.metadata_
										)}</pre>
								</div>
								<div class="rounded-xl border border-zinc-800 bg-zinc-900">
									<div
										class="border-b border-zinc-800 px-4 py-3 text-sm font-medium text-zinc-100"
									>
										result
									</div>
									<pre
										class="max-h-72 overflow-auto p-4 font-mono text-xs break-all whitespace-pre-wrap text-zinc-300">{jsonText(
											task.result
										)}</pre>
								</div>
							</div>
						</div>
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no task selected
					</div>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
