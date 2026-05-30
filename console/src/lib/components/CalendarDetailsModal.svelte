<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type CalendarRecord = Schemas['Calendar']
	type CalendarEvent = Schemas['CalendarEvent']
	type CalendarUpdate = Schemas['CalendarUpdate']

	import AclModal from '$lib/components/AclModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Textarea } from '$lib/components/ui/textarea'
	import {
		CalendarDays,
		ChevronLeft,
		ChevronRight,
		Clock,
		Folder,
		Hash,
		Pencil,
		Save,
		Shield,
		Trash2,
		User,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		calendarId: string | null
		highlightEventId?: string | null
		onUpdated?: (calendar: CalendarRecord) => void
		onDeleted?: (calendarId: string) => void
		onViewUser?: (userId: string) => void
	}

	let {
		open = $bindable(false),
		calendarId,
		highlightEventId = null,
		onUpdated,
		onDeleted,
		onViewUser,
	}: Props = $props()

	const CALENDAR_EVENT_PAGE_LIMIT = 20

	let calendar = $state<CalendarRecord | null>(null)
	let events = $state<CalendarEvent[]>([])
	let eventsPageIndex = $state(0)
	let isLoading = $state(false)
	let loadError = $state<string | null>(null)
	let isLoadingEvents = $state(false)
	let eventsError = $state<string | null>(null)
	let eventsRequestId = 0

	let isEditing = $state(false)
	let editName = $state('')
	let editDescription = $state('')
	let editColor = $state('#d45446')
	let editPosition = $state('0')
	let editIsDefault = $state(false)
	let editTimezone = $state('')
	let editProjectIds = $state('')
	let editMetadata = $state('{}')

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let confirmDelete = $state(false)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)
	let showAclModal = $state(false)

	function close() {
		open = false
		calendar = null
		events = []
		eventsPageIndex = 0
		isEditing = false
		confirmDelete = false
		loadError = null
		eventsError = null
		saveError = null
		deleteError = null
		showAclModal = false
	}

	function formatDate(value: string | null | undefined): string {
		if (!value) return 'never'
		const date = new Date(value)
		if (Number.isNaN(date.getTime())) return 'unknown'
		return date.toLocaleString()
	}

	function formatEventRange(event: CalendarEvent): string {
		if (event.all_day) return `${new Date(event.start_at).toLocaleDateString()} - all day`
		return `${formatDate(event.start_at)} - ${formatDate(event.end_at)}`
	}

	function formatJsonObject(value: unknown): string {
		if (value === null || typeof value !== 'object' || Array.isArray(value)) return '{}'
		return JSON.stringify(value, null, 2)
	}

	function parseJsonObject(value: string): Record<string, unknown> {
		const trimmed = value.trim()
		if (!trimmed) return {}
		const parsed: unknown = JSON.parse(trimmed)
		if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
			throw new Error('expected JSON object')
		}
		return Object.fromEntries(Object.entries(parsed))
	}

	function splitProjectIds(value: string): string[] {
		return value
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean)
	}

	function viewOwner(source: CalendarRecord) {
		onViewUser?.(source.owner_id)
	}

	function startEdit() {
		if (!calendar) return
		editName = calendar.name
		editDescription = calendar.description ?? ''
		editColor = calendar.color || '#d45446'
		editPosition = String(calendar.position ?? 0)
		editIsDefault = calendar.is_default
		editTimezone = calendar.timezone ?? ''
		editProjectIds = (calendar.project_ids ?? []).join(', ')
		editMetadata = formatJsonObject(calendar.metadata_)
		isEditing = true
		saveError = null
	}

	function cancelEdit() {
		isEditing = false
		saveError = null
	}

	function eventsPageOffset(index: number): number {
		return Math.max(0, Math.trunc(index)) * CALENDAR_EVENT_PAGE_LIMIT
	}

	function previousEventsPage() {
		eventsPageIndex = Math.max(0, eventsPageIndex - 1)
	}

	function nextEventsPage() {
		if (events.length < CALENDAR_EVENT_PAGE_LIMIT) return
		eventsPageIndex += 1
	}

	async function loadCalendar() {
		if (!calendarId) return
		isLoading = true
		loadError = null
		calendar = null
		try {
			calendar = unwrap(
				await api.GET('/v1/calendars/{calendar_id}', {
					params: { path: { calendar_id: calendarId } },
				})
			)
		} catch (e: unknown) {
			loadError = e instanceof Error ? e.message : 'failed to load calendar'
		} finally {
			isLoading = false
		}
	}

	async function loadEvents(sourceCalendarId: string, pageIndex: number) {
		const requestId = ++eventsRequestId
		isLoadingEvents = true
		eventsError = null
		events = []
		try {
			const loaded = unwrap(
				await api.GET('/v1/calendars/{calendar_id}/events', {
					params: {
						path: { calendar_id: sourceCalendarId },
						query: {
							skip: eventsPageOffset(pageIndex),
							limit: CALENDAR_EVENT_PAGE_LIMIT,
							sort_by: 'start_at',
							sort_dir: 'asc',
						},
					},
				})
			)
			if (requestId !== eventsRequestId) return
			events = loaded
		} catch (e: unknown) {
			if (requestId !== eventsRequestId) return
			eventsError = e instanceof Error ? e.message : 'failed to load events'
		} finally {
			if (requestId === eventsRequestId) isLoadingEvents = false
		}
	}

	async function saveCalendar() {
		if (!calendar) return
		isSaving = true
		saveError = null
		try {
			const position = Number(editPosition)
			if (!Number.isFinite(position)) throw new Error('position must be a number')

			const body: CalendarUpdate = {
				name: editName.trim(),
				description: editDescription.trim() || null,
				color: editColor.trim() || '#d45446',
				position,
				is_default: editIsDefault,
				timezone: editTimezone.trim() || null,
				project_ids: splitProjectIds(editProjectIds),
				metadata_: parseJsonObject(editMetadata),
			}

			const updated = unwrap(
				await api.PATCH('/v1/calendars/{calendar_id}', {
					params: { path: { calendar_id: calendar.id } },
					body,
				})
			)
			calendar = updated
			isEditing = false
			onUpdated?.(updated)
		} catch (e: unknown) {
			saveError = e instanceof Error ? e.message : 'failed to save calendar'
		} finally {
			isSaving = false
		}
	}

	async function deleteCalendar() {
		if (!calendar) return
		isDeleting = true
		deleteError = null
		try {
			await api.DELETE('/v1/calendars/{calendar_id}', {
				params: { path: { calendar_id: calendar.id } },
			})
			onDeleted?.(calendar.id)
			close()
		} catch (e: unknown) {
			deleteError = e instanceof Error ? e.message : 'failed to delete calendar'
		} finally {
			isDeleting = false
		}
	}

	$effect(() => {
		if (!open || !calendarId) return
		eventsPageIndex = 0
		void loadCalendar()
	})

	$effect(() => {
		if (!open || !calendarId) return
		void loadEvents(calendarId, eventsPageIndex)
	})
</script>

<Dialog.Root
	bind:open
	onOpenChange={(value) => {
		if (!value) close()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			data-dialog-content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-[min(780px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-auto rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div class="min-w-0 flex-1">
					<Dialog.Title class="truncate text-base font-semibold">
						{calendar?.name ?? 'calendar'}
					</Dialog.Title>
					<Dialog.Description class="text-xs text-zinc-500"
						>calendar details</Dialog.Description
					>
				</div>
				<div class="flex shrink-0 items-center gap-1">
					{#if calendar && !isEditing}
						<Button
							variant="ghost"
							size="sm"
							class="h-7 rounded-lg px-2 text-xs text-zinc-400 hover:text-zinc-200"
							onclick={() => (showAclModal = true)}
						>
							<Shield class="mr-1 h-3 w-3" />
							access
						</Button>
						<Button
							variant="ghost"
							size="sm"
							class="h-7 rounded-lg px-2 text-xs text-zinc-400 hover:text-zinc-200"
							onclick={startEdit}
						>
							<Pencil class="mr-1 h-3 w-3" />
							edit
						</Button>
						{#if !confirmDelete}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-red-400 hover:text-red-300"
								onclick={() => (confirmDelete = true)}
							>
								<Trash2 class="mr-1 h-3 w-3" />
								delete
							</Button>
						{:else}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-red-400 hover:text-red-300"
								onclick={deleteCalendar}
								disabled={isDeleting}
							>
								{isDeleting ? 'deleting...' : 'confirm?'}
							</Button>
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-zinc-400"
								onclick={() => (confirmDelete = false)}
							>
								<X class="mr-1 h-3 w-3" />
								cancel
							</Button>
						{/if}
					{/if}
					<Button variant="ghost" size="icon" class="shrink-0 rounded-xl" onclick={close}>
						<X class="h-4 w-4" />
					</Button>
				</div>
			</div>

			<div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-4">
				{#if isLoading}
					<div
						class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 text-sm text-zinc-400"
					>
						loading calendar...
					</div>
				{:else if loadError}
					<div
						class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
					>
						{loadError}
					</div>
				{:else if calendar}
					{#if deleteError}
						<div
							class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
						>
							{deleteError}
						</div>
					{/if}

					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							identity
						</p>
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Hash class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-20 shrink-0 text-xs text-zinc-500">id</span>
								<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
									>{calendar.id}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<User class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-20 shrink-0 text-xs text-zinc-500">owner</span>
								{#if onViewUser}
									<button
										type="button"
										class="min-w-0 truncate font-mono text-xs text-zinc-300 underline underline-offset-4 hover:text-zinc-100"
										onclick={() => {
											if (calendar) viewOwner(calendar)
										}}>{calendar.owner_id}</button
									>
								{:else}
									<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
										>{calendar.owner_id}</span
									>
								{/if}
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<CalendarDays class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-20 shrink-0 text-xs text-zinc-500">created</span>
								<span class="text-xs text-zinc-300"
									>{formatDate(calendar.created_at)}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Clock class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-20 shrink-0 text-xs text-zinc-500">updated</span>
								<span class="text-xs text-zinc-300"
									>{formatDate(calendar.updated_at)}</span
								>
							</div>
						</div>
					</div>

					{#if isEditing}
						<div class="space-y-3">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								edit
							</p>
							<div class="grid gap-3 sm:grid-cols-2">
								<div class="space-y-1.5 sm:col-span-2">
									<Label class="text-xs text-zinc-400">name</Label>
									<Input
										bind:value={editName}
										class="rounded-xl border-zinc-700 bg-zinc-900"
									/>
								</div>
								<div class="space-y-1.5 sm:col-span-2">
									<Label class="text-xs text-zinc-400">description</Label>
									<Textarea
										bind:value={editDescription}
										rows={3}
										class="rounded-xl border-zinc-700 bg-zinc-900"
									/>
								</div>
								<div class="space-y-1.5">
									<Label class="text-xs text-zinc-400">color</Label>
									<div class="flex gap-2">
										<input
											type="color"
											bind:value={editColor}
											class="h-10 w-12 rounded-xl border border-zinc-700 bg-zinc-900 p-1"
										/>
										<Input
											bind:value={editColor}
											class="rounded-xl border-zinc-700 bg-zinc-900"
										/>
									</div>
								</div>
								<div class="space-y-1.5">
									<Label class="text-xs text-zinc-400">position</Label>
									<Input
										bind:value={editPosition}
										type="number"
										class="rounded-xl border-zinc-700 bg-zinc-900"
									/>
								</div>
								<div class="space-y-1.5">
									<Label class="text-xs text-zinc-400">timezone</Label>
									<Input
										bind:value={editTimezone}
										class="rounded-xl border-zinc-700 bg-zinc-900"
									/>
								</div>
								<label class="flex items-center gap-2 pt-6 text-sm text-zinc-300">
									<input
										type="checkbox"
										bind:checked={editIsDefault}
										class="h-4 w-4 rounded border-zinc-700 bg-zinc-900"
									/>
									default calendar
								</label>
								<div class="space-y-1.5 sm:col-span-2">
									<Label class="text-xs text-zinc-400">project ids</Label>
									<Input
										bind:value={editProjectIds}
										class="rounded-xl border-zinc-700 bg-zinc-900"
									/>
								</div>
								<div class="space-y-1.5 sm:col-span-2">
									<Label class="text-xs text-zinc-400">metadata</Label>
									<Textarea
										bind:value={editMetadata}
										rows={6}
										class="rounded-xl border-zinc-700 bg-zinc-900 font-mono text-xs"
									/>
								</div>
							</div>
							{#if saveError}
								<div
									class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
								>
									{saveError}
								</div>
							{/if}
							<div class="flex gap-2">
								<Button
									variant="outline"
									size="sm"
									class="rounded-xl"
									onclick={saveCalendar}
									disabled={isSaving}
								>
									<Save class="mr-1.5 h-3.5 w-3.5" />
									{isSaving ? 'saving...' : 'save'}
								</Button>
								<Button
									variant="ghost"
									size="sm"
									class="rounded-xl"
									onclick={cancelEdit}
								>
									<X class="mr-1.5 h-3.5 w-3.5" />
									cancel
								</Button>
							</div>
						</div>
					{:else}
						<div class="space-y-4">
							<div
								class="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900 p-4"
							>
								<span
									class="mt-1 h-4 w-4 shrink-0 rounded-full border border-zinc-700"
									style="background-color: {calendar.color}"
								></span>
								<div class="min-w-0 flex-1">
									<div class="flex flex-wrap items-center gap-2">
										<div class="font-medium">{calendar.name}</div>
										{#if calendar.is_default}
											<span
												class="rounded-md bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-emerald-400 uppercase"
												>default</span
											>
										{/if}
									</div>
									{#if calendar.description}
										<div class="mt-1 text-sm whitespace-pre-wrap text-zinc-400">
											{calendar.description}
										</div>
									{/if}
								</div>
							</div>

							<div class="grid gap-3 sm:grid-cols-2">
								<div
									class="rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-sm"
								>
									<div class="text-xs text-zinc-500">timezone</div>
									<div class="mt-1 text-zinc-300">
										{calendar.timezone ?? 'unset'}
									</div>
								</div>
								<div
									class="rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-sm"
								>
									<div class="text-xs text-zinc-500">position</div>
									<div class="mt-1 text-zinc-300">{calendar.position}</div>
								</div>
								<div
									class="rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-sm sm:col-span-2"
								>
									<div class="mb-2 flex items-center gap-2 text-xs text-zinc-500">
										<Folder class="h-3.5 w-3.5" />
										project ids
									</div>
									{#if (calendar.project_ids ?? []).length > 0}
										<div class="flex flex-wrap gap-1.5">
											{#each calendar.project_ids ?? [] as projectId (projectId)}
												<span
													class="rounded-lg bg-zinc-800 px-2.5 py-1 font-mono text-xs text-zinc-300"
													>{projectId}</span
												>
											{/each}
										</div>
									{:else}
										<div class="text-sm text-zinc-500">none</div>
									{/if}
								</div>
							</div>

							<div class="space-y-2">
								<div class="flex items-center justify-between gap-3">
									<div
										class="text-xs font-medium tracking-wider text-zinc-500 uppercase"
									>
										events
									</div>
									<div class="flex items-center gap-2">
										<Button
											variant="outline"
											size="sm"
											class="h-7 rounded-lg px-2 text-xs"
											onclick={previousEventsPage}
											disabled={eventsPageIndex === 0 || isLoadingEvents}
										>
											<ChevronLeft class="mr-1 h-3 w-3" />
											prev
										</Button>
										<span class="text-xs text-zinc-500 tabular-nums">
											page {eventsPageIndex + 1}{events.length > 0
												? ` · ${events.length} items`
												: ''}
										</span>
										<Button
											variant="outline"
											size="sm"
											class="h-7 rounded-lg px-2 text-xs"
											onclick={nextEventsPage}
											disabled={events.length < CALENDAR_EVENT_PAGE_LIMIT ||
												isLoadingEvents}
										>
											next
											<ChevronRight class="ml-1 h-3 w-3" />
										</Button>
									</div>
								</div>
								{#if isLoadingEvents}
									<div
										class="rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-500"
									>
										loading events...
									</div>
								{:else if eventsError}
									<div
										class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
									>
										{eventsError}
									</div>
								{:else if events.length === 0}
									<div
										class="rounded-xl border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500"
									>
										no events in this calendar
									</div>
								{:else}
									<div class="flex flex-col gap-2">
										{#each events as event (event.id)}
											<div
												class="rounded-xl border p-4 {event.id ===
												highlightEventId
													? 'border-rose-500/60 bg-rose-500/10'
													: 'border-zinc-800 bg-zinc-900'}"
											>
												<div
													class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
												>
													<div class="min-w-0 space-y-1">
														<div
															class="truncate font-medium text-zinc-100"
														>
															{event.title}
														</div>
														{#if event.description}
															<div
																class="line-clamp-2 text-sm text-zinc-400"
															>
																{event.description}
															</div>
														{/if}
														<div
															class="flex flex-wrap items-center gap-3 text-xs text-zinc-500"
														>
															<span
																class="inline-flex items-center gap-1.5"
															>
																<Clock class="h-3.5 w-3.5" />
																{formatEventRange(event)}
															</span>
															{#if event.location}
																<span>{event.location}</span>
															{/if}
															<span
																class="font-mono text-[10px] opacity-60"
																>{event.id}</span
															>
														</div>
													</div>
													{#if event.id === highlightEventId}
														<span
															class="shrink-0 rounded-md bg-rose-500/15 px-2 py-1 text-xs text-rose-300"
														>
															matched
														</span>
													{/if}
												</div>
											</div>
										{/each}
									</div>
								{/if}
							</div>

							{#if calendar.metadata_ && Object.keys(calendar.metadata_).length > 0}
								<div class="space-y-2">
									<div
										class="text-xs font-medium tracking-wider text-zinc-500 uppercase"
									>
										metadata
									</div>
									<pre
										class="max-h-64 overflow-auto rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-xs text-zinc-300">{JSON.stringify(
											calendar.metadata_,
											null,
											2
										)}</pre>
								</div>
							{/if}
						</div>
					{/if}
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

{#if calendar}
	<AclModal
		bind:open={showAclModal}
		resourceType="calendar"
		resourceId={calendar.id}
		title={`access rules: ${calendar.name}`}
	/>
{/if}
