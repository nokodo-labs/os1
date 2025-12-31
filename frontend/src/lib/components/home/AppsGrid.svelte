<script lang="ts">
	import Bolt from '$lib/components/icons/Bolt.svelte'
	import Bookmark from '$lib/components/icons/Bookmark.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import Cloud from '$lib/components/icons/Cloud.svelte'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import Database from '$lib/components/icons/Database.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Heart from '$lib/components/icons/Heart.svelte'
	import Map from '$lib/components/icons/Map.svelte'
	import Photo from '$lib/components/icons/Photo.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Star from '$lib/components/icons/Star.svelte'
	import Terminal from '$lib/components/icons/Terminal.svelte'
	import Users from '$lib/components/icons/Users.svelte'
	import { onDestroy } from 'svelte'

	type IconComponent = typeof Document

	interface AppDefinition {
		id: string
		title: string
		icon: IconComponent
	}

	type IconShape = 'default' | 'circle'

	interface Props {
		iconShape?: IconShape
	}

	let { iconShape = 'circle' }: Props = $props()

	const apps: AppDefinition[] = [
		{ id: 'notes', title: 'notes', icon: Document },
		{ id: 'reminders', title: 'reminders', icon: CheckBox },
		{ id: 'calendar', title: 'calendar', icon: Calendar },
		{ id: 'messages', title: 'messages', icon: ChatBubbles },
		{ id: 'bookmarks', title: 'bookmarks', icon: Bookmark },
		{ id: 'automations', title: 'automations', icon: Bolt },
		{ id: 'cloud', title: 'cloud', icon: Cloud },
		{ id: 'settings', title: 'settings', icon: Cog6 },
		{ id: 'database', title: 'database', icon: Database },
		{ id: 'world', title: 'world', icon: GlobeAlt },
		{ id: 'photos', title: 'photos', icon: Photo },
		{ id: 'maps', title: 'maps', icon: Map },
		{ id: 'spark', title: 'spark', icon: Sparkles },
		{ id: 'favorites', title: 'favorites', icon: Star },
		{ id: 'health', title: 'health', icon: Heart },
		{ id: 'terminal', title: 'terminal', icon: Terminal },
		{ id: 'teams', title: 'teams', icon: Users },
	]

	let tilePx = $state(76)
	let labelPx = $state(18)
	let tileToLabelGapPx = $state(8)
	let gridGapXPx = $state(30)
	let gridGapYPx = $state(35)
	let iconPx = $state(32)
	const INDICATOR_SPACE_PX = 28
	const BOTTOM_PADDING_PX = 12

	let rootEl: HTMLDivElement
	let scrollerEl: HTMLDivElement
	let trackEl: HTMLDivElement
	let cols = $state(5)
	let rows = $state(2)
	let currentPage = $state(0)
	let isDragging = $state(false)
	let suppressClick = $state(false)
	let dragPointerId: number | null = null
	let dragStartX = 0
	let dragStartScrollLeft = 0
	let elasticOffsetPx = $state(0)
	let rubberbandAnimation: Animation | null = null
	let hasPassedDragThreshold = $state(false)
	const DRAG_THRESHOLD_PX = 6
	const ELASTIC_CONSTANT = 0.55
	const ELASTIC_MAX_PX = 96

	function rubberband(distance: number) {
		const abs = Math.abs(distance)
		if (abs <= 0) return 0
		// iOS-like rubberband: asymptotically approaches ELASTIC_MAX_PX.
		const band =
			(abs * ELASTIC_CONSTANT * ELASTIC_MAX_PX) / (ELASTIC_MAX_PX + ELASTIC_CONSTANT * abs)
		return Math.sign(distance) * band
	}

	function clamp(value: number, min: number, max: number) {
		return Math.max(min, Math.min(max, value))
	}

	let recalcRaf: number | null = null
	function scheduleRecalc() {
		if (typeof window === 'undefined') return
		if (recalcRaf !== null) cancelAnimationFrame(recalcRaf)
		recalcRaf = requestAnimationFrame(() => {
			recalcRaf = null
			recalcLayout()
			// One extra frame helps when the viewport is mid-transition (mobile URL bar / orientation).
			requestAnimationFrame(recalcLayout)
		})
	}

	function recalcLayout() {
		if (!rootEl) return

		const rect = rootEl.getBoundingClientRect()
		const width = rect.width

		// Scale tile sizing down on small viewports.
		const scale = clamp(width / 560, 0.78, 1)
		tilePx = Math.round(76 * scale)
		gridGapXPx = Math.round(30 * scale)
		gridGapYPx = Math.round(35 * scale)
		tileToLabelGapPx = Math.max(6, Math.round(8 * scale))
		labelPx = Math.max(16, Math.round(18 * scale))
		iconPx = clamp(Math.round(tilePx * 0.42), 22, 32)
		const viewportHeight = window.visualViewport?.height ?? window.innerHeight
		const availableHeight = Math.max(0, viewportHeight - rect.top - BOTTOM_PADDING_PX)

		const tileBlockWidth = tilePx + gridGapXPx
		const nextCols = clamp(Math.floor((width + gridGapXPx) / tileBlockWidth), 3, 7)

		const cellHeight = tilePx + tileToLabelGapPx + labelPx
		const tileBlockHeight = cellHeight + gridGapYPx
		const heightForGrid = Math.max(0, availableHeight - INDICATOR_SPACE_PX)
		const nextRows = clamp(Math.floor((heightForGrid + gridGapYPx) / tileBlockHeight), 1, 5)

		cols = nextCols
		rows = nextRows

		const appsPerPage = Math.max(1, cols * rows)
		const pageCount = Math.max(1, Math.ceil(apps.length / appsPerPage))
		currentPage = clamp(currentPage, 0, pageCount - 1)
		scrollToPage(currentPage, 'auto')
	}

	function scrollToPage(pageIndex: number, behavior: 'smooth' | 'auto' = 'smooth') {
		if (!scrollerEl) return
		const width = scrollerEl.clientWidth
		if (width <= 0) return
		scrollerEl.scrollTo({ left: pageIndex * width, behavior })
	}

	function syncPageFromScroll() {
		if (isDragging) return
		if (!scrollerEl) return
		const width = scrollerEl.clientWidth
		if (width <= 0) return
		const next = clamp(Math.round(scrollerEl.scrollLeft / width), 0, pages.length - 1)
		if (next !== currentPage) currentPage = next
	}

	function applyDragScroll(desiredScrollLeft: number) {
		if (!scrollerEl) return
		rubberbandAnimation?.cancel()
		rubberbandAnimation = null
		const maxScroll = Math.max(0, scrollerEl.scrollWidth - scrollerEl.clientWidth)

		if (desiredScrollLeft < 0) {
			scrollerEl.scrollLeft = 0
			const overshoot = -desiredScrollLeft
			elasticOffsetPx = clamp(rubberband(overshoot), 0, ELASTIC_MAX_PX)
			return
		}

		if (desiredScrollLeft > maxScroll) {
			scrollerEl.scrollLeft = maxScroll
			const overshoot = desiredScrollLeft - maxScroll
			elasticOffsetPx = -clamp(rubberband(overshoot), 0, ELASTIC_MAX_PX)
			return
		}

		elasticOffsetPx = 0
		scrollerEl.scrollLeft = desiredScrollLeft
	}

	function handleClickCapture(event: MouseEvent) {
		if (!suppressClick) return
		event.preventDefault()
		event.stopPropagation()
		suppressClick = false
	}

	function handlePointerDown(event: PointerEvent) {
		if (!scrollerEl) return
		if (event.pointerType === 'mouse' && event.button !== 0) return
		rubberbandAnimation?.cancel()
		rubberbandAnimation = null
		isDragging = false
		hasPassedDragThreshold = false
		suppressClick = false
		dragPointerId = event.pointerId
		dragStartX = event.clientX
		dragStartScrollLeft = scrollerEl.scrollLeft
	}

	function animateElasticReturn() {
		if (!trackEl) {
			elasticOffsetPx = 0
			return
		}
		const start = elasticOffsetPx
		if (start === 0) return
		rubberbandAnimation?.cancel()
		rubberbandAnimation = trackEl.animate(
			[{ transform: `translateX(${start}px)` }, { transform: 'translateX(0px)' }],
			{
				duration: 280,
				easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
				fill: 'forwards',
			}
		)
		rubberbandAnimation.onfinish = () => {
			rubberbandAnimation = null
			elasticOffsetPx = 0
		}
		rubberbandAnimation.oncancel = () => {
			rubberbandAnimation = null
		}
	}

	function handlePointerMove(event: PointerEvent) {
		if (!scrollerEl) return
		if (dragPointerId !== event.pointerId) return
		const dx = event.clientX - dragStartX
		if (!hasPassedDragThreshold) {
			if (Math.abs(dx) < DRAG_THRESHOLD_PX) return
			hasPassedDragThreshold = true
			isDragging = true
			suppressClick = true
			scrollerEl.setPointerCapture(event.pointerId)
		}

		// From here on, we are dragging. Prevent text selection and keep it feeling native.
		event.preventDefault()
		applyDragScroll(dragStartScrollLeft - dx)
	}

	function handlePointerUp(event: PointerEvent) {
		if (dragPointerId !== event.pointerId) return
		const didDrag = hasPassedDragThreshold
		isDragging = false
		hasPassedDragThreshold = false
		dragPointerId = null
		if (!scrollerEl) return
		const width = scrollerEl.clientWidth
		if (width <= 0) return
		animateElasticReturn()
		if (didDrag) {
			currentPage = clamp(Math.round(scrollerEl.scrollLeft / width), 0, pages.length - 1)
			scrollToPage(currentPage)
			// If the browser doesn't emit a click after a drag (e.g. release outside), don't
			// leave click suppression enabled.
			setTimeout(() => {
				suppressClick = false
			}, 0)
		}
	}

	function handlePointerCancel(event: PointerEvent) {
		if (dragPointerId !== event.pointerId) return
		isDragging = false
		hasPassedDragThreshold = false
		animateElasticReturn()
		dragPointerId = null
	}

	const resizeObserver =
		typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => scheduleRecalc())

	$effect(() => {
		if (!rootEl) return
		resizeObserver?.observe(rootEl)
		window.addEventListener('resize', scheduleRecalc, { passive: true })
		window.addEventListener('orientationchange', scheduleRecalc, { passive: true })
		window.visualViewport?.addEventListener('resize', scheduleRecalc, { passive: true })
		window.visualViewport?.addEventListener('scroll', scheduleRecalc, { passive: true })

		// Ensure we measure after layout (especially because this grid is positioned under the input)
		scheduleRecalc()

		return () => {
			if (recalcRaf !== null) cancelAnimationFrame(recalcRaf)
			window.removeEventListener('resize', scheduleRecalc)
			window.removeEventListener('orientationchange', scheduleRecalc)
			window.visualViewport?.removeEventListener('resize', scheduleRecalc)
			window.visualViewport?.removeEventListener('scroll', scheduleRecalc)
			resizeObserver?.unobserve(rootEl)
		}
	})

	onDestroy(() => {
		resizeObserver?.disconnect()
	})

	const pages = $derived.by(() => {
		const appsPerPage = Math.max(1, cols * rows)
		const pageCount = Math.max(1, Math.ceil(apps.length / appsPerPage))

		return Array.from({ length: pageCount }, (_unused, pageIndex) =>
			apps.slice(pageIndex * appsPerPage, (pageIndex + 1) * appsPerPage)
		)
	})
