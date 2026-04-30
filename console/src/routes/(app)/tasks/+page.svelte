<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
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
		XCircle,
	} from '@lucide/svelte'

	type Task = Schemas['Task']
	type TaskStatus = Schemas['TaskStatus']
	type SortKey = 'updated_at' | 'created_at' | 'status' | 'task_type' | 'stage' | 'last_event_at'
	type SortDir = 'asc' | 'desc'
	type ViewMode = 'live' | 'history' | 'all'
	type StatusFilter = 'all' | TaskStatus

	const viewOptions: Array<{ value: ViewMode; label: string; description: string }> = [
		{ value: 'live', label: 'live', description: 'running and pending' },
		{ value: 'history', label: 'history', description: 'completed, failed, cancelled' },
		{ value: 'all', label: 'all', description: 'latest tasks' },
	]

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'last_event_at', label: 'last event' },
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'status', label: 'status' },
		{ value: 'task_type', label: 'task type' },
		{ value: 'stage', label: 'stage' },
	]

	const liveStatusOptions: Array<{ value: StatusFilter; label: string }> = [
		{ value: 'all', label: 'all live statuses' },
		{ value: 'running', label: 'running' },
		{ value: 'pending', label: 'pending' },
	]

	const historyStatusOptions: Array<{ value: StatusFilter; label: string }> = [
		{ value: 'all', label: 'all ended statuses' },
		{ value: 'complete', label: 'complete' },
		{ value: 'failed', label: 'failed' },
		{ value: 'cancelled', label: 'cancelled' },
	]

	const allStatusOptions: Array<{ value: StatusFilter; label: string }> = [
		{ value: 'all', label: 'all statuses' },
		{ value: 'pending', label: 'pending' },
		{ value: 'running', label: 'running' },
		{ value: 'complete', label: 'complete' },
		{ value: 'failed', label: 'failed' },
		{ value: 'cancelled', label: 'cancelled' },
	]

	let tasks = $state<Task[]>([])
	let view = $state<ViewMode>('live')
	let statusFilter = $state<StatusFilter>('all')
	let ownerFilter = $state('')
	let sortKey = $state<SortKey>('last_event_at')
	let sortDir = $state<SortDir>('desc')
	let pageIndex = $state(0)
	let limit = $state(50)
	let refreshToken = $state(0)
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let hasNext = $state(false)
	let cancellingTaskId = $state<string | null>(null)

	const statusOptions = $derived.by(() => {
		if (view === 'live') return liveStatusOptions
		if (view === 'history') return historyStatusOptions
		return allStatusOptions
	})

	const loadedActiveCount = $derived(
		tasks.filter((task) => task.status === 'pending' || task.status === 'running').length
	)
	const loadedEndedCount = $derived(tasks.length - loadedActiveCount)

	function setView(next: ViewMode) {
		view = next
		statusFilter = 'all'
		pageIndex = 0
	}

	function setStatusFilter(next: string) {
		statusFilter = next as StatusFilter
		pageIndex = 0
	}

	function setSort(next: string) {
		sortKey = next as SortKey
		pageIndex = 0
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
		pageIndex = 0
	}

	function refresh() {
		refreshToken += 1
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
			metadataString(task, 'integration') ??
			metadataString(task, 'thread_id') ??
			metadataString(task, 'deployment_origin')
		)
	}

	function isActiveStatus(statusValue: TaskStatus): boolean {
		return statusValue === 'pending' || statusValue === 'running'
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

	async function cancelTask(task: Task) {
		if (!isActiveStatus(task.status)) return
		cancellingTaskId = task.id
		error = null
		try {
			const updated = unwrap(
				await api.POST('/v1/tasks/{task_id}/cancel', {
					params: { path: { task_id: task.id } },
					body: { reason: 'cancelled from console' },
				})
			)
			tasks = tasks.map((item) => (item.id === updated.id ? updated : item))
		} catch (err) {
			error = err instanceof Error ? err.message : 'failed to cancel task'
		} finally {
			cancellingTaskId = null
		}
	}

	$effect(() => {
		if (!browser) return
		void refreshToken

		const userId = ownerFilter.trim()
		const stateFilter = view === 'live' ? 'active' : view === 'history' ? 'ended' : undefined

		isLoading = true
		error = null

		api.GET('/v1/tasks', {
			params: {
				query: {
					user_id: userId || undefined,
					status_filter: statusFilter === 'all' ? undefined : statusFilter,
					state_filter: stateFilter,
					skip: pageIndex * limit,
					limit,
					sort_by: sortKey,
					sort_dir: sortDir,
				},
			},
		})
			.then((result) => unwrap(result))
			.then((loaded) => {
				tasks = loaded
				hasNext = loaded.length === limit
			})
			.catch((err: unknown) => {
				error = err instanceof Error ? err.message : 'failed to load tasks'
				tasks = []
				hasNext = false
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">tasks</h2>
			<p class="text-zinc-400">monitor live work and ended task history.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					placeholder="filter by user id..."
					bind:value={ownerFilter}
					class="w-full pl-8 sm:w-56 lg:w-72"
					oninput={() => (pageIndex = 0)}
				/>
			</div>
			<Select value={statusFilter} onValueChange={setStatusFilter}>
				<SelectTrigger class="w-full rounded-xl sm:w-56">
					<span class="truncate text-left">
						{statusOptions.find((option) => option.value === statusFilter)?.label ??
							statusFilter}
					</span>
				</SelectTrigger>
				<SelectContent>
					{#each statusOptions as option (option.value)}
						<SelectItem value={option.value}>{option.label}</SelectItem>
					{/each}
				</SelectContent>
			</Select>
			<div class="flex w-full items-center gap-2 sm:w-auto">
				<Select value={sortKey} onValueChange={setSort}>
					<SelectTrigger class="w-full flex-1 rounded-xl sm:w-44">
						<span class="truncate text-left">
							{sortOptions.find((option) => option.value === sortKey)?.label ??
								sortKey}
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
					class="shrink-0 rounded-xl px-3"
					onclick={toggleSortDir}
					disabled={isLoading}
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
			<Button variant="outline" class="rounded-xl" onclick={refresh} disabled={isLoading}>
				<RefreshCw class="mr-1.5 h-4 w-4 {isLoading ? 'animate-spin' : ''}" />
				{isLoading ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	<div class="grid gap-2 sm:grid-cols-3">
		{#each viewOptions as option (option.value)}
			<button
				type="button"
				class="rounded-2xl border p-4 text-left transition-colors {view === option.value
					? 'border-lime-500/30 bg-lime-500/10 text-zinc-100'
					: 'border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-800/60'}"
				onclick={() => setView(option.value)}
			>
				<div class="flex items-center gap-2 text-sm font-medium">
					<Activity class="h-4 w-4 text-lime-400" />
					{option.label}
				</div>
				<div class="mt-1 text-xs text-zinc-500">{option.description}</div>
			</button>
		{/each}
	</div>

	{#if error}
		<div
			class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
		>
			{error}
		</div>
	{/if}

	<div class="flex flex-col gap-4">
		<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
			<div class="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
				<span class="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-2 py-1">
					<LoaderCircle class="h-3.5 w-3.5 text-lime-400" />
					{loadedActiveCount} live
				</span>
				<span class="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-2 py-1">
					<CheckCircle2 class="h-3.5 w-3.5 text-emerald-400" />
					{loadedEndedCount} ended
				</span>
			</div>
			<div class="flex items-center gap-2">
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => (pageIndex = Math.max(0, pageIndex - 1))}
					disabled={pageIndex === 0 || isLoading}
				>
					prev
				</Button>
				<span class="text-xs text-zinc-400 tabular-nums">
					page {pageIndex + 1}{tasks.length > 0 ? ` - ${tasks.length} items` : ''}
				</span>
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => (pageIndex += 1)}
					disabled={!hasNext || isLoading}
				>
					next
				</Button>
			</div>
		</div>

		<div class="flex flex-col space-y-2">
			{#if isLoading && tasks.length === 0}
				<div
					class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{/if}

			{#if tasks.length === 0 && !isLoading}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no tasks found
				</div>
			{/if}

			{#each tasks as task (task.id)}
				{@const progress = progressValue(task)}
				{@const active = isActiveStatus(task.status)}
				{@const context = taskContext(task)}
				{@const summary = resultSummary(task)}
				<div
					class="flex flex-col gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 transition-colors hover:border-zinc-700 hover:bg-zinc-800/50 lg:flex-row lg:items-center lg:justify-between"
				>
					<div class="flex min-w-0 flex-1 gap-4">
						<div
							class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-lime-500/15 text-lime-400"
						>
							{#if task.status === 'running'}
								<LoaderCircle class="h-5 w-5 animate-spin" />
							{:else if task.status === 'pending'}
								<Clock3 class="h-5 w-5" />
							{:else if task.status === 'complete'}
								<CheckCircle2 class="h-5 w-5" />
							{:else if task.status === 'failed'}
								<AlertTriangle class="h-5 w-5" />
							{:else}
								<Ban class="h-5 w-5" />
							{/if}
						</div>
						<div class="min-w-0 flex-1 space-y-2">
							<div class="flex flex-wrap items-center gap-2">
								<span class="truncate text-base font-medium text-zinc-100">
									{taskName(task)}
								</span>
								<span
									class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs {statusClass(
										task.status
									)}"
								>
									{#if task.status === 'running'}
										<LoaderCircle class="h-3 w-3 animate-spin" />
									{:else if task.status === 'complete'}
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
								<span class="inline-flex items-center gap-1.5">
									<Hash class="h-3.5 w-3.5" />
									{task.id}
								</span>
								<span class="inline-flex items-center gap-1.5">
									<User class="h-3.5 w-3.5" />
									{task.user_id}
								</span>
								<span>{task.task_type.replaceAll('_', ' ')}</span>
								{#if task.stage}
									<span>{task.stage}</span>
								{/if}
								{#if context}
									<span class="truncate">{context}</span>
								{/if}
							</div>

							{#if active || task.progress != null}
								<div class="max-w-2xl space-y-1">
									<div class="h-2 overflow-hidden rounded-full bg-zinc-950">
										<div
											class="h-full rounded-full bg-lime-400 transition-all"
											style:width={`${progress}%`}
										></div>
									</div>
									<div class="text-xs text-zinc-500">{progress}%</div>
								</div>
							{/if}

							{#if summary}
								<div class="line-clamp-2 text-sm text-red-200/90">{summary}</div>
							{/if}
						</div>
					</div>

					<div class="flex shrink-0 flex-col gap-3 lg:items-end">
						<div
							class="grid gap-1 text-xs text-zinc-500 sm:grid-cols-3 lg:grid-cols-1 lg:text-right"
						>
							<span>created {formatDate(task.created_at)}</span>
							<span
								>last event {formatDate(
									task.last_event_at ?? task.updated_at
								)}</span
							>
							<span>ended {formatDate(task.completed_at ?? task.cancelled_at)}</span>
						</div>
						{#if active}
							<Button
								variant="outline"
								class="rounded-xl border-red-900/60 text-red-200 hover:bg-red-950/40"
								onclick={() => cancelTask(task)}
								disabled={cancellingTaskId === task.id}
							>
								<Ban class="mr-1.5 h-4 w-4" />
								{cancellingTaskId === task.id ? 'cancelling...' : 'cancel'}
							</Button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	</div>
</div>
