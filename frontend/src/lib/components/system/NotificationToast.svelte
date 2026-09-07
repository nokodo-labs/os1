<script lang="ts">
	import { cubicOut } from 'svelte/easing'
	import { fly } from 'svelte/transition'

	import { portal } from '$lib/attachments/portal'
	import { swipe, type SwipeDirection } from '$lib/attachments/swipe'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte'
	import ExclamationTriangle from '$lib/components/icons/ExclamationTriangle.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { notificationIcon } from '$lib/resources/notificationVisuals'
	import { device } from '$lib/stores/device.svelte'
	import type { EphemeralVariant, ToastItem } from '$lib/stores/notifications.svelte'
	import type { Attachment } from 'svelte/attachments'
	import { SvelteMap, SvelteSet } from 'svelte/reactivity'

	interface Props {
		toasts: ToastItem[]
		onDismiss?: (id: string) => void
		onSwipeDismiss?: (id: string) => void
		onClick?: (id: string) => void
	}

	let { toasts, onDismiss, onSwipeDismiss, onClick }: Props = $props()

	// auto-dismiss (component-managed so exit animation plays)
	const AUTO_DISMISS_MS = 12000
	const ERROR_DISMISS_MS = 5000
	let dismissTimers = new SvelteMap<string, ReturnType<typeof setTimeout>>()
	// toasts under a finger: they hold off auto-dismiss until the swipe ends
	const grabbed = new SvelteSet<string>()

	$effect(() => {
		const currentIds = new Set(toasts.map((t) => t.id))

		// schedule auto-dismiss for new toasts
		for (const toast of toasts) {
			if (!dismissTimers.has(toast.id) && !grabbed.has(toast.id)) {
				const ms = toast.type === 'ephemeral' ? ERROR_DISMISS_MS : AUTO_DISMISS_MS
				dismissTimers.set(
					toast.id,
					setTimeout(() => {
						dismissTimers.delete(toast.id)
						startDismiss(toast.id)
					}, ms)
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
		for (const id of grabbed) {
			if (!currentIds.has(id)) grabbed.delete(id)
		}
	})

	// dismiss animation
	let dismissing = $state<Record<string, SwipeDirection>>({})

	function startDismiss(id: string) {
		if (dismissing[id]) return
		dismissing[id] = device.isMobile ? 'up' : 'right'
		setTimeout(() => onDismiss?.(id), 280)
	}

	function startSwipeDismiss(id: string, direction: SwipeDirection) {
		if (dismissing[id]) return
		// the swipe already flew the toast off-screen, so hand it over right away
		dismissing[id] = direction
		if (direction === 'up' || direction === 'down') {
			onDismiss?.(id)
		} else {
			onSwipeDismiss?.(id)
		}
	}

	// swipe: up on mobile (banner at the top), sideways on the desktop stack
	const SWIPE_THRESHOLD = 50
	const swipeDirections = $derived<readonly SwipeDirection[]>(
		device.isMobile ? ['up'] : ['left', 'right']
	)

	function swipeDismiss(id: string): Attachment<HTMLElement> {
		return swipe({
			direction: swipeDirections,
			threshold: SWIPE_THRESHOLD,
			release: 'fly',
			onGrab: () => pauseAutoDismiss(id),
			onRelease: () => resumeAutoDismiss(id),
			onTrigger: (direction) => startSwipeDismiss(id, direction),
		})
	}

	function pauseAutoDismiss(id: string) {
		grabbed.add(id)
		const existing = dismissTimers.get(id)
		if (existing) {
			clearTimeout(existing)
			dismissTimers.delete(id)
		}
	}

	function resumeAutoDismiss(id: string) {
		grabbed.delete(id)
		if (dismissTimers.has(id) || dismissing[id]) return
		const toast = toasts.find((t) => t.id === id)
		const ms = toast?.type === 'ephemeral' ? ERROR_DISMISS_MS : AUTO_DISMISS_MS
		dismissTimers.set(
			id,
			setTimeout(() => {
				dismissTimers.delete(id)
				startDismiss(id)
			}, ms)
		)
	}

	function handleTap(id: string) {
		onClick?.(id)
		startDismiss(id)
	}

	function handleButtonDismiss(id: string) {
		startDismiss(id)
	}

	function toastStyle(id: string): string {
		const dir = dismissing[id]
		if (!dir) return ''

		const transforms: Record<SwipeDirection, string> = {
			up: 'translateY(-150%)',
			down: 'translateY(150%)',
			left: 'translateX(-150%)',
			right: 'translateX(150%)',
		}
		return `transform: ${transforms[dir]}; opacity: 0; transition: transform 280ms ease-out, opacity 280ms ease-out;`
	}
	type EphemeralMeta = { tint: string; iconColor: string }
	function ephemeralMeta(variant: EphemeralVariant | undefined): EphemeralMeta {
		switch (variant) {
			case 'success':
				return { tint: 'rgba(22,163,74,0.18)', iconColor: 'text-green-500' }
			case 'info':
				return { tint: 'rgba(37,99,235,0.18)', iconColor: 'text-blue-400' }
			case 'warning':
				return { tint: 'rgba(217,119,6,0.22)', iconColor: 'text-amber-400' }
			default:
				return { tint: 'rgba(220,38,38,0.18)', iconColor: 'text-red-500' }
		}
	}
</script>

{#if toasts.length > 0}
	{#if device.isMobile}
		<!-- mobile: full-width banners at top -->
		<div {@attach portal()} class="fixed inset-x-0 top-0 z-100 flex flex-col gap-2 px-3 pt-3">
			{#each toasts as toast (toast.id)}
				{#if toast.type === 'notification'}
					{@const ToastIcon = notificationIcon(toast.eventType)}
					<LiquidGlass
						{@attach swipeDismiss(toast.id)}
						class="notification-toast flex w-full items-start gap-3 rounded-2xl px-4 py-3 text-left"
						style={toastStyle(toast.id)}
						role="button"
						tabindex="0"
						onclick={() => handleTap(toast.id)}
						onkeydown={(e: KeyboardEvent) => {
							if (e.key === 'Enter') handleTap(toast.id)
						}}
					>
						<div
							class="bg-foreground/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
						>
							{#if toast.iconUrl}
								<img
									src={toast.iconUrl}
									alt=""
									class="h-5 w-5 rounded-full object-cover"
								/>
							{:else}
								<ToastIcon class="text-foreground/80 h-4 w-4" />
							{/if}
						</div>
						<div class="min-w-0 flex-1">
							<div class="text-foreground/90 truncate text-sm font-semibold">
								{toast.title}
							</div>
							{#if toast.body}
								<div class="text-foreground/60 line-clamp-2 text-sm">
									{toast.body}
								</div>
							{/if}
							{#if toast.imageUrl}
								<img
									src={toast.imageUrl}
									alt=""
									class="mt-2 max-h-32 w-full rounded-lg object-cover"
								/>
							{/if}
						</div>
						<XMark
							class="text-foreground/45 hover:text-foreground/80 mt-0.5 size-5 shrink-0 cursor-pointer transition-all duration-150 hover:scale-[1.05] active:scale-[0.97]"
							onpointerdown={(e) => e.stopPropagation()}
							onclick={(e) => {
								e.stopPropagation()
								handleButtonDismiss(toast.id)
							}}
						/>
					</LiquidGlass>
				{:else}
					{@const meta = ephemeralMeta(toast.variant)}
					<LiquidGlass
						{@attach swipeDismiss(toast.id)}
						class="notification-toast relative flex w-full items-start gap-3 overflow-hidden rounded-2xl px-4 py-3 text-left"
						style={toastStyle(toast.id)}
						role="alert"
						onclick={() => handleTap(toast.id)}
					>
						<!-- color tint overlay -->
						<div
							class="absolute inset-0 rounded-2xl"
							style="background:{meta.tint}"
						></div>
						<div
							class="bg-foreground/10 relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
						>
							{#if toast.variant === 'success'}
								<CheckCircle class="h-4 w-4 {meta.iconColor}" />
							{:else if toast.variant === 'warning'}
								<ExclamationTriangle class="h-4 w-4 {meta.iconColor}" />
							{:else if toast.variant === 'info'}
								<InfoCircle class="h-4 w-4 {meta.iconColor}" />
							{:else}
								<XMark class="h-4 w-4 {meta.iconColor}" />
							{/if}
						</div>
						<div class="relative min-w-0 flex-1">
							<div class="text-foreground/90 truncate text-sm font-semibold">
								{toast.title}
							</div>
						</div>
						<XMark
							class="text-foreground/45 hover:text-foreground/80 relative mt-0.5 size-5 shrink-0 cursor-pointer transition-all duration-150 hover:scale-[1.05] active:scale-[0.97]"
							onpointerdown={(e) => e.stopPropagation()}
							onclick={(e) => {
								e.stopPropagation()
								handleButtonDismiss(toast.id)
							}}
						/>
					</LiquidGlass>
				{/if}
			{/each}
		</div>
	{:else}
		<!-- desktop: top-right stack like macOS -->
		<div {@attach portal()} class="fixed top-6 right-6 z-100 flex w-80 flex-col gap-2">
			{#each toasts as toast (toast.id)}
				<div in:fly={{ x: 200, duration: 300, easing: cubicOut }}>
					{#if toast.type === 'notification'}
						{@const ToastIcon = notificationIcon(toast.eventType)}
						<LiquidGlass
							{@attach swipeDismiss(toast.id)}
							class="notification-toast flex w-full items-start gap-3 rounded-2xl px-4 py-3 text-left shadow-lg shadow-black/20"
							style={toastStyle(toast.id)}
							role="button"
							tabindex="0"
							onclick={() => handleTap(toast.id)}
							onkeydown={(e: KeyboardEvent) => {
								if (e.key === 'Enter') handleTap(toast.id)
							}}
						>
							<div
								class="bg-foreground/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
							>
								{#if toast.iconUrl}
									<img
										src={toast.iconUrl}
										alt=""
										class="h-5 w-5 rounded-full object-cover"
									/>
								{:else}
									<ToastIcon class="text-foreground/80 h-4 w-4" />
								{/if}
							</div>
							<div class="min-w-0 flex-1">
								<div class="text-foreground/90 truncate text-sm font-semibold">
									{toast.title}
								</div>
								{#if toast.body}
									<div class="text-foreground/60 line-clamp-2 text-sm">
										{toast.body}
									</div>
								{/if}
								{#if toast.imageUrl}
									<img
										src={toast.imageUrl}
										alt=""
										class="mt-2 max-h-32 w-full rounded-lg object-cover"
									/>
								{/if}
							</div>
							<XMark
								class="text-foreground/45 hover:text-foreground/80 mt-0.5 size-5 shrink-0 cursor-pointer transition-all duration-150 hover:scale-[1.05] active:scale-[0.97]"
								onpointerdown={(e) => e.stopPropagation()}
								onclick={(e) => {
									e.stopPropagation()
									handleButtonDismiss(toast.id)
								}}
							/>
						</LiquidGlass>
					{:else}
						{@const meta = ephemeralMeta(toast.variant)}
						<LiquidGlass
							{@attach swipeDismiss(toast.id)}
							class="notification-toast relative flex w-full items-start gap-3 overflow-hidden rounded-2xl px-4 py-3 text-left shadow-lg shadow-black/20"
							style={toastStyle(toast.id)}
							role="alert"
							onclick={() => handleTap(toast.id)}
						>
							<!-- color tint overlay -->
							<div
								class="absolute inset-0 rounded-2xl"
								style="background:{meta.tint}"
							></div>
							<div
								class="bg-foreground/10 relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
							>
								{#if toast.variant === 'success'}
									<CheckCircle class="h-4 w-4 {meta.iconColor}" />
								{:else if toast.variant === 'warning'}
									<ExclamationTriangle class="h-4 w-4 {meta.iconColor}" />
								{:else if toast.variant === 'info'}
									<InfoCircle class="h-4 w-4 {meta.iconColor}" />
								{:else}
									<XMark class="h-4 w-4 {meta.iconColor}" />
								{/if}
							</div>
							<div class="relative min-w-0 flex-1">
								<div class="text-foreground/90 truncate text-sm font-semibold">
									{toast.title}
								</div>
							</div>
							<XMark
								class="text-foreground/45 hover:text-foreground/80 relative mt-0.5 size-5 shrink-0 cursor-pointer transition-all duration-150 hover:scale-[1.05] active:scale-[0.97]"
								onpointerdown={(e) => e.stopPropagation()}
								onclick={(e) => {
									e.stopPropagation()
									handleButtonDismiss(toast.id)
								}}
							/>
						</LiquidGlass>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
{/if}