</script>

<div bind:this={rootEl} class="w-full">
	<div
		bind:this={scrollerEl}
		class="no-scrollbar relative flex w-full overflow-x-scroll overscroll-x-contain select-none {isDragging
			? 'cursor-grabbing snap-none'
			: 'cursor-grab snap-x snap-mandatory'}"
		style="touch-action: pan-x;"
		onclickcapture={handleClickCapture}
		onscroll={syncPageFromScroll}
		onpointerdowncapture={handlePointerDown}
		onpointermovecapture={handlePointerMove}
		onpointerup={handlePointerUp}
		onpointercancel={handlePointerCancel}
	>
		<div
			bind:this={trackEl}
			class="flex w-full"
			style="transform: translateX({elasticOffsetPx}px);"
		>
			{#each pages as pageApps, pageIndex (pageIndex)}
				<div class="w-full shrink-0 snap-start">
					<div
						class="grid w-full justify-center"
						style="grid-template-columns: repeat({cols}, {tilePx}px); column-gap: {gridGapXPx}px; row-gap: {gridGapYPx}px;"
					>
						{#each pageApps as app (app.id)}
							{@const Icon = app.icon}
							<button
								type="button"
								class="group flex flex-col items-center border-none bg-transparent"
								style="height: {tilePx + tileToLabelGapPx + labelPx}px;"
								aria-label={app.title}
							>
								<div
									class="liquid-glass flex items-center justify-center shadow-[0_24px_48px_rgba(12,10,30,0.35)] ring-1 ring-transparent transition-[transform,box-shadow] duration-150 group-hover:scale-[1.03] group-hover:ring-white/10 group-active:scale-[0.99] group-active:ring-white/20 {iconShape ===
									'circle'
										? 'rounded-full'
										: 'rounded-3xl'}"
									style="width: {tilePx}px; height: {tilePx}px; background-color: var(--accent-bg); --icon-px: {iconPx}px;"
								>
									<span class="liquid-glass__highlight" aria-hidden="true"></span>
									<div class="liquid-glass__content">
										<Icon
											className="h-(--icon-px) w-(--icon-px) text-white/90"
										/>
									</div>
								</div>
								<div
									class="text-center text-xs font-medium text-white/70"
									style="margin-top: {tileToLabelGapPx}px; line-height: {labelPx}px; height: {labelPx}px;"
								>
									{app.title}
								</div>
							</button>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	</div>

	<div class="mt-6 flex items-center justify-center gap-2" aria-label="apps pages">
		{#each pages as _page, index (index)}
			<button
				type="button"
				class="transition-all duration-200 {index === currentPage
					? 'h-2 w-6 rounded-full bg-white/80'
					: 'h-2 w-2 rounded-full bg-white/30 hover:bg-white/45'}"
				aria-label={`page ${index + 1} (${_page.length})`}
				aria-current={index === currentPage ? 'page' : undefined}
				onclick={() => {
					currentPage = index
					scrollToPage(index)
				}}
			></button>
		{/each}
	</div>
</div>
