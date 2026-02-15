<script lang="ts">
	import { cubicOut } from 'svelte/easing'
	import { fly } from 'svelte/transition'

	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { ToastItem } from '$lib/stores/notifications.svelte'
	import { SvelteMap } from 'svelte/reactivity'

	interface Props {
		toasts: ToastItem[]
		onDismiss?: (id: string) => void
		onSwipeDismiss?: (id: string) => void
		onClick?: (id: string) => void
	}

	let { toasts, onDismiss, onSwipeDismiss, onClick }: Props = $props()

	// --- auto-dismiss (component-managed so exit animation plays) ---
	const AUTO_DISMISS_MS = 5000
	let dismissTimers = new SvelteMap<string, ReturnType<typeof setTimeout>>()

	$effect(() => {
		const currentIds = new Set(toasts.map((t) => t.id))

		// schedule auto-dismiss for new toasts
		for (const toast of toasts) {
			if (!dismissTimers.has(toast.id)) {
				dismissTimers.set(
					toast.id,
					setTimeout(() => {
						dismissTimers.delete(toast.id)
						startDismiss(toast.id)
					}, AUTO_DISMISS_MS)
				)
			}
		}

		// clean up timers for removed toasts
		for (const [id, timer] of dismissTimers) {
			if (!currentIds.has(id)) {
				clearTimeout(timer)
				dismissTimers.delete(id)
			}
		}
	})

	// --- dismiss animation ---
	let dismissing = $state<Record<string, 'up' | 'left' | 'right'>>({})

	function startDismiss(id: string) {
		if (dismissing[id]) return
		dismissing[id] = device.isMobile ? 'up' : 'right'
		setTimeout(() => onDismiss?.(id), 280)
	}

	function startSwipeDismiss(id: string, direction: 'up' | 'left' | 'right') {
		if (dismissing[id]) return
		dismissing[id] = direction
		if (direction === 'up') {
			setTimeout(() => onDismiss?.(id), 280)
		} else {
			setTimeout(() => onSwipeDismiss?.(id), 280)
		}
	}

	// --- swipe / drag ---
	const DRAG_THRESHOLD = 6
	const SWIPE_THRESHOLD = 50

	interface Drag {
		startX: number
		startY: number
		dx: number
		dy: number
		intent: 'none' | 'horizontal' | 'vertical'
	}

	let drags = $state<Record<string, Drag>>({})

	function onPointerDown(id: string, e: PointerEvent) {
		// pause auto-dismiss while grabbed
		const existing = dismissTimers.get(id)
		if (existing) {
			clearTimeout(existing)
			dismissTimers.delete(id)
		}

		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
		drags[id] = {
			startX: e.clientX,
			startY: e.clientY,
			dx: 0,
			dy: 0,
			intent: 'none',
		}
	}

	function onPointerMove(id: string, e: PointerEvent) {
		const d = drags[id]
		if (!d) return
		d.dx = e.clientX - d.startX
		d.dy = e.clientY - d.startY
		if (d.intent === 'none') {
			if (Math.abs(d.dx) > DRAG_THRESHOLD || Math.abs(d.dy) > DRAG_THRESHOLD) {
				d.intent = Math.abs(d.dx) > Math.abs(d.dy) ? 'horizontal' : 'vertical'
			}
		}
	}

	function resumeAutoDismiss(id: string) {
		if (dismissTimers.has(id) || dismissing[id]) return
		dismissTimers.set(
			id,
			setTimeout(() => {
				dismissTimers.delete(id)
				startDismiss(id)
			}, AUTO_DISMISS_MS)
		)
	}

	function onPointerUp(id: string) {
		const d = drags[id]
		if (!d) return

		const absX = Math.abs(d.dx)
		const absY = Math.abs(d.dy)

		if (absX < DRAG_THRESHOLD && absY < DRAG_THRESHOLD) {
			// tap - treat as click then dismiss
			delete drags[id]
			onClick?.(id)
			startDismiss(id)
			return
		}

		if (d.intent === 'vertical' && d.dy < -SWIPE_THRESHOLD) {
			// swipe up → dismiss toast only
			delete drags[id]
			startSwipeDismiss(id, 'up')
		} else if (d.intent === 'horizontal' && absX > SWIPE_THRESHOLD) {
			// swipe sideways → dismiss notification
			delete drags[id]
			startSwipeDismiss(id, d.dx > 0 ? 'right' : 'left')
		} else {
			// below threshold - snap back, resume auto-dismiss
			delete drags[id]
			resumeAutoDismiss(id)
		}
	}

	function onPointerCancel(id: string) {
		delete drags[id]
		resumeAutoDismiss(id)
	}

	function handleButtonDismiss(id: string) {
		startDismiss(id)
	}

	function toastStyle(id: string): string {
		const d = drags[id]
		const dir = dismissing[id]

		if (d && d.intent !== 'none') {
			const tx = d.intent === 'horizontal' ? d.dx : 0
			const ty = d.intent === 'vertical' ? Math.min(0, d.dy) : 0
			const progress = Math.max(Math.abs(d.dx), Math.abs(d.dy)) / (SWIPE_THRESHOLD * 2)
			const opacity = Math.max(0.4, 1 - progress)
			return `transform: translate(${tx}px, ${ty}px); opacity: ${opacity}; transition: none;`
		}

		if (dir) {
			const transforms: Record<string, string> = {
				up: 'translateY(-150%)',
				left: 'translateX(-150%)',
				right: 'translateX(150%)',
			}
			return `transform: ${transforms[dir]}; opacity: 0; transition: transform 280ms ease-out, opacity 280ms ease-out;`
		}

		return ''
	}
