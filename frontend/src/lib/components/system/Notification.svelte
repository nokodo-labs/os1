<script lang="ts">
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { Notification } from '$lib/stores/notifications.svelte'

	interface Props {
		notification: Notification
		iconUrl?: string | null
		imageUrl?: string | null
		title: string
		body: string
		timestamp: Date
		isUnread: boolean
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
		onMarkRead,
		onDismiss,
	}: Props = $props()

	// -- expand / collapse --
	const COLLAPSED_HEIGHT = 18

	let expanded = $state(false)
	let bodyMeasureRef: HTMLDivElement | undefined = $state()
	let titleRef: HTMLSpanElement | undefined = $state()
	let isBodyOverflowing = $state(false)
	let isTitleOverflowing = $state(false)
	let expandedHeight = $state(COLLAPSED_HEIGHT)

	const hasImage = $derived(!!imageUrl)
	const canExpand = $derived(isBodyOverflowing || isTitleOverflowing || hasImage)

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

	function toggleExpand() {
		expanded = !expanded
		if (expanded && isUnread && onMarkRead) {
			onMarkRead(notification.id)
		}
	}

	// -- swipe to dismiss (touch only) --
	const SWIPE_THRESHOLD = 80
	const DRAG_DEAD_ZONE = 6

	let swipeX = $state(0)
	let swiping = $state(false)
	let dismissed = $state(false)
	let pointerStart = { x: 0, y: 0 }
	let pointerIntent: 'none' | 'horizontal' | 'vertical' = 'none'

	function onPointerDown(e: PointerEvent) {
		if (!device.isTouch || dismissed) return
		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
		pointerStart = { x: e.clientX, y: e.clientY }
		pointerIntent = 'none'
		swiping = false
		swipeX = 0
	}

	function onPointerMove(e: PointerEvent) {
		if (!device.isTouch || dismissed) return
		const dx = e.clientX - pointerStart.x
		const dy = e.clientY - pointerStart.y
		if (
			pointerIntent === 'none' &&
			(Math.abs(dx) > DRAG_DEAD_ZONE || Math.abs(dy) > DRAG_DEAD_ZONE)
		) {
			pointerIntent = Math.abs(dx) > Math.abs(dy) ? 'horizontal' : 'vertical'
		}
		if (pointerIntent === 'horizontal') {
			swiping = true
			swipeX = dx
		}
	}

	function onPointerUp() {
		if (!device.isTouch || !swiping || dismissed) {
			swiping = false
			swipeX = 0
			return
		}
		if (Math.abs(swipeX) > SWIPE_THRESHOLD) {
			dismissed = true
			swipeX = swipeX > 0 ? 400 : -400
			setTimeout(() => onDismiss?.(notification.id), 280)
		} else {
			swipeX = 0
		}
		swiping = false
	}

	function onPointerCancel() {
		swiping = false
		swipeX = 0
	}

	function swipeStyle(): string {
		if (!device.isTouch || swipeX === 0) return ''
		const opacity = Math.max(0.3, 1 - Math.abs(swipeX) / 300)
		const transition = swiping ? 'none' : 'transform 280ms ease-out, opacity 280ms ease-out'
		return `transform: translateX(${swipeX}px); opacity: ${opacity}; transition: ${transition};`
	}
</script>

<LiquidGlass
	class="relative flex items-start gap-3 rounded-2xl px-3 py-3 text-left {device.isTouch
		? 'touch-pan-y select-none'
		: ''}"
	style={swipeStyle()}
	onpointerdown={(e: PointerEvent) => onPointerDown(e)}
	onpointermove={(e: PointerEvent) => onPointerMove(e)}
	onpointerup={() => onPointerUp()}
	onpointercancel={() => onPointerCancel()}
>
	<!-- icon -->
	<div
		class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/8 text-white/85"
	>
		{#if iconUrl}
			<img src={iconUrl} alt="" class="h-5 w-5 rounded-full object-cover" />
		{:else}
			<AppNotification class="h-5 w-5" />
		{/if}
	</div>

	<!-- content -->
	<div class="min-w-0 flex-1">
		<!-- title row: when expanded, timestamp moves above title -->
		{#if expanded && canExpand}
			<Timestamp
				{timestamp}
				mode="relative"
				minUnit="minute"
				className="block text-[0.6875rem] text-white/50 mb-0.5 transition-all duration-300"
			/>
		{/if}

		<div
			class="flex min-w-0 items-center gap-1.5 text-[0.8125rem] leading-4.5 font-semibold {isUnread
				? 'text-white/90'
				: 'text-white/70'}"
		>
			<span bind:this={titleRef} class="min-w-0 truncate">{title}</span>
			{#if isUnread}
				<span class="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400"></span>
			{/if}
			{#if !expanded}
				<span class="shrink-0 text-white/30">·</span>
				<Timestamp
					{timestamp}
					mode="relative"
					minUnit="minute"
					className="shrink-0 text-[0.6875rem] font-normal text-white/50"
				/>
			{/if}
		</div>

		<!-- body -->
		<div class="relative">
			<div
				class="text-[0.8125rem] {isUnread
					? 'text-white/60'
					: 'text-white/55'} overflow-hidden leading-4.5 transition-[max-height] duration-300 ease-out {!expanded &&
				isBodyOverflowing
					? 'line-clamp-1'
					: ''}"
				style="max-height: {expanded ? expandedHeight : COLLAPSED_HEIGHT}px"
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

		{#if expanded && imageUrl}
			<img src={imageUrl} alt="" class="mt-2 max-h-48 w-full rounded-xl object-cover" />
		{/if}
	</div>

	<!-- right column: dismiss + expand -->
	<div class="flex shrink-0 flex-col items-center gap-1.5">
		{#if !device.isTouch && onDismiss}
			<XMark
				class="size-6 cursor-pointer text-white/50 transition-all duration-150 hover:scale-[1.05] hover:text-white/80 active:scale-[0.97]"
				onclick={() => onDismiss?.(notification.id)}
			/>
		{/if}
		{#if canExpand}
			<button
				type="button"
				class="cursor-pointer text-white/80 transition-all duration-150 hover:text-white"
				onclick={toggleExpand}
			>
				<ChevronDown
					class="size-5 transition-transform duration-300 {expanded ? 'rotate-180' : ''}"
				/>
			</button>
		{/if}
	</div>
</LiquidGlass>
