<script lang="ts">
	import CalendarManageModal from '$lib/components/calendar/CalendarManageModal.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import ScrollTopShadow from '$lib/components/ScrollTopShadow.svelte'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import type { ResourceProjectOption } from '$lib/components/widgets/ResourceProjectsMenu.svelte'
	import ResourceProjectsMenu from '$lib/components/widgets/ResourceProjectsMenu.svelte'
	import {
		calendars,
		scheduledItems,
		type Calendar as CalendarRecord,
		type ScheduledItem,
	} from '$lib/stores/calendars.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { projects } from '$lib/stores/projects.svelte'
	import {
		canDeleteAccessLevel,
		canEditAccessLevel,
		canShareAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'

	interface Props {
		isMobile?: boolean
		onClose?: () => void
	}

	let { isMobile = false, onClose }: Props = $props()
	const sidebarListEdgeStyle = $derived(
		isMobile
			? 'width: 100%;'
			: 'margin-left: calc(0px - var(--spacing-page-x)); margin-right: calc(0px - var(--spacing-page-x)); width: calc(100% + var(--spacing-page-x) + var(--spacing-page-x));'
	)
	let manageModalOpen = $state(false)
	let manageCalendar = $state<CalendarRecord | null>(null)
	let openCalendarMenuId = $state<string | null>(null)
	let calendarMenuButtonEl = $state<HTMLElement | null>(null)
	let selectedCalendarId = $state<string | null>(null)
	let ownedCalendarsOpen = $state(true)
	let sharedCalendarsOpen = $state(true)
	let scrollEl = $state<HTMLElement | null>(null)

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
	const currentUserId = $derived(session.currentUserId)
	const ownedCalendars = $derived(
		currentUserId
			? calendarList.filter((calendar) => calendar.owner_id === currentUserId)
			: calendarList
	)
	const sharedCalendars = $derived(
		currentUserId ? calendarList.filter((calendar) => calendar.owner_id !== currentUserId) : []
	)
	const effectiveSharedCalendarsOpen = $derived(
		sharedCalendars.length > 0 ? sharedCalendarsOpen : false
	)
	const manageableProjectOptions = $derived.by((): ResourceProjectOption[] =>
		projects.list
			.filter((project) =>
				canEditAccessLevel(resourceAccess.level('project', project.id, project.owner_id))
			)
			.map((project) => ({
				id: project.id,
				name: project.name,
				owner_id: project.owner_id,
			}))
	)
	const showCalendarSections = $derived(Boolean(currentUserId))
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

	$effect(() => {
		if (sharedCalendars.length === 0) return
		void session.ensureUsers(sharedCalendars.map((calendar) => calendar.owner_id))
	})

	$effect(() => {
		for (const calendar of calendarList) {
			void resourceAccess.ensure('calendar', calendar.id, calendar.owner_id)
		}
	})

	$effect(() => {
		void projects.load()
	})

	$effect(() => {
		for (const project of projects.list) {
			void resourceAccess.ensure('project', project.id, project.owner_id)
		}
	})

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

	function createCalendar(): void {
		closeCalendarMenu()
		manageCalendar = null
		manageModalOpen = true
	}

	function editCalendar(calendar: CalendarRecord): void {
		if (!canEditCalendar(calendar)) return
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
		if (!canShareCalendar(calendar)) return
		closeCalendarMenu()
		modals.open('resource-access', {
			resourceType: 'calendar',
			resourceId: calendar.id,
			title: calendar.name,
		})
	}

	function requestDeleteCalendar(calendar: CalendarRecord): void {
		if (!canDeleteCalendar(calendar)) return
		closeCalendarMenu()
		modals.open('confirm-delete', {
			title: 'delete calendar?',
			description: calendar.name,
			onDelete: () => calendars.remove(calendar.id),
		})
	}

	async function handleCalendarProjectToggle(
		calendar: CalendarRecord,
		projectId: string,
		selected: boolean
	): Promise<void> {
		if (!canEditCalendar(calendar)) return
		const currentIds = calendar.project_ids ?? []
		const nextIds = selected
			? [...new Set([...currentIds, projectId])]
			: currentIds.filter((id) => id !== projectId)
		await calendars.update(calendar.id, { project_ids: nextIds })
		projects.invalidateResourceCounts([...new Set([...currentIds, ...nextIds])])
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

	function calendarOwnerLabel(calendar: CalendarRecord): string | null {
		if (calendar.owner_id === currentUserId) return null
		return session.authorLabel(calendar.owner_id)
	}

	function calendarAccessLevel(calendar: CalendarRecord) {
		return resourceAccess.level('calendar', calendar.id, calendar.owner_id)
	}

	function canEditCalendar(calendar: CalendarRecord): boolean {
		return canEditAccessLevel(calendarAccessLevel(calendar))
	}

	function canShareCalendar(calendar: CalendarRecord): boolean {
		return canShareAccessLevel(calendarAccessLevel(calendar))
	}

	function canDeleteCalendar(calendar: CalendarRecord): boolean {
		return canDeleteAccessLevel(calendarAccessLevel(calendar))
	}
</script>

{#snippet emptySection(message: string)}
	<EmptyState label={message} compact />
{/snippet}

{#snippet calendarRow(calendar: CalendarRecord)}
	{@const ownerLabel = calendarOwnerLabel(calendar)}
	<div class="relative px-3">
		<SidebarListItem
			selected={selectedCalendarId === calendar.id}
			onSelect={() => selectCalendar(calendar.id)}
			actionsVisibility={device.isTouch ? 'always' : 'reserve-hover'}
			showChevron={true}
		>
			{#snippet leading()}
				<span
					class="rounded-pill flex h-8 w-8 items-center justify-center"
					style={`background-color: ${calendar.color}24`}
				>
					<span class="h-3 w-3 rounded-full" style={`background-color: ${calendar.color}`}
					></span>
				</span>
			{/snippet}
			<span class="flex min-w-0 flex-col">
				<span class="flex min-w-0 items-center gap-2">
					<span class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium">
						{calendar.name}
					</span>
					{#if calendar.is_default}
						<span class="text-foreground/45 shrink-0 text-xs">default</span>
					{/if}
				</span>
				{#if ownerLabel}
					<span class="text-foreground/55 min-w-0 truncate text-xs">by {ownerLabel}</span>
				{/if}
			</span>
			{#snippet actions()}
				{#if canEditCalendar(calendar) || canShareCalendar(calendar) || canDeleteCalendar(calendar)}
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
				{/if}
			{/snippet}
		</SidebarListItem>

		<PopupMenu
			open={openCalendarMenuId === calendar.id}
			anchorEl={calendarMenuButtonEl}
			onClose={closeCalendarMenu}
		>
			{#if canEditCalendar(calendar)}
				<MenuItem onclick={() => editCalendar(calendar)}>
					{#snippet icon()}<InfoCircle variant="solid" class="size-full" />{/snippet}
					properties
				</MenuItem>
			{/if}
			{#if canShareCalendar(calendar)}
				<MenuItem onclick={() => shareCalendar(calendar)}>
					{#snippet icon()}<Share class="size-full" strokeWidth="2.1" />{/snippet}
					share
				</MenuItem>
			{/if}
			{#if canEditCalendar(calendar)}
				<ResourceProjectsMenu
					projectOptions={manageableProjectOptions}
					selectedProjectIds={calendar.project_ids ?? []}
					onProjectToggle={(projectId, selected) =>
						handleCalendarProjectToggle(calendar, projectId, selected)}
				/>
			{/if}
			{#if !calendar.is_default && canDeleteCalendar(calendar)}
				<div class="bg-foreground/10 my-1 h-px w-full"></div>
				<MenuItem destructive onclick={() => requestDeleteCalendar(calendar)}>
					{#snippet icon()}<Trash
							class="size-full text-red-400"
							strokeWidth="2.1"
						/>{/snippet}
					delete
				</MenuItem>
			{/if}
		</PopupMenu>
	</div>
{/snippet}

{#snippet sectionHeader(label: string, count: number, open: boolean, onToggle: () => void)}
	<button
		type="button"
		class="text-foreground/70 hover:text-foreground/90 flex w-full cursor-pointer items-center gap-1.5 bg-transparent px-5 py-2 text-xs font-semibold tracking-wide uppercase transition-colors duration-150"
		onclick={onToggle}
		aria-expanded={open}
	>
		<ChevronDown class="h-3 w-3 transition-transform duration-200 {open ? '' : '-rotate-90'}" />
		{label}
		<span class="text-foreground/50 font-normal">({count})</span>
	</button>
{/snippet}

{#snippet calendarsSection()}
	<section class="space-y-2 pb-6">
		<div class="flex items-center gap-2 px-5">
			<div class="text-foreground/45 text-xs font-medium tracking-[0.12em] uppercase">
				calendars
			</div>
		</div>
		<div class="px-3">
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
					<span class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium">
						all calendars
					</span>
					<span class="text-foreground/55 text-xs">{allCalendarsCount()}</span>
				</span>
			</SidebarListItem>
		</div>

		<div class="px-3">
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
					<span class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium">
						reminders
					</span>
					<span class="text-foreground/55 text-xs"
						>{scheduledItems.all.filter((item) => item.kind === 'reminder')
							.length}</span
					>
				</span>
			</SidebarListItem>
		</div>

		{#if showCalendarSections}
			<div class="pt-3">
				{@render sectionHeader(
					'your calendars',
					ownedCalendars.length,
					ownedCalendarsOpen,
					() => {
						ownedCalendarsOpen = !ownedCalendarsOpen
					}
				)}
				{#if ownedCalendarsOpen}
					{#if ownedCalendars.length > 0}
						<div class="space-y-1">
							{#each ownedCalendars as calendar (calendar.id)}
								{@render calendarRow(calendar)}
							{/each}
						</div>
					{:else}
						{@render emptySection('no calendars yet')}
					{/if}
				{/if}
			</div>

			<div class="pt-3">
				{@render sectionHeader(
					'shared with you',
					sharedCalendars.length,
					effectiveSharedCalendarsOpen,
					() => {
						sharedCalendarsOpen = !sharedCalendarsOpen
					}
				)}
				{#if effectiveSharedCalendarsOpen}
					{#if sharedCalendars.length > 0}
						<div class="space-y-1">
							{#each sharedCalendars as calendar (calendar.id)}
								{@render calendarRow(calendar)}
							{/each}
						</div>
					{:else}
						{@render emptySection('no shared calendars')}
					{/if}
				{/if}
			</div>
		{:else}
			{#each calendarList as calendar (calendar.id)}
				{@render calendarRow(calendar)}
			{/each}
		{/if}
	</section>
{/snippet}

<div class="flex h-full min-h-0 flex-col">
	<header
		class="{isMobile
			? 'pt-5 pb-4'
			: 'mt-(--master-detail-header-top) mb-(--spacing-island-content) h-(--master-detail-header-height) py-0'} relative z-10 flex shrink-0 items-center justify-between gap-3 px-2"
	>
		<PageTitle icon={Calendar} label="calendar" iconColor="text-(--accent-primary)" tag="h2" />
		{#if isMobile && onClose}
			<button
				type="button"
				class="text-foreground relative flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full border border-transparent bg-transparent transition-all"
				aria-label="close calendar sidebar"
				onclick={onClose}
			>
				<ChevronLeft class="h-8 w-8" />
			</button>
		{:else if !isMobile}
			<button
				type="button"
				onclick={createCalendar}
				class="text-foreground/80 hover:text-foreground flex h-12 w-12 cursor-pointer items-center justify-center bg-transparent transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97]"
				aria-label="create calendar"
			>
				<Plus class="h-6 w-6" />
			</button>
		{/if}
	</header>

	<div class="relative min-h-0 flex-1 overflow-hidden" style={sidebarListEdgeStyle}>
		<nav
			bind:this={scrollEl}
			class="flex h-full min-h-0 w-full flex-col overflow-y-auto pt-2 pb-6"
		>
			{#if (!scheduledItems.hydrated && scheduledItems.loading) || (!calendars.hydrated && calendars.loading)}
				<div class="flex flex-1 items-center justify-center py-8">
					<NokodoLoader className="opacity-70" expanded={false} />
				</div>
			{:else}
				{@render calendarsSection()}

				<section class="space-y-2 pb-6">
					<div
						class="text-foreground/45 px-5 text-xs font-medium tracking-[0.12em] uppercase"
					>
						today
					</div>
					{#if todayEvents.length === 0}
						<EmptyState label="no events today" compact />
					{:else}
						{#each todayEvents as event (event.id)}
							<div class="px-3">
								<SidebarListItem
									onSelect={() => focusEvent(event)}
									paddingClass="py-2.5 pr-3 pl-4"
								>
									<span class="flex min-w-0 flex-col">
										<span
											class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
										>
											{event.title}
										</span>
										<span class="text-foreground/55 min-w-0 truncate text-xs">
											{formatTime(event)} · {event.calendarLabel}
										</span>
									</span>
								</SidebarListItem>
							</div>
						{/each}
					{/if}
				</section>

				<section class="space-y-2 pb-6">
					<div
						class="text-foreground/45 px-5 text-xs font-medium tracking-[0.12em] uppercase"
					>
						upcoming
					</div>
					{#if upcomingEvents.length === 0}
						<EmptyState label="nothing scheduled" compact />
					{:else}
						{#each upcomingEvents as event (event.id)}
							<div class="px-3">
								<SidebarListItem
									onSelect={() => focusEvent(event)}
									paddingClass="py-2.5 pr-3 pl-4"
								>
									<span class="flex min-w-0 flex-col">
										<span
											class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
										>
											{event.title}
										</span>
										<span class="text-foreground/55 min-w-0 truncate text-xs">
											{formatDate(new Date(event.startAt))} · {formatTime(
												event
											)} · {event.calendarLabel}
										</span>
									</span>
								</SidebarListItem>
							</div>
						{/each}
					{/if}
				</section>
			{/if}
		</nav>
		<ScrollTopShadow target={scrollEl} />
	</div>

	<CalendarManageModal
		open={manageModalOpen}
		calendar={manageCalendar}
		onClose={closeManageModal}
	/>
</div>
