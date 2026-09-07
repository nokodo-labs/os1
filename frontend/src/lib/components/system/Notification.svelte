<script lang="ts">
	import { swipe, type SwipeDirection } from '$lib/attachments/swipe'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { accentColors } from '$lib/contexts/themeContext.svelte'
	import {
		NOTIFICATION_ENTER_EASING,
		NOTIFICATION_ENTER_KEYFRAMES,
		NOTIFICATION_ENTER_MS,
		NOTIFICATION_EXPAND_MS,
		NOTIFICATION_LEAVE_MS,
		type GroupPosition,
	} from '$lib/resources/dockNotifications'
	import { notificationAccent, notificationIcon } from '$lib/resources/notificationVisuals'
	import { device } from '$lib/stores/device.svelte'
	import type { Notification } from '$lib/stores/notifications.svelte'
	import type { Attachment } from 'svelte/attachments'

	interface Props {
		notification: Notification
		iconUrl?: string | null
		imageUrl?: string | null
		title: string
		body: string
		timestamp: Date
		isUnread: boolean
		/** where the row sits in its day's card, so it knows whether to draw a hairline. */
		position?: GroupPosition
		/** claims this id's one-shot entrance; false once some cell has used it. */
		claimEntrance?: (id: string) => boolean
		onMarkRead?: (id: string) => void
		onDismiss?: (id: string) => void
	}

	let {
		notification,
		iconUrl = null,
		imageUrl = null,
		title,
		body,
		timestamp,
		isUnread,
		position = 'single',
		claimEntrance,
		onMarkRead,
		onDismiss,
	}: Props = $props()

	// -- expand / collapse --
	const COLLAPSED_HEIGHT = 18

	let expanded = $state(false)
	/**
	 * whether the row is at REST closed. the clamp and the image key off this
	 * rather than off `expanded`, so closing gets the same 300ms the opening
	 * does: dropping the clamp on the same tick as the height is what used to
	 * snap the row shut while opening glided.
	 */
	let closed = $state(true)
	let settleTimer: ReturnType<typeof setTimeout> | undefined
	let bodyMeasureRef: HTMLDivElement | undefined = $state()
	let titleRef: HTMLSpanElement | undefined = $state()
	let isBodyOverflowing = $state(false)
	let isTitleOverflowing = $state(false)
	let expandedHeight = $state(COLLAPSED_HEIGHT)

	const hasImage = $derived(!!imageUrl)
	const canExpand = $derived(isBodyOverflowing || isTitleOverflowing || hasImage)
	// pointer input dismisses with the X, touch dismisses with a swipe - so on
	// touch the X is not hidden, it does not exist, and reserves nothing.
	const canHover = $derived(device.hasHover && !device.isCoarsePointer)
	const canDismissByButton = $derived(canHover && !!onDismiss)
	const TypeIcon = $derived(notificationIcon(notification.event?.type))
	// the owning app's accent, applied the way the homepage suggestion rows tint
	// their app glyph: 14% fill, the accent itself for the glyph, an 18% rim.
	const accent = $derived(accentColors[notificationAccent(notification.event?.type)])

	$effect(() => {
		const shouldMeasure = device.width >= 0 || body.length >= 0 || title.length >= 0
		if (bodyMeasureRef && shouldMeasure) {
			expandedHeight = bodyMeasureRef.scrollHeight
			isBodyOverflowing = expandedHeight > COLLAPSED_HEIGHT + 1
		}
		if (titleRef && shouldMeasure) {
			isTitleOverflowing = titleRef.scrollWidth > titleRef.clientWidth + 1
		}
	})

	$effect(() => {
		if (isUnread && !canExpand && onMarkRead) {
			onMarkRead(notification.id)
		}
	})

	$effect(() => () => clearTimeout(settleTimer))

	function toggleExpand() {
		expanded = !expanded
		clearTimeout(settleTimer)
		if (expanded) {
			// unclamp first, so the height has somewhere to travel to
			closed = false
			if (isUnread && onMarkRead) onMarkRead(notification.id)
			return
		}
		if (device.prefersReducedMotion) closed = true
		else settleTimer = setTimeout(() => (closed = true), NOTIFICATION_EXPAND_MS)
	}

	// -- entrance: a notification that arrives while the dock is open --
	// the id is a real argument for the same reason the swipe takes one: the
	// dock's list recycles cells, so the claim has to be re-made (and refused)
	// the moment this cell becomes another notification.
	function entrance(id: string): Attachment<HTMLElement> {
		return (node) => {
			if (!claimEntrance?.(id)) return
			if (device.prefersReducedMotion || typeof node.animate !== 'function') return
			node.animate(NOTIFICATION_ENTER_KEYFRAMES, {
				duration: NOTIFICATION_ENTER_MS,
				easing: NOTIFICATION_ENTER_EASING,
			})
		}
	}

	// -- dismissal --
	let leaving = $state(false)

	/** 0..1 travel of an in-flight swipe, and the way it is heading. */
	let swipeProgress = $state(0)
	let swipeDirection = $state<SwipeDirection>('left')

	// a recycled cell must never inherit the previous row's exit, nor the travel
	// of a gesture that was aimed at the row it used to be.
	$effect(() => {
		void notification.id
		leaving = false
		swipeProgress = 0
	})

	function dismiss(): void {
		if (leaving) return
		const id = notification.id
		if (device.prefersReducedMotion) {
			onDismiss?.(id)
			return
		}
		leaving = true
		setTimeout(() => onDismiss?.(id), NOTIFICATION_LEAVE_MS)
	}

	// -- swipe to dismiss (touch only) --
	const SWIPE_THRESHOLD = 80
	/** how much opacity a full swipe eats, so the row reads as leaving. */
	const SWIPE_FADE = 0.3

	// the id is a real argument so the dock's virtual list, which recycles rows,
	// re-attaches (and so resets the travel) when this row becomes another one.
	function swipeDismiss(enabled: boolean, id: string): Attachment<HTMLElement> {
		return (node) =>
			swipe({
				enabled,
				direction: ['left', 'right'],
				threshold: SWIPE_THRESHOLD,
				release: 'fly',
				onProgress: (progress, direction) => {
					node.style.opacity = progress === 0 ? '' : `${1 - progress * SWIPE_FADE}`
					swipeProgress = progress
					swipeDirection = direction
				},
				onTrigger: () => onDismiss?.(id),
			})(node)
	}
