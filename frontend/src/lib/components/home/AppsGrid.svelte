<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import BoltSolid from '$lib/components/icons/BoltSolid.svelte'
	import BookmarkSolid from '$lib/components/icons/BookmarkSolid.svelte'
	import CalendarSolid from '$lib/components/icons/CalendarSolid.svelte'
	import ChatBubblesSolid from '$lib/components/icons/ChatBubblesSolid.svelte'
	import CheckBoxSolid from '$lib/components/icons/CheckBoxSolid.svelte'
	import CloudSolid from '$lib/components/icons/CloudSolid.svelte'
	import Cog6Solid from '$lib/components/icons/Cog6Solid.svelte'
	import CommandLineSolid from '$lib/components/icons/CommandLineSolid.svelte'
	import DatabaseSolid from '$lib/components/icons/DatabaseSolid.svelte'
	import DocumentSolid from '$lib/components/icons/DocumentSolid.svelte'
	import GlobeAltSolid from '$lib/components/icons/GlobeAltSolid.svelte'
	import HeartSolid from '$lib/components/icons/HeartSolid.svelte'
	import MapSolid from '$lib/components/icons/MapSolid.svelte'
	import PhotoSolid from '$lib/components/icons/PhotoSolid.svelte'
	import SparklesSolid from '$lib/components/icons/SparklesSolid.svelte'
	import StarSolid from '$lib/components/icons/StarSolid.svelte'
	import UsersSolid from '$lib/components/icons/UsersSolid.svelte'
	import { reminders } from '$lib/stores/reminders.svelte'
	import { onDestroy, tick } from 'svelte'

	type IconComponent = typeof DocumentSolid

	interface AppDefinition {
		id: string
		title: string
		icon: IconComponent
		action?: () => Promise<void>
	}

	type IconShape = 'default' | 'circle'

	interface Props {
		iconShape?: IconShape
	}

	let { iconShape = 'circle' }: Props = $props()

	const apps: AppDefinition[] = [
		{ id: 'notes', title: 'notes', icon: DocumentSolid },
		{
			id: 'reminders',
			title: 'reminders',
			icon: CheckBoxSolid,
			action: async () => {
				await goto(resolve(reminders.remindersAppUrl))
			},
		},
		{ id: 'calendar', title: 'calendar', icon: CalendarSolid },
		{ id: 'messages', title: 'messages', icon: ChatBubblesSolid },
		{ id: 'bookmarks', title: 'bookmarks', icon: BookmarkSolid },
		{ id: 'automations', title: 'automations', icon: BoltSolid },
		{ id: 'cloud', title: 'cloud', icon: CloudSolid },
		{
			id: 'settings',
			title: 'settings',
			icon: Cog6Solid,
			action: async () => {
				await goto(resolve('/settings'))
			},
		},
		{ id: 'database', title: 'database', icon: DatabaseSolid },
		{ id: 'world', title: 'world', icon: GlobeAltSolid },
		{ id: 'photos', title: 'photos', icon: PhotoSolid },
		{ id: 'maps', title: 'maps', icon: MapSolid },
		{ id: 'spark', title: 'spark', icon: SparklesSolid },
		{ id: 'favorites', title: 'favorites', icon: StarSolid },
		{ id: 'health', title: 'health', icon: HeartSolid },
		{ id: 'terminal', title: 'terminal', icon: CommandLineSolid },
		{ id: 'teams', title: 'teams', icon: UsersSolid },
	]

	let tilePx = $state(76)
	let labelPx = $state(18)
	let tileToLabelGapPx = $state(8)
	let gridGapXPx = $state(30)
	let gridGapYPx = $state(35)
	let iconPx = $state(32)
	const INDICATOR_SPACE_PX = 48
	const SIDE_PADDING_PX = 24

	let rootEl: HTMLDivElement
	let scrollerEl: HTMLDivElement
	let cols = $state(5)
	let rows = $state(2)
	let currentPage = $state(0)
	let wheelAccum = 0
	let wheelResetTimeout: number | null = null

	function clamp(value: number, min: number, max: number) {
		return Math.max(min, Math.min(max, value))
	}

	let recalcRaf: number | null = null
	let fitToken = 0

	async function ensureFitsViewport(token: number) {
		if (!browser) return
		if (!rootEl) return

		await tick()
		if (token !== fitToken) return

		// Use the component's actual height from its parent flex container
		const rootHeight = rootEl.clientHeight

		let attempts = 0
		while (attempts < 6) {
			// Calculate current content height
			const cellHeight = tilePx + tileToLabelGapPx + labelPx
			const gridHeight = rows * (cellHeight + gridGapYPx) - gridGapYPx
			const totalHeight = gridHeight + INDICATOR_SPACE_PX

			if (totalHeight <= rootHeight) break
			if (rows <= 1) break

			rows -= 1
			attempts += 1
			await tick()
			if (token !== fitToken) return
		}

		const appsPerPage = Math.max(1, cols * rows)
		const pageCount = Math.max(1, Math.ceil(apps.length / appsPerPage))
		currentPage = clamp(currentPage, 0, pageCount - 1)
		scrollToPage(currentPage, 'auto')
	}

	function scheduleRecalc() {
		if (!browser) return
		if (recalcRaf !== null) cancelAnimationFrame(recalcRaf)
		recalcRaf = requestAnimationFrame(() => {
			recalcRaf = null
			recalcLayout()
		})
	}

	function recalcLayout() {
		if (!rootEl) return

		const rect = rootEl.getBoundingClientRect()
		// Account for side padding when calculating columns
		const availableWidth = rect.width - SIDE_PADDING_PX * 2

		// Scale tile sizing down on small viewports.
		const scale = clamp(rect.width / 560, 0.78, 1)
		tilePx = Math.round(76 * scale)
		gridGapXPx = Math.round(30 * scale)
		gridGapYPx = Math.round(35 * scale)
		tileToLabelGapPx = Math.max(6, Math.round(8 * scale))
		labelPx = Math.max(16, Math.round(18 * scale))
		iconPx = clamp(Math.round(tilePx * 0.42), 22, 32)

		// Use the component's actual height from its parent flex container
		const availableHeight = rootEl.clientHeight

		const tileBlockWidth = tilePx + gridGapXPx
		const nextCols = clamp(Math.floor((availableWidth + gridGapXPx) / tileBlockWidth), 3, 7)

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

		const token = ++fitToken
		void ensureFitsViewport(token)
	}

	function scrollToPage(pageIndex: number, behavior: 'smooth' | 'auto' = 'smooth') {
		if (!scrollerEl) return
		const width = scrollerEl.clientWidth
		if (width <= 0) return
		scrollerEl.scrollTo({ left: pageIndex * width, behavior })
	}

	function pageBy(delta: number) {
		const next = clamp(currentPage + delta, 0, pages.length - 1)
		if (next === currentPage) return
		currentPage = next
		scrollToPage(next)
	}

	function onScrollerWheel(event: WheelEvent) {
		// Keep native behavior for trackpads and horizontal wheel/shift-scroll.
		if (event.ctrlKey) return
		if (!scrollerEl) return
		if (pages.length <= 1) return

		const dx = event.deltaX
		const dy = event.deltaY
		const absDx = Math.abs(dx)
		const absDy = Math.abs(dy)
		if (event.shiftKey || absDx > absDy) return

		// Treat vertical wheel as a paging intent on desktop mice.
		wheelAccum += dy

		if (wheelResetTimeout !== null) window.clearTimeout(wheelResetTimeout)
		wheelResetTimeout = window.setTimeout(() => {
			wheelAccum = 0
			wheelResetTimeout = null
		}, 160)

		const threshold = 70
		if (wheelAccum >= threshold) {
			wheelAccum = 0
			pageBy(1)
		} else if (wheelAccum <= -threshold) {
			wheelAccum = 0
			pageBy(-1)
		}
	}

	function passiveWheel(node: HTMLElement, handler: (event: WheelEvent) => void) {
		let currentHandler = handler
		const listener = (event: WheelEvent) => currentHandler(event)
		node.addEventListener('wheel', listener, { passive: true })
		return {
			update(nextHandler: (event: WheelEvent) => void) {
				currentHandler = nextHandler
			},
			destroy() {
				node.removeEventListener('wheel', listener)
			},
		}
	}

	function syncPageFromScroll() {
		if (!scrollerEl) return
		const width = scrollerEl.clientWidth
		if (width <= 0) return
		const next = clamp(Math.round(scrollerEl.scrollLeft / width), 0, pages.length - 1)
		if (next !== currentPage) currentPage = next
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
		window.addEventListener('scroll', scheduleRecalc, { passive: true })

		// Ensure we measure after layout.
		scheduleRecalc()

		return () => {
			if (recalcRaf !== null) cancelAnimationFrame(recalcRaf)
			if (wheelResetTimeout !== null) window.clearTimeout(wheelResetTimeout)
			window.removeEventListener('resize', scheduleRecalc)
			window.removeEventListener('orientationchange', scheduleRecalc)
			window.visualViewport?.removeEventListener('resize', scheduleRecalc)
			window.visualViewport?.removeEventListener('scroll', scheduleRecalc)
			window.removeEventListener('scroll', scheduleRecalc)
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

<div bind:this={rootEl} class="flex h-full w-full flex-col">
	<!-- scroller takes all available space -->
	<div
		bind:this={scrollerEl}
		class="no-scrollbar relative flex min-h-0 w-full flex-1 snap-x snap-mandatory overflow-x-auto overscroll-x-contain select-none"
		style="touch-action: pan-x; -webkit-overflow-scrolling: touch;"
		onscroll={syncPageFromScroll}
		use:passiveWheel={onScrollerWheel}
	>
		{#each pages as pageApps, pageIndex (pageIndex)}
			<div class="w-full shrink-0 snap-center">
				<div
					class="grid w-full justify-center"
					style="grid-template-columns: repeat({cols}, {tilePx}px); column-gap: {gridGapXPx}px; row-gap: {gridGapYPx}px; padding-left: {SIDE_PADDING_PX}px; padding-right: {SIDE_PADDING_PX}px;"
				>
					{#each pageApps as app (app.id)}
						{@const Icon = app.icon}
						<button
							type="button"
							class="group flex cursor-pointer flex-col items-center border-none bg-transparent"
							style="height: {tilePx + tileToLabelGapPx + labelPx}px;"
							aria-label={app.title}
							onclick={async () => {
								if (!app.action) return
								await app.action()
							}}
						>
							<div
								class="liquid-glass flex items-center justify-center shadow-[0_24px_48px_rgba(12,10,30,0.35)] ring-1 ring-transparent transition-[box-shadow,ring-color] duration-150 group-hover:ring-white/15 group-active:scale-[0.96] {iconShape ===
								'circle'
									? 'rounded-full'
									: 'rounded-container'}"
								style="width: {tilePx}px; height: {tilePx}px; background-color: var(--accent-bg); --icon-px: {iconPx}px;"
							>
								<div class="relative z-10">
									<Icon className="h-(--icon-px) w-(--icon-px) text-white/90" />
								</div>
							</div>
							<div
								class="text-center text-xs font-medium text-white/70 transition-colors duration-150 group-hover:text-white/85"
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

	<div
		class="mt-auto flex shrink-0 items-center justify-center gap-2 py-4"
		aria-label="apps pages"
	>
		{#each pages as _page, index (index)}
			<button
				type="button"
				class="cursor-pointer transition-all duration-200 {index === currentPage
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