</script>

{#if toasts.length > 0}
	{#if device.isMobile}
		<!-- mobile: full-width banners at top -->
		<div class="fixed inset-x-0 top-0 z-60 flex flex-col gap-2 px-3 pt-3">
			{#each toasts as toast (toast.id)}
				<div
					role="button"
					tabindex="0"
					class="notification-toast flex w-full touch-none items-start gap-3 rounded-2xl border border-white/10 bg-black/70 px-4 py-3 text-left backdrop-blur-xl select-none"
					style={toastStyle(toast.id)}
					in:fly={{ y: -80, duration: 300, easing: cubicOut }}
					onpointerdown={(e) => onPointerDown(toast.id, e)}
					onpointermove={(e) => onPointerMove(toast.id, e)}
					onpointerup={() => onPointerUp(toast.id)}
					onpointercancel={() => onPointerCancel(toast.id)}
					onkeydown={(e) => {
						if (e.key === 'Enter') {
							onClick?.(toast.id)
							startDismiss(toast.id)
						}
					}}
				>
					<div
						class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10"
					>
						{#if toast.iconUrl}
							<img
								src={toast.iconUrl}
								alt=""
								class="h-5 w-5 rounded-full object-cover"
							/>
						{:else}
							<AppNotification class="h-4 w-4 text-white/80" />
						{/if}
					</div>
					<div class="min-w-0 flex-1">
						<div class="truncate text-sm font-semibold text-white/90">
							{toast.title}
						</div>
						{#if toast.body}
							<div class="truncate text-sm text-white/60">{toast.body}</div>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{:else}
		<!-- desktop: top-right stack like macOS -->
		<div class="fixed top-6 right-6 z-60 flex w-80 flex-col gap-2">
			{#each toasts as toast (toast.id)}
				<div
					role="button"
					tabindex="0"
					class="notification-toast flex w-full touch-none items-start gap-3 rounded-2xl border border-white/8 bg-black/60 px-4 py-3 text-left shadow-lg shadow-black/20 backdrop-blur-xl select-none"
					style={toastStyle(toast.id)}
					in:fly={{ x: 200, duration: 300, easing: cubicOut }}
					onpointerdown={(e) => onPointerDown(toast.id, e)}
					onpointermove={(e) => onPointerMove(toast.id, e)}
					onpointerup={() => onPointerUp(toast.id)}
					onpointercancel={() => onPointerCancel(toast.id)}
					onkeydown={(e) => {
						if (e.key === 'Enter') {
							onClick?.(toast.id)
							startDismiss(toast.id)
						}
					}}
				>
					<div
						class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10"
					>
						{#if toast.iconUrl}
							<img
								src={toast.iconUrl}
								alt=""
								class="h-5 w-5 rounded-full object-cover"
							/>
						{:else}
							<AppNotification class="h-4 w-4 text-white/80" />
						{/if}
					</div>
					<div class="min-w-0 flex-1">
						<div class="truncate text-sm font-semibold text-white/90">
							{toast.title}
						</div>
						{#if toast.body}
							<div class="truncate text-sm text-white/60">{toast.body}</div>
						{/if}
					</div>
					<button
						type="button"
						aria-label="dismiss"
						class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-white/40 transition-colors hover:text-white/70"
						onpointerdown={(e) => e.stopPropagation()}
						onclick={() => handleButtonDismiss(toast.id)}
					>
						<svg
							class="h-3.5 w-3.5"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2.5"
							stroke-linecap="round"
						>
							<path d="M18 6L6 18M6 6l12 12" />
						</svg>
					</button>
				</div>
			{/each}
		</div>
	{/if}
{/if}
