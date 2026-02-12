<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Reminder, type ReminderListWithCounts } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import UserDetailsModal from '$lib/components/UserDetailsModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import {
		ArrowDown,
		ArrowUp,
		ChevronDown,
		ChevronRight,
		Circle,
		CircleCheck,
		Clock,
		Hash,
		ListChecks,
		User,
	} from '@lucide/svelte'

	type ListSortKey = 'updated_at' | 'created_at' | 'name' | 'position'
	type SortDir = 'asc' | 'desc'

	const listSortOptions: Array<{ value: ListSortKey; label: string }> = [
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'name', label: 'name' },
		{ value: 'position', label: 'position' },
	]

	function defaultSortDir(sort: ListSortKey): SortDir {
		if (sort === 'name') return 'asc'
		if (sort === 'position') return 'asc'
		return 'desc'
	}

	let sortKey = $state<ListSortKey>('updated_at')
	let sortDir = $state<SortDir>('desc')
	let searchQuery = $state('')
	let refreshToken = $state(0)

	let lists = $state<ReminderListWithCounts[]>([])
	let isLoading = $state(false)
	let error = $state<string | null>(null)

	let expandedListId = $state<string | null>(null)
	let listReminders = $state<Reminder[]>([])
	let isRemindersLoading = $state(false)
	let remindersError = $state<string | null>(null)

	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)

	const filteredLists = $derived(
		lists.filter((l) => {
			const q = searchQuery.toLowerCase()
			return (
				l.name.toLowerCase().includes(q) ||
				l.id.toLowerCase().includes(q) ||
				(l.description ?? '').toLowerCase().includes(q)
			)
		})
	)

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
	}

	function refresh() {
		refreshToken += 1
	}

	function setSort(next: ListSortKey) {
		sortKey = next
		sortDir = defaultSortDir(next)
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
	}

	async function toggleExpand(listId: string) {
		if (expandedListId === listId) {
			expandedListId = null
			listReminders = []
			return
		}
		expandedListId = listId
		isRemindersLoading = true
		remindersError = null
		try {
			listReminders = unwrap(
				await api.GET('/v1/reminders', {
					params: {
						query: {
							list_id: listId,
							include_subtasks: true,
							limit: 100,
							sort_by: 'position',
							sort_dir: 'asc',
						},
					},
				})
			)
		} catch (e: unknown) {
			remindersError = e instanceof Error ? e.message : 'failed to load reminders'
			listReminders = []
		} finally {
			isRemindersLoading = false
		}
	}

	$effect(() => {
		if (!browser) return

		// depend on refreshToken to allow manual refresh
		void refreshToken

		isLoading = true
		error = null

		api.GET('/v1/reminders/lists', {
			params: {
				query: {
					include_counts: true,
					sort_by: sortKey,
					sort_dir: sortDir,
					limit: 200,
				},
			},
		})
			.then((r) => unwrap(r))
			.then((result) => {
				lists = result
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load reminder lists'
				lists = []
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">reminders</h2>
			<p class="text-zinc-400">all reminder lists and their reminders.</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<Input
				type="search"
				placeholder="search lists..."
				bind:value={searchQuery}
				class="h-9 w-50 lg:w-75"
			/>
			<Select value={sortKey} onValueChange={(v: string) => setSort(v as ListSortKey)}>
				<SelectTrigger class="w-56 rounded-xl">
					<span class="truncate text-left">
						{listSortOptions.find((o) => o.value === sortKey)?.label ?? sortKey}
					</span>
				</SelectTrigger>
				<SelectContent>
					{#each listSortOptions as opt (opt.value)}
						<SelectItem value={opt.value}>{opt.label}</SelectItem>
					{/each}
				</SelectContent>
			</Select>
			<Button
				variant="outline"
				class="rounded-xl px-3"
				onclick={() => toggleSortDir()}
				disabled={isLoading}
				title="toggle sort direction"
				aria-label="toggle sort direction"
			>
				{#if sortDir === 'asc'}
					<ArrowUp class="h-4 w-4" />
				{:else}
					<ArrowDown class="h-4 w-4" />
				{/if}
			</Button>
			<Button
				variant="outline"
				class="rounded-xl"
				onclick={() => refresh()}
				disabled={isLoading}
			>
				{isLoading ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	{#if error}
		<div
			class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
		>
			{error}
		</div>
	{/if}

	<Card
		class="flex min-h-0 flex-1 flex-col rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100"
	>
		<CardHeader class="shrink-0">
			<CardTitle>reminder lists</CardTitle>
			<CardDescription>
				{filteredLists.length} list{filteredLists.length === 1 ? '' : 's'}
			</CardDescription>
		</CardHeader>
		<CardContent class="flex min-h-0 flex-1 flex-col space-y-2 overflow-y-auto">
			{#if isLoading && lists.length === 0}
				<div
					class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{/if}

			{#if filteredLists.length === 0 && !isLoading}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no reminder lists found
				</div>
			{/if}

			{#each filteredLists as list (list.id)}
				<div
					class="rounded-xl border border-zinc-800 bg-zinc-950 transition-colors hover:border-zinc-700"
				>
					<div
						role="button"
						tabindex="0"
						class="flex w-full cursor-pointer items-start gap-3 p-4 text-left"
						onclick={() => toggleExpand(list.id)}
						onkeydown={(e: KeyboardEvent) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault()
								toggleExpand(list.id)
							}
						}}
					>
						<div class="mt-0.5 shrink-0 text-zinc-500">
							{#if expandedListId === list.id}
								<ChevronDown class="h-4 w-4" />
							{:else}
								<ChevronRight class="h-4 w-4" />
							{/if}
						</div>
						<div class="min-w-0 flex-1 space-y-2">
							<div class="flex items-center gap-2">
								{#if list.color}
									<span
										class="inline-block h-3 w-3 rounded-full"
										style="background-color: {list.color}"
									></span>
								{/if}
								<span class="truncate font-medium">{list.name}</span>
							</div>
							{#if list.description}
								<div class="line-clamp-1 text-sm text-zinc-400">
									{list.description}
								</div>
							{/if}
							<div class="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<Hash class="h-3.5 w-3.5" />
									{list.id}
								</span>
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<User class="h-3.5 w-3.5" />
									<button
										type="button"
										class="underline underline-offset-4 hover:text-zinc-200"
										onclick={(e: MouseEvent) => {
											e.stopPropagation()
											openUser(list.owner_id)
										}}
									>
										{list.owner_id}
									</button>
								</span>
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<ListChecks class="h-3.5 w-3.5" />
									total {list.total_count}
								</span>
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<Circle class="h-3.5 w-3.5" />
									pending {list.pending_count}
								</span>
								<span
									class="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5"
								>
									<CircleCheck class="h-3.5 w-3.5" />
									completed {list.completed_count}
								</span>
							</div>
						</div>
						<div class="shrink-0 text-xs text-zinc-500">
							<div class="flex items-center gap-1">
								<Clock class="h-3.5 w-3.5" />
								updated {new Date(list.updated_at).toLocaleString()}
							</div>
						</div>
					</div>
					{#if expandedListId === list.id}
						<div class="border-t border-zinc-800 px-4 py-3">
							{#if isRemindersLoading}
								<div class="flex items-center justify-center p-6">
									<NokodoLoader />
								</div>
							{:else if remindersError}
								<div
									class="rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-sm text-red-200"
								>
									{remindersError}
								</div>
							{:else if listReminders.length === 0}
								<div class="py-4 text-center text-sm text-zinc-500">
									no reminders in this list
								</div>
							{:else}
								<div class="space-y-1">
									{#each listReminders as reminder (reminder.id)}
										<div
											class="flex items-start gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-zinc-900"
										>
											<div class="mt-0.5 shrink-0">
												{#if reminder.status === 'completed'}
													<CircleCheck class="h-4 w-4 text-emerald-400" />
												{:else}
													<Circle class="h-4 w-4 text-zinc-500" />
												{/if}
											</div>
											<div class="min-w-0 flex-1">
												<div
													class="text-sm font-medium {reminder.status ===
													'completed'
														? 'text-zinc-500 line-through'
														: ''}"
												>
													{reminder.title}
												</div>
												{#if reminder.description}
													<div
														class="mt-0.5 line-clamp-1 text-xs text-zinc-400"
													>
														{reminder.description}
													</div>
												{/if}
												<div
													class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-zinc-500"
												>
													<div>id: {reminder.id}</div>
													{#if reminder.due_at}
														<div>
															due: {new Date(
																reminder.due_at
															).toLocaleString()}
														</div>
													{/if}
													{#if reminder.completed_at}
														<div>
															completed: {new Date(
																reminder.completed_at
															).toLocaleString()}
														</div>
													{/if}
													<div>
														owner:
														<button
															type="button"
															class="ml-1 underline underline-offset-4 hover:text-zinc-200"
															onclick={() =>
																openUser(reminder.owner_id)}
														>
															{reminder.owner_id}
														</button>
													</div>
												</div>
											</div>
											<div class="shrink-0 text-xs text-zinc-500">
												{new Date(reminder.updated_at).toLocaleString()}
											</div>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</CardContent>
	</Card>
</div>

<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />
