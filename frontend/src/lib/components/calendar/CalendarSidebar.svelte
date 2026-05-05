<script lang="ts">
	import CalendarManageModal from '$lib/components/calendar/CalendarManageModal.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import PopupMenu from '$lib/components/primitives/PopupMenu.svelte'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import {
		calendars,
		scheduledItems,
		type Calendar as CalendarRecord,
		type ScheduledItem,
	} from '$lib/stores/calendars.svelte'
	import { modals } from '$lib/stores/modals.svelte'

	interface Props {
		isMobile?: boolean
	}

	let { isMobile = false }: Props = $props()
	let manageModalOpen = $state(false)
	let manageCalendar = $state<CalendarRecord | null>(null)
	let openCalendarMenuId = $state<string | null>(null)
	let calendarMenuButtonEl = $state<HTMLElement | null>(null)
	let selectedCalendarId = $state<string | null>(null)

	const REMINDERS_CALENDAR_ID = '__reminders__'

	type ScheduleItem = {
		id: string
		title: string
		startAt: string
		endAt: string
		allDay: boolean
		calendarId: string | null
		calendarLabel: string
		source: ScheduledItem['kind']
	}

	$effect(() => {
		void calendars.load()
		const window = sidebarWindow()
		void scheduledItems.load({ startAt: window.startAt, endAt: window.endAt })
	})

	const calendarList = $derived(calendars.all)
	const scheduleItems = $derived(
		scheduledItems.all
			.map(toScheduleItem)
			.filter(matchesSelectedCalendar)
			.toSorted((left, right) => Date.parse(left.startAt) - Date.parse(right.startAt))
	)
	const now = $derived(new Date())
	const todayStart = $derived(new Date(now.getFullYear(), now.getMonth(), now.getDate()))
	const tomorrowStart = $derived(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1))
	const nextWindow = $derived(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 14))

	const todayEvents = $derived(
		scheduleItems.filter((event) => overlapsRange(event, todayStart, tomorrowStart)).slice(0, 5)
	)

	const upcomingEvents = $derived(
		scheduleItems
			.filter((event) => {
				const start = new Date(event.startAt)
				return start >= tomorrowStart && start < nextWindow
			})
			.slice(0, 8)
	)

	function overlapsRange(event: ScheduleItem, start: Date, end: Date): boolean {
		const eventStart = new Date(event.startAt)
		const eventEnd = new Date(event.endAt)
		return eventStart < end && eventEnd > start
	}

	function toScheduleItem(item: ScheduledItem): ScheduleItem {
		const start = new Date(item.effective_start_at)
		const endAt =
			item.effective_end_at ?? new Date(start.getTime() + 30 * 60 * 1000).toISOString()
		const calendarId =
			item.kind === 'reminder' ? REMINDERS_CALENDAR_ID : (item.calendar_id ?? null)
		return {
			id: item.id,
			title: item.title,
			startAt: item.effective_start_at,
			endAt,
			allDay: item.all_day,
			calendarId,
			calendarLabel: item.kind === 'reminder' ? 'reminders' : calendarName(item.calendar_id),
			source: item.kind,
		}
	}

	function matchesSelectedCalendar(event: ScheduleItem): boolean {
		if (selectedCalendarId === null) return true
		return event.calendarId === selectedCalendarId
	}

	function sidebarWindow(): { startAt: string; endAt: string } {
		const now = new Date()
		const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
		const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 14)
		return { startAt: start.toISOString(), endAt: end.toISOString() }
	}

	function formatDate(date: Date): string {
		return new Intl.DateTimeFormat(undefined, {
			weekday: 'short',
			month: 'short',
			day: 'numeric',
		})
			.format(date)
			.toLowerCase()
	}

	function formatTime(event: ScheduleItem): string {
		if (event.allDay) return 'all day'
		const formatter = new Intl.DateTimeFormat(undefined, {
			hour: 'numeric',
			minute: '2-digit',
		})
		return `${formatter.format(new Date(event.startAt)).toLowerCase()} - ${formatter
			.format(new Date(event.endAt))
			.toLowerCase()}`
	}

	function createEvent(): void {
		window.dispatchEvent(new CustomEvent('calendar:add'))
	}

	function createCalendar(): void {
		closeCalendarMenu()
		manageCalendar = null
		manageModalOpen = true
	}

	function editCalendar(calendar: CalendarRecord): void {
		closeCalendarMenu()
		manageCalendar = calendar
		manageModalOpen = true
	}

	function closeManageModal(): void {
		manageModalOpen = false
		manageCalendar = null
	}

	function toggleCalendarMenu(calendarId: string, anchorEl: HTMLElement | null): void {
		if (openCalendarMenuId === calendarId) {
			closeCalendarMenu()
			return
		}
		openCalendarMenuId = calendarId
		calendarMenuButtonEl = anchorEl
	}

	function closeCalendarMenu(): void {
		openCalendarMenuId = null
		calendarMenuButtonEl = null
	}

	function shareCalendar(calendar: CalendarRecord): void {
		closeCalendarMenu()
		modals.open('resource-access', {
			resourceType: 'calendar',
			resourceId: calendar.id,
			title: calendar.name,
		})
	}

	function requestDeleteCalendar(calendar: CalendarRecord): void {
		closeCalendarMenu()
		modals.open('confirm-delete', {
			title: 'delete calendar?',
			description: calendar.name,
			onDelete: () => calendars.remove(calendar.id),
		})
	}

	function selectCalendar(calendarId: string | null): void {
		selectedCalendarId = calendarId
		window.dispatchEvent(
			new CustomEvent('calendar:filter', {
				detail: { calendarId },
			})
		)
	}

	function focusEvent(event: ScheduleItem): void {
		window.dispatchEvent(
			new CustomEvent('calendar:focus', {
				detail: { eventId: event.id, startAt: event.startAt },
			})
		)
	}

	function allCalendarsCount(): number {
		return calendarList.length + 1
	}

	function calendarName(calendarId: string | null | undefined): string {
		return calendarList.find((calendar) => calendar.id === calendarId)?.name ?? 'calendar'
	}
</script>

<div
	class="flex min-h-0 flex-col {isMobile ? '' : 'h-full'}"
	style="gap: var(--spacing-header-content);"
>
	<header
		class="{isMobile
			? 'mt-0'
			: 'mt-7'} flex max-h-22 items-center justify-between gap-3 px-2 py-5 pb-6"
	>
		<PageTitle icon={Calendar} label="calendar" iconColor="text-(--accent-primary)" tag="h2" />
		{#if !isMobile}
			<button
				type="button"
				onclick={createEvent}
				class="text-foreground/80 hover:text-foreground flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
				aria-label="create event"
			>
				<Plus class="h-6 w-6" />
			</button>
		{/if}
	</header>

	<nav class="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2">
		{#if (!scheduledItems.hydrated && scheduledItems.loading) || (!calendars.hydrated && calendars.loading)}
			<div class="flex flex-1 items-center justify-center py-8">
				<NokodoLoader className="opacity-70" expanded={false} />
			</div>
		{:else}
			<section class="space-y-2 pb-6">
				<div
					class="text-foreground/45 px-2 text-xs font-medium tracking-[0.12em] uppercase"
				>
					today
				</div>
				{#if todayEvents.length === 0}
					<div
						class="rounded-container border-foreground/14 bg-foreground/5 text-foreground/55 border p-3 text-center text-sm"
					>
						no events today
					</div>
				{:else}
					{#each todayEvents as event (event.id)}
						<SidebarListItem onSelect={() => focusEvent(event)} showChevron={true}>
							<span class="flex min-w-0 flex-col">
								<span
									class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
								>
									{event.title}
								</span>
								<span class="text-foreground/55 min-w-0 truncate text-xs">
									{formatTime(event)} - {event.calendarLabel}
								</span>
							</span>
						</SidebarListItem>
					{/each}
				{/if}
			</section>

			<section class="space-y-2 pb-6">
				<div
					class="text-foreground/45 px-2 text-xs font-medium tracking-[0.12em] uppercase"
				>
					upcoming
				</div>
				{#if upcomingEvents.length === 0}
					<div
						class="rounded-container border-foreground/14 bg-foreground/5 text-foreground/55 border p-3 text-center text-sm"
					>
						nothing scheduled
					</div>
				{:else}
					{#each upcomingEvents as event (event.id)}
						<SidebarListItem onSelect={() => focusEvent(event)} showChevron={true}>
							<span class="flex min-w-0 flex-col">
								<span
									class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
								>
									{event.title}
								</span>
								<span class="text-foreground/55 min-w-0 truncate text-xs">
									{formatDate(new Date(event.startAt))} - {formatTime(event)} - {event.calendarLabel}
								</span>
							</span>
						</SidebarListItem>
					{/each}
				{/if}
			</section>

			<section class="space-y-2 pb-2">
				<div class="flex items-center justify-between gap-2 px-2">
					<div class="text-foreground/45 text-xs font-medium tracking-[0.12em] uppercase">
						calendars
					</div>
					<button
						type="button"
						class="text-foreground/65 hover:bg-foreground/8 hover:text-foreground flex h-8 w-8 cursor-pointer items-center justify-center rounded-full bg-transparent transition-all"
						aria-label="create calendar"
						onclick={createCalendar}
					>
						<Plus class="h-4 w-4" />
					</button>
				</div>
				<SidebarListItem
					selected={selectedCalendarId === null}
					onSelect={() => selectCalendar(null)}
				>
					{#snippet leading()}
						<span
							class="rounded-pill bg-foreground/8 text-foreground/80 flex h-8 w-8 items-center justify-center"
						>
							<Calendar class="h-5 w-5" />
						</span>
					{/snippet}
					<span class="flex min-w-0 items-center gap-2">
						<span
							class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
						>
							all calendars
						</span>
						<span class="text-foreground/55 text-xs">{allCalendarsCount()}</span>
					</span>
				</SidebarListItem>

				<SidebarListItem
					selected={selectedCalendarId === REMINDERS_CALENDAR_ID}
					onSelect={() => selectCalendar(REMINDERS_CALENDAR_ID)}
				>
					{#snippet leading()}
						<span
							class="rounded-pill bg-foreground/8 text-foreground/80 flex h-8 w-8 items-center justify-center"
						>
							<ListBullet class="h-5 w-5" />
						</span>
					{/snippet}
					<span class="flex min-w-0 items-center gap-2">
						<span
							class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
						>
							reminders
						</span>
						<span class="text-foreground/55 text-xs"
							>{scheduledItems.all.filter((item) => item.kind === 'reminder')
								.length}</span
						>
					</span>
				</SidebarListItem>

				{#each calendarList as calendar (calendar.id)}
					<div class="relative">
						<SidebarListItem
							selected={selectedCalendarId === calendar.id}
							onSelect={() => selectCalendar(calendar.id)}
							actionsVisibility="always"
						>
							{#snippet leading()}
								<span
									class="rounded-pill flex h-8 w-8 items-center justify-center"
									style={`background-color: ${calendar.color}24`}
								>
									<span
										class="h-3 w-3 rounded-full"
										style={`background-color: ${calendar.color}`}
									></span>
								</span>
							{/snippet}
							<span class="flex min-w-0 items-center gap-2">
								<span
									class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
								>
									{calendar.name}
								</span>
								{#if calendar.is_default}
									<span class="text-foreground/45 shrink-0 text-xs">default</span>
								{/if}
							</span>
							{#snippet actions()}
								<button
									type="button"
									class="text-foreground/65 hover:bg-foreground/8 hover:text-foreground flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full border-none bg-transparent transition-all"
									aria-label="calendar options"
									onclick={(event) => {
										event.stopPropagation()
										toggleCalendarMenu(calendar.id, event.currentTarget)
									}}
								>
									<EllipsisHorizontal class="h-5 w-5" />
								</button>
							{/snippet}
						</SidebarListItem>

						<PopupMenu
							open={openCalendarMenuId === calendar.id}
							anchorEl={calendarMenuButtonEl}
							onClose={closeCalendarMenu}
						>
							<button
								type="button"
								class="rounded-pill text-foreground/80 hover:bg-foreground/10 flex w-full cursor-pointer items-center gap-2 border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150"
								onclick={() => editCalendar(calendar)}
							>
								<InfoCircle class="h-4 w-4" />
								properties
							</button>
							<button
								type="button"
								class="rounded-pill text-foreground/80 hover:bg-foreground/10 flex w-full cursor-pointer items-center gap-2 border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150"
								onclick={() => shareCalendar(calendar)}
							>
								<Share class="h-4 w-4" />
								share
							</button>
							{#if !calendar.is_default}
								<div class="bg-foreground/10 my-1 h-px w-full"></div>
								<button
									type="button"
									class="rounded-pill text-foreground/80 flex w-full cursor-pointer items-center gap-2 border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-red-500/10 hover:text-red-300"
									onclick={() => requestDeleteCalendar(calendar)}
								>
									<Trash class="h-4 w-4 text-red-400" />
									delete
								</button>
							{/if}
						</PopupMenu>
					</div>
				{/each}
			</section>
		{/if}
	</nav>

	<CalendarManageModal
		open={manageModalOpen}
		calendar={manageCalendar}
		onClose={closeManageModal}
	/>
</div>