</script>

<div class="relative">
	{#if swipeProgress > 0}
		<!-- the dismissal's glyph, sitting where the card is sliding off to, the
		     way the bubble's reply arrow fills in behind a swipe: it stays put
		     while the row travels over and past it. -->
		<div
			data-swipe-hint
			data-direction={swipeDirection}
			class="text-foreground/60 pointer-events-none absolute top-1/2 flex size-7 items-center justify-center rounded-full"
			class:left-3={swipeDirection === 'right'}
			class:right-3={swipeDirection === 'left'}
			style:opacity={swipeProgress}
			style:transform="translateY(-50%) scale({0.6 + swipeProgress * 0.4})"
			aria-hidden="true"
		>
			<XMark class="size-4.5" />
		</div>
	{/if}

	<div
		{@attach swipeDismiss(device.isTouch, notification.id)}
		{@attach entrance(notification.id)}
		class="notif-cell group/notif relative flex items-start gap-3 py-2.5 pr-2 pl-3 text-left {device.isTouch
			? 'select-none'
			: ''}"
		class:notif-cell--unread={isUnread}
		class:notif-cell--leaving={leaving}
		style="--notif-accent: {accent.primary}; --notif-accent-rgb: {accent.rgb}"
		data-notification-cell
		data-position={position}
	>
		{#if position === 'middle' || position === 'last'}
			<!-- the card's hairline between rows, inset past the icon like the inbox's -->
			<span
				class="bg-foreground/10 pointer-events-none absolute top-0 right-0 left-15 h-px"
				aria-hidden="true"
			></span>
		{/if}

		<!-- icon: the app that owns the backing event, in that app's accent -->
		<div
			class="rounded-pill flex size-9 shrink-0 items-center justify-center bg-[rgb(var(--notif-accent-rgb)/0.14)] text-(--notif-accent) shadow-[inset_0_0_0_1px_rgb(var(--notif-accent-rgb)/0.18)]"
		>
			{#if iconUrl}
				<img src={iconUrl} alt="" class="h-5 w-5 rounded-full object-cover" />
			{:else}
				<TypeIcon class="h-5 w-5" />
			{/if}
		</div>

		<!-- content -->
		<div class="min-w-0 flex-1">
			<!-- title line: the name carries the weight, the clock stays quiet meta -->
			<div class="flex min-w-0 items-baseline gap-2">
				<span
					bind:this={titleRef}
					class="min-w-0 flex-1 truncate text-[0.8125rem] leading-4.5 {isUnread
						? 'text-foreground font-semibold'
						: 'text-foreground/75 font-medium'}"
				>
					{title}
				</span>
				{#if isUnread}
					<span
						class="bg-(--accent-primary) size-2 shrink-0 self-center rounded-full"
						aria-label="unread"
					></span>
				{/if}
				<Timestamp
					{timestamp}
					mode="relative"
					minUnit="minute"
					className="text-foreground/40 shrink-0 text-[0.6875rem]"
				/>
			</div>

			<!-- body -->
			<div class="relative">
				<div
					class="text-[0.8125rem] {isUnread
						? 'text-foreground/70'
						: 'text-foreground/50'} overflow-hidden leading-4.5 {device.prefersReducedMotion
						? ''
						: 'transition-[max-height] duration-300 ease-out'} {closed &&
					isBodyOverflowing
						? 'line-clamp-1'
						: ''}"
					style="max-height: {expanded ? expandedHeight : COLLAPSED_HEIGHT}px"
					data-notification-body
				>
					{body}
				</div>
				<!-- invisible measure element: wraps naturally, gives us true expanded height -->
				<div
					bind:this={bodyMeasureRef}
					class="pointer-events-none invisible absolute inset-x-0 top-0 text-[0.8125rem] leading-4.5"
					aria-hidden="true"
				>
					{body}
				</div>
			</div>

			{#if !closed && imageUrl}
				<img src={imageUrl} alt="" class="mt-2 max-h-48 w-full rounded-xl object-cover" />
			{/if}
		</div>

		<!-- controls, level with the title: side by side rather than stacked, so a
		     closed row is only ever as tall as what it shows.  the X is always
		     there under a pointer; touch has no slot for it at all and swipes. -->
		{#if canExpand || canDismissByButton}
			<div class="flex shrink-0 items-center gap-0.5 pt-0.5" data-notification-controls>
				{#if canExpand}
					<button
						type="button"
						class="interactive-subtle text-foreground/55 hover:text-foreground/85 flex size-6 items-center justify-center rounded-full"
						aria-label={expanded ? 'collapse notification' : 'expand notification'}
						aria-expanded={expanded}
						onclick={toggleExpand}
					>
						<ChevronDown
							class="size-4.5 transition-transform duration-300 {expanded
								? 'rotate-180'
								: ''}"
						/>
					</button>
				{/if}
				{#if canDismissByButton}
					<button
						type="button"
						class="interactive-subtle text-foreground/45 hover:text-foreground/85 flex size-6 items-center justify-center rounded-full"
						aria-label="dismiss notification"
						onclick={dismiss}
					>
						<XMark class="size-4" />
					</button>
				{/if}
			</div>
		{/if}
	</div>
</div>

<style>
	/*
	   a row is a flat tint on the day card it sits in (F138): the card is the
	   frosted surface and owns the rim and the corners, so nothing here carries
	   a backdrop-filter, a rim or a radius of its own.  `position` still says
	   where the row sits, which is what decides its hairline.
	 */
	.notif-cell {
		background-color: color-mix(in oklab, var(--foreground) 6%, transparent);
		transition: background-color 240ms cubic-bezier(0.4, 0, 0.2, 1);
	}

	/* unread reads as the accent, and settles to the neutral tint when read */
	.notif-cell--unread {
		background-color: color-mix(in oklab, var(--accent-primary) 15%, transparent);
	}

	/*
	   dismissal by button: fly to the edge, then hand the row over - the same
	   280ms the notification toasts leave on.  declared here so entering this
	   state is what runs the transition, leaving the entrance animation alone.
	 */
	.notif-cell--leaving {
		transform: translateX(105%);
		opacity: 0;
		pointer-events: none;
		transition:
			transform 280ms cubic-bezier(0.4, 0, 1, 1),
			opacity 280ms cubic-bezier(0.4, 0, 1, 1);
	}
</style>
