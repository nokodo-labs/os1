<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import UserDetailsModal from '$lib/components/UserDetailsModal.svelte'
	import {
		ArrowDown,
		ArrowUp,
		CalendarCheck,
		CalendarDays,
		Clock,
		Hash,
		MapPin,
		RefreshCw,
		Search,
		User,
		Video,
	} from '@lucide/svelte'
	import { SvelteDate } from 'svelte/reactivity'

	type CalendarRecord = Schemas['Calendar']
	type CalendarEvent = Schemas['CalendarEvent']
	type SortKey = 'updated_at' | 'created_at' | 'name' | 'position'
	type SortDir = 'asc' | 'desc'
	type CalendarFilter = 'all' | string

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'position', label: 'position' },
		{ value: 'name', label: 'name' },
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
	]

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'name') return 'asc'
		if (sort === 'position') return 'asc'
		return 'desc'
	}

	let calendars = $state<CalendarRecord[]>([])
	let events = $state<CalendarEvent[]>([])
	let sortKey = $state<SortKey>('position')
	let sortDir = $state<SortDir>('asc')
	let selectedCalendarId = $state<CalendarFilter>('all')
	let searchQuery = $state('')
	let refreshToken = $state(0)
	let isLoading = $state(false)
	let isLoadingEvents = $state(false)
	let error = $state<string | null>(null)
	let eventsError = $state<string | null>(null)
	let isUserDetailsOpen = $state(false)
	let selectedUserId = $state<string | null>(null)

	const filteredCalendars = $derived.by(() => {
		const q = searchQuery.trim().toLowerCase()
		if (!q) return calendars
		return calendars.filter((calendar) => {
			const description = calendar.description ?? ''
			return (
				calendar.name.toLowerCase().includes(q) ||
				description.toLowerCase().includes(q) ||
				calendar.id.toLowerCase().includes(q) ||
				calendar.owner_id.toLowerCase().includes(q)
			)
		})
	})

	const visibleEvents = $derived.by(() => {
		const items =
			selectedCalendarId === 'all'
				? events
				: events.filter((event) => event.calendar_id === selectedCalendarId)
		return items.toSorted(
			(left, right) => Date.parse(left.start_at) - Date.parse(right.start_at)
		)
	})

	const defaultCalendars = $derived(calendars.filter((calendar) => calendar.is_default).length)
	const eventWindowLabel = $derived(
		`${visibleEvents.length} event${visibleEvents.length === 1 ? '' : 's'}`
	)

	function refresh() {
		refreshToken += 1
	}

	function setSort(next: string) {
		const option = sortOptions.find((item) => item.value === next)
		if (!option) return
		sortKey = option.value
		sortDir = defaultSortDir(option.value)
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
	}

	function openUser(userId: string) {
		selectedUserId = userId
		isUserDetailsOpen = true
	}

	function selectCalendar(calendarId: CalendarFilter) {
		selectedCalendarId = calendarId
	}

	function selectCalendarOnKeydown(event: KeyboardEvent, calendarId: CalendarFilter) {
		if (event.key !== 'Enter' && event.key !== ' ') return
		event.preventDefault()
		selectCalendar(calendarId)
	}

	function calendarName(calendarId: string): string {
		return calendars.find((calendar) => calendar.id === calendarId)?.name ?? 'calendar'
	}

	function projectCount(calendar: CalendarRecord): number {
		return calendar.project_ids?.length ?? 0
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

	function eventWindow(): { startAt: string; endAt: string } {
		const start = new SvelteDate()
		start.setDate(start.getDate() - 7)
		start.setHours(0, 0, 0, 0)
		const end = new SvelteDate()
		end.setDate(end.getDate() + 30)
		end.setHours(23, 59, 59, 999)
		return { startAt: start.toISOString(), endAt: end.toISOString() }
	}

	async function loadEvents(sourceCalendars: CalendarRecord[]): Promise<void> {
		const window = eventWindow()
		isLoadingEvents = true
		eventsError = null
		try {
			const responses = await Promise.all(
				sourceCalendars.map(async (calendar) => {
					try {
						return unwrap(
							await api.GET('/v1/calendars/{calendar_id}/events', {
								params: {
									path: { calendar_id: calendar.id },
									query: {
										start_at: window.startAt,
										end_at: window.endAt,
										limit: 500,
										sort_by: 'start_at',
										sort_dir: 'asc',
									},
								},
							})
						)
					} catch {
						return []
					}
				})
			)
			events = responses.flat()
		} catch (err) {
			eventsError = err instanceof Error ? err.message : 'failed to load calendar events'
			events = []
		} finally {
			isLoadingEvents = false
		}
	}

	$effect(() => {
		if (!browser) return
		void refreshToken

		isLoading = true
		error = null

		api.GET('/v1/calendars', {
			params: {
				query: {
					limit: 300,
					sort_by: sortKey,
					sort_dir: sortDir,
				},
			},
		})
			.then((result) => unwrap(result))
			.then((loaded) => {
				calendars = loaded
				if (
					selectedCalendarId !== 'all' &&
					!loaded.some((calendar) => calendar.id === selectedCalendarId)
				) {
					selectedCalendarId = 'all'
				}
				void loadEvents(loaded)
			})
			.catch((err: unknown) => {
				error = err instanceof Error ? err.message : 'failed to load calendars'
				calendars = []
				events = []
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">calendars</h2>
			<p class="text-zinc-400">all calendars and upcoming calendar events.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search calendars..."
					bind:value={searchQuery}
					class="w-full pl-8 sm:w-50 lg:w-75"
				/>
			</div>
			<Select value={sortKey} onValueChange={setSort}>
				<SelectTrigger class="w-full rounded-xl sm:w-48">
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
			<Button variant="outline" class="rounded-xl" onclick={refresh} disabled={isLoading}>
				<RefreshCw class="mr-1.5 h-4 w-4 {isLoading ? 'animate-spin' : ''}" />
				{isLoading ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	<div class="grid gap-3 sm:grid-cols-3">
		<div class="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
			<div class="flex items-center gap-2 text-sm text-zinc-400">
				<CalendarDays class="h-4 w-4 text-rose-400" />
				calendars
			</div>
			<div class="mt-2 text-2xl font-semibold">{calendars.length}</div>
		</div>
		<div class="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
			<div class="flex items-center gap-2 text-sm text-zinc-400">
				<CalendarCheck class="h-4 w-4 text-emerald-400" />
				default calendars
			</div>
			<div class="mt-2 text-2xl font-semibold">{defaultCalendars}</div>
		</div>
		<div class="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
			<div class="flex items-center gap-2 text-sm text-zinc-400">
				<Clock class="h-4 w-4 text-sky-400" />
				visible events
			</div>
			<div class="mt-2 text-2xl font-semibold">{visibleEvents.length}</div>
		</div>
	</div>

	{#if error}
		<div class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200">
			{error}
		</div>
	{/if}

	<div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(340px,0.9fr)]">
		<section class="space-y-3">
			<div class="flex items-center justify-between text-sm text-zinc-400">
				<span
					>{filteredCalendars.length} calendar{filteredCalendars.length === 1
						? ''
						: 's'}</span
				>
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => selectCalendar('all')}
					disabled={selectedCalendarId === 'all'}
				>
					show all events
				</Button>
			</div>

			{#if isLoading && calendars.length === 0}
				<div
					class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{:else if filteredCalendars.length === 0}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no calendars found
				</div>
			{:else}
				<div class="flex flex-col gap-2">
					{#each filteredCalendars as calendar (calendar.id)}
						{@const calendarProjectCount = projectCount(calendar)}
						<div
							role="button"
							tabindex="0"
							class="flex w-full items-start justify-between gap-4 rounded-2xl border p-4 text-left transition-colors {selectedCalendarId ===
							calendar.id
								? 'border-rose-500/40 bg-rose-500/10'
								: 'border-zinc-800 bg-zinc-900 hover:border-zinc-700 hover:bg-zinc-800/50'}"
							onclick={() => selectCalendar(calendar.id)}
							onkeydown={(event) => selectCalendarOnKeydown(event, calendar.id)}
						>
							<div class="flex min-w-0 gap-4">
								<span
									class="mt-1 h-4 w-4 shrink-0 rounded-full border border-zinc-700"
									style="background-color: {calendar.color}"
								></span>
								<div class="min-w-0 space-y-1">
									<div class="flex flex-wrap items-center gap-2">
										<span class="truncate font-medium">{calendar.name}</span>
										{#if calendar.is_default}
											<span
												class="rounded-md bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-emerald-400 uppercase"
												>default</span
											>
										{/if}
									</div>
									{#if calendar.description}
										<div class="line-clamp-1 text-sm text-zinc-400">
											{calendar.description}
										</div>
									{/if}
									<div
										class="flex flex-wrap items-center gap-3 text-xs text-zinc-500"
									>
										<span
											class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-60"
										>
											<Hash class="h-3 w-3" />
											{calendar.id}
										</span>
										<span class="inline-flex items-center gap-1">
											<User class="h-3.5 w-3.5" />
											<button
												type="button"
												class="cursor-pointer bg-transparent p-0 text-left text-xs text-zinc-500 underline underline-offset-4 hover:text-zinc-300"
												onclick={(event) => {
													event.stopPropagation()
													openUser(calendar.owner_id)
												}}>{calendar.owner_id}</button
											>
										</span>
										{#if calendar.timezone}
											<span>{calendar.timezone}</span>
										{/if}
										<span>
											{calendarProjectCount} project{calendarProjectCount ===
											1
												? ''
												: 's'}
										</span>
									</div>
								</div>
							</div>
							<div class="shrink-0 text-right text-xs text-zinc-500">
								updated {formatDate(calendar.updated_at)}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>

		<section class="space-y-3">
			<div class="flex items-center justify-between text-sm text-zinc-400">
				<span>{eventWindowLabel}</span>
				<span>next 30 days</span>
			</div>

			{#if isLoadingEvents && events.length === 0}
				<div
					class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{:else if eventsError}
				<div
					class="rounded-xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
				>
					{eventsError}
				</div>
			{:else if visibleEvents.length === 0}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no calendar events found
				</div>
			{:else}
				<div class="flex flex-col gap-2">
					{#each visibleEvents as event (event.id)}
						<div class="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
							<div class="flex items-start justify-between gap-3">
								<div class="min-w-0 space-y-1">
									<div class="truncate font-medium">{event.title}</div>
									{#if event.description}
										<div class="line-clamp-2 text-sm text-zinc-400">
											{event.description}
										</div>
									{/if}
								</div>
								<span
									class="shrink-0 rounded-md bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400"
								>
									{calendarName(event.calendar_id)}
								</span>
							</div>
							<div
								class="mt-3 flex flex-wrap items-center gap-3 text-xs text-zinc-500"
							>
								<span class="inline-flex items-center gap-1.5">
									<Clock class="h-3.5 w-3.5" />
									{formatDate(event.start_at)} - {formatDate(event.end_at)}
								</span>
								{#if event.location}
									<span class="inline-flex items-center gap-1.5">
										<MapPin class="h-3.5 w-3.5" />
										{event.location}
									</span>
								{/if}
								{#if event.virtual_url}
									<span class="inline-flex items-center gap-1.5">
										<Video class="h-3.5 w-3.5" />
										{event.virtual_url}
									</span>
								{/if}
								<span
									class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-60"
								>
									<Hash class="h-3 w-3" />
									{event.id}
								</span>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>
	</div>
</div>

<UserDetailsModal bind:open={isUserDetailsOpen} userId={selectedUserId} />
