<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'
	import ManualTaskKickoffModal from '$lib/components/ManualTaskKickoffModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import TaskDetailsModal from '$lib/components/TaskDetailsModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import {
		Activity,
		AlertTriangle,
		ArrowDown,
		ArrowUp,
		Ban,
		CheckCircle2,
		Circle,
		Clock3,
		Hash,
		LoaderCircle,
		RefreshCw,
		Search,
		User,
		Wrench,
		XCircle,
	} from '@lucide/svelte'

	type Task = Schemas['Task']
	type TaskStatus = Schemas['TaskStatus']
	type SortKey = 'updated_at' | 'created_at' | 'status' | 'task_type' | 'stage' | 'last_event_at'
	type SortDir = 'asc' | 'desc'
	type HistoryStatusFilter = 'all' | 'complete' | 'failed' | 'cancelled'

	const historyStatusOptions: Array<{ value: HistoryStatusFilter; label: string }> = [
		{ value: 'all', label: 'all ended statuses' },
		{ value: 'complete', label: 'complete' },
		{ value: 'failed', label: 'failed' },
		{ value: 'cancelled', label: 'cancelled' },
	]

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'last_event_at', label: 'last event' },
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'status', label: 'status' },
		{ value: 'task_type', label: 'task type' },
		{ value: 'stage', label: 'stage' },
	]

	let liveTasks = $state<Task[]>([])
	let historyTasks = $state<Task[]>([])
	let ownerFilter = $state('')
	let threadFilter = $state('')
	let historyStatusFilter = $state<HistoryStatusFilter>('all')
	let sortKey = $state<SortKey>('last_event_at')
	let sortDir = $state<SortDir>('desc')
	let pageIndex = $state(0)
	let limit = $state(50)
	let refreshToken = $state(0)
	let isLoadingLive = $state(false)
	let isLoadingHistory = $state(false)
	let liveError = $state<string | null>(null)
	let historyError = $state<string | null>(null)
	let hasNext = $state(false)
	let taskDetailsOpen = $state(false)
	let selectedTaskId = $state<string | null>(null)
	let selectedTask = $state<Task | null>(null)
	let manualTasksOpen = $state(false)

	const liveCount = $derived(liveTasks.length)
	const endedCount = $derived(historyTasks.length)
	const isLoading = $derived(isLoadingLive || isLoadingHistory)

	function refresh() {
		refreshToken += 1
	}

	function resetHistoryPage() {
		pageIndex = 0
	}

	function setStatusFilter(next: string) {
		historyStatusFilter = next as HistoryStatusFilter
		resetHistoryPage()
	}

	function setSort(next: string) {
		sortKey = next as SortKey
		resetHistoryPage()
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
		resetHistoryPage()
	}

	function metadataString(task: Task, key: string): string | null {
		const value = task.metadata_?.[key]
		return typeof value === 'string' && value.trim() ? value : null
	}

	function taskName(task: Task): string {
		return metadataString(task, 'task_name') ?? task.task_type.replaceAll('_', ' ')
	}

	function taskContext(task: Task): string | null {
		return (
			task.spawned_thread_id ??
			metadataString(task, 'thread_id') ??
			metadataString(task, 'integration') ??
			metadataString(task, 'deployment_origin')
		)
	}

	function progressValue(task: Task): number {
		if (typeof task.progress === 'number') return Math.min(100, Math.max(0, task.progress))
		if (task.status === 'complete') return 100
		return 0
	}

	function formatDate(value: string | null | undefined): string {
		if (!value) return 'never'
		const date = new Date(value)
		if (Number.isNaN(date.getTime())) return 'unknown'
		return new Intl.DateTimeFormat(undefined, {
			month: 'short',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
		}).format(date)
	}

	function statusClass(statusValue: TaskStatus): string {
		if (statusValue === 'running') return 'bg-lime-500/10 text-lime-300 border-lime-500/20'
		if (statusValue === 'pending') return 'bg-sky-500/10 text-sky-300 border-sky-500/20'
		if (statusValue === 'complete')
			return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
		if (statusValue === 'failed') return 'bg-red-500/10 text-red-300 border-red-500/20'
		return 'bg-zinc-700/40 text-zinc-300 border-zinc-600/40'
	}

	function resultSummary(task: Task): string | null {
		const result = task.result
		if (!result) return null
		const errorValue = result.error
		if (typeof errorValue === 'string' && errorValue.trim()) return errorValue
		const messageValue = result.message
		if (typeof messageValue === 'string' && messageValue.trim()) return messageValue
		return null
	}

	function openTaskDetails(task: Task) {
		selectedTask = task
		selectedTaskId = task.id
		taskDetailsOpen = true
	}

	function replaceTask(updated: Task) {
		liveTasks = liveTasks.map((task) => (task.id === updated.id ? updated : task))
		historyTasks = historyTasks.map((task) => (task.id === updated.id ? updated : task))
		if (selectedTaskId === updated.id) selectedTask = updated
	}

	$effect(() => {
		if (!browser) return
		void refreshToken

		const userId = ownerFilter.trim()
		const threadId = threadFilter.trim()

		isLoadingLive = true
		liveError = null
		api.GET('/v1/tasks', {
			params: {
				query: {
					user_id: userId || undefined,
					spawned_thread_id: threadId || undefined,
					state_filter: 'active',
					skip: 0,
					limit: 20,
					sort_by: 'last_event_at',
					sort_dir: 'desc',
				},
			},
		})
			.then((result) => unwrap(result))
			.then((loaded) => {
				liveTasks = loaded
			})
			.catch((err: unknown) => {
				liveError = err instanceof Error ? err.message : 'failed to load live tasks'
				liveTasks = []
			})
			.finally(() => {
				isLoadingLive = false
			})

		isLoadingHistory = true
		historyError = null
		api.GET('/v1/tasks', {
			params: {
				query: {
					user_id: userId || undefined,
					spawned_thread_id: threadId || undefined,
					status_filter: historyStatusFilter === 'all' ? undefined : historyStatusFilter,
					state_filter: 'ended',
					skip: pageIndex * limit,
					limit,
					sort_by: sortKey,
					sort_dir: sortDir,
				},
			},
		})
			.then((result) => unwrap(result))
			.then((loaded) => {
				historyTasks = loaded
				hasNext = loaded.length === limit
			})
			.catch((err: unknown) => {
				historyError = err instanceof Error ? err.message : 'failed to load task history'
				historyTasks = []
				hasNext = false
			})
			.finally(() => {
				isLoadingHistory = false
			})
	})
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">tasks</h2>
			<p class="text-zinc-400">monitor live work and ended task history.</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<Button variant="outline" class="rounded-xl" onclick={() => (manualTasksOpen = true)}>
				<Wrench class="mr-1.5 h-4 w-4" />
				manual kickoff
			</Button>
			<Button variant="outline" class="rounded-xl" onclick={refresh} disabled={isLoading}>
				<RefreshCw class="mr-1.5 h-4 w-4 {isLoading ? 'animate-spin' : ''}" />
				{isLoading ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	<div class="grid gap-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto_auto]">
		<div class="relative">
			<Search
				class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
			/>
			<Input
				placeholder="filter by user id..."
				bind:value={ownerFilter}
				class="w-full rounded-xl pl-8"
				oninput={resetHistoryPage}
			/>
		</div>
		<div class="relative">
			<Hash
				class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
			/>
			<Input
				placeholder="filter by thread id..."
				bind:value={threadFilter}
				class="w-full rounded-xl pl-8"
				oninput={resetHistoryPage}
			/>
		</div>
		<Select value={historyStatusFilter} onValueChange={setStatusFilter}>
			<SelectTrigger class="w-full rounded-xl lg:w-56">
				<span class="truncate text-left">
					{historyStatusOptions.find((option) => option.value === historyStatusFilter)
						?.label ?? historyStatusFilter}
				</span>
			</SelectTrigger>
			<SelectContent>
				{#each historyStatusOptions as option (option.value)}
					<SelectItem value={option.value}>{option.label}</SelectItem>
				{/each}
			</SelectContent>
		</Select>
		<Select value={sortKey} onValueChange={setSort}>
			<SelectTrigger class="w-full rounded-xl lg:w-44">
				<span class="truncate text-left">
					{sortOptions.find((option) => option.value === sortKey)?.label ?? sortKey}
				</span>
			</SelectTrigger>
			<SelectContent>
				{#each sortOptions as option (option.value)}
					<SelectItem value={option.value}>{option.label}</SelectItem>
				{/each}
			</SelectContent>
		</Select>
		<Button
			variant="outline"
			class="rounded-xl px-3"
			onclick={toggleSortDir}
			disabled={isLoadingHistory}
			aria-label="toggle sort direction"
			title="toggle sort direction"
		>
			{#if sortDir === 'asc'}
				<ArrowUp class="h-4 w-4" />
			{:else}
				<ArrowDown class="h-4 w-4" />
			{/if}
		</Button>
	</div>

	{#if liveTasks.length > 0 || isLoadingLive || liveError}
		<section class="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
			<div class="flex items-center justify-between gap-3">
				<div>
					<div class="flex items-center gap-2 text-sm font-medium text-zinc-100">
						<Activity class="h-4 w-4 text-lime-400" />
						live tasks
					</div>
					<div class="mt-1 text-xs text-zinc-500">pending and running work</div>
				</div>
				<span class="text-xs text-zinc-500">{liveCount} live</span>
			</div>

			{#if isLoadingLive && liveTasks.length === 0}
				<div class="flex items-center justify-center py-8">
					<NokodoLoader />
				</div>
			{:else if liveError}
				<div
					class="mt-4 rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-sm text-red-200"
				>
					{liveError}
				</div>
			{:else}
				<div class="mt-4 grid gap-2 xl:grid-cols-2">
					{#each liveTasks as task (task.id)}
						{@const progress = progressValue(task)}
						{@const context = taskContext(task)}
						<button
							type="button"
							class="rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-900"
							onclick={() => openTaskDetails(task)}
						>
							<div class="flex items-start gap-3">
								<div
									class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-lime-500/15 text-lime-400"
								>
									{#if task.status === 'running'}
										<LoaderCircle class="h-4 w-4 animate-spin" />
									{:else}
										<Clock3 class="h-4 w-4" />
									{/if}
								</div>
								<div class="min-w-0 flex-1 space-y-2">
									<div class="flex flex-wrap items-center gap-2">
										<span class="truncate text-sm font-medium text-zinc-100"
											>{taskName(task)}</span
										>
										<span
											class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs {statusClass(
												task.status
											)}"
										>
											{task.status}
										</span>
									</div>
									<div class="h-2 overflow-hidden rounded-full bg-zinc-900">
										<div
											class="h-full rounded-full bg-lime-400"
											style:width={`${progress}%`}
										></div>
									</div>
									<div class="flex flex-wrap gap-3 text-xs text-zinc-500">
										<span>{progress}%</span>
										<span
											>last event {formatDate(
												task.last_event_at ?? task.updated_at
											)}</span
										>
										{#if context}<span class="truncate">{context}</span>{/if}
									</div>
								</div>
							</div>
						</button>
					{/each}
				</div>
			{/if}
		</section>
	{/if}

	<section class="flex flex-col gap-4">
		<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
			<div class="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
				<span class="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-2 py-1">
					<LoaderCircle class="h-3.5 w-3.5 text-lime-400" />
					{liveCount} live
				</span>
				<span class="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-2 py-1">
					<CheckCircle2 class="h-3.5 w-3.5 text-emerald-400" />
					{endedCount} shown
				</span>
			</div>
			<div class="flex items-center gap-2">
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => (pageIndex = Math.max(0, pageIndex - 1))}
					disabled={pageIndex === 0 || isLoadingHistory}
				>
					prev
				</Button>
				<span class="text-xs text-zinc-400 tabular-nums">
					page {pageIndex + 1}{historyTasks.length > 0
						? ` - ${historyTasks.length} items`
						: ''}
				</span>
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => (pageIndex += 1)}
					disabled={!hasNext || isLoadingHistory}
				>
					next
				</Button>
			</div>
		</div>

		{#if historyError}
			<div
				class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
			>
				{historyError}
			</div>
		{/if}

		<div class="flex flex-col gap-2">
			{#if isLoadingHistory && historyTasks.length === 0}
				<div
					class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{:else if historyTasks.length === 0 && !isLoadingHistory}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no task history found
				</div>
			{/if}

			{#each historyTasks as task (task.id)}
				{@const context = taskContext(task)}
				{@const summary = resultSummary(task)}
				<button
					type="button"
					class="flex flex-col gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50 lg:flex-row lg:items-center lg:justify-between"
					onclick={() => openTaskDetails(task)}
				>
					<div class="flex min-w-0 flex-1 gap-4">
						<div
							class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-950 text-zinc-300"
						>
							{#if task.status === 'complete'}
								<CheckCircle2 class="h-5 w-5 text-emerald-400" />
							{:else if task.status === 'failed'}
								<AlertTriangle class="h-5 w-5 text-red-400" />
							{:else if task.status === 'cancelled'}
								<Ban class="h-5 w-5 text-zinc-400" />
							{:else if task.status === 'running'}
								<LoaderCircle class="h-5 w-5 animate-spin text-lime-400" />
							{:else}
								<Clock3 class="h-5 w-5 text-sky-400" />
							{/if}
						</div>
						<div class="min-w-0 flex-1 space-y-2">
							<div class="flex flex-wrap items-center gap-2">
								<span class="truncate text-base font-medium text-zinc-100"
									>{taskName(task)}</span
								>
								<span
									class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs {statusClass(
										task.status
									)}"
								>
									{#if task.status === 'complete'}
										<CheckCircle2 class="h-3 w-3" />
									{:else if task.status === 'failed'}
										<XCircle class="h-3 w-3" />
									{:else if task.status === 'cancelled'}
										<Ban class="h-3 w-3" />
									{:else}
										<Circle class="h-3 w-3" />
									{/if}
									{task.status}
								</span>
							</div>

							<div class="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
								<span class="inline-flex items-center gap-1.5 break-all">
									<Hash class="h-3.5 w-3.5" />
									{task.id}
								</span>
								<span class="inline-flex items-center gap-1.5 break-all">
									<User class="h-3.5 w-3.5" />
									{task.user_id}
								</span>
								<span>{task.task_type.replaceAll('_', ' ')}</span>
								{#if task.stage}<span>{task.stage}</span>{/if}
								{#if context}<span class="truncate">{context}</span>{/if}
							</div>

							{#if summary}
								<div class="line-clamp-2 text-sm text-red-200/90">{summary}</div>
							{/if}
						</div>
					</div>

					<div
						class="grid shrink-0 gap-1 text-xs text-zinc-500 sm:grid-cols-3 lg:grid-cols-1 lg:text-right"
					>
						<span>created {formatDate(task.created_at)}</span>
						<span>last event {formatDate(task.last_event_at ?? task.updated_at)}</span>
						<span>ended {formatDate(task.completed_at ?? task.cancelled_at)}</span>
					</div>
				</button>
			{/each}
		</div>
	</section>
</div>

<TaskDetailsModal
	bind:open={taskDetailsOpen}
	taskId={selectedTaskId}
	initialTask={selectedTask}
	onUpdated={replaceTask}
/>

<ManualTaskKickoffModal bind:open={manualTasksOpen} onComplete={refresh} />
