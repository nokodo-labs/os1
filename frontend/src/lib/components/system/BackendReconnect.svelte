<script lang="ts">
	import { getApiOrigin } from '$lib/api/origin'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import WifiSlash from '$lib/components/icons/WifiSlash.svelte'
	import { onDestroy, onMount } from 'svelte'

	const POLL_INTERVAL_MS = 5000

	let isChecking = $state(false)

	async function tryConnect(): Promise<boolean> {
		try {
			const res = await fetch(`${getApiOrigin()}/health`, {
				method: 'GET',
				credentials: 'include',
				signal: AbortSignal.timeout(4000),
			})
			return res.ok
		} catch {
			return false
		}
	}

	async function check() {
		if (isChecking) return
		isChecking = true
		try {
			const ok = await tryConnect()
			if (ok) {
				// backend is back - reload to restart the full boot flow cleanly
				window.location.reload()
			}
		} finally {
			isChecking = false
		}
	}

	let intervalId: ReturnType<typeof setInterval> | null = null

	onMount(() => {
		// kick off first check immediately, then auto-poll
		void check()
		intervalId = setInterval(() => void check(), POLL_INTERVAL_MS)
	})

	onDestroy(() => {
		if (intervalId !== null) clearInterval(intervalId)
	})
</script>

<div class="h-app relative z-1 flex">
	<div
		class="relative flex min-w-0 flex-1 flex-col overflow-y-auto"
		style="touch-action: pan-y; overscroll-behavior-y: contain;"
	>
		<div class="flex-1 overflow-y-auto">
			<div class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-8 pt-8 pb-24">
				<div class="flex flex-1 items-center justify-center">
					<div class="w-full max-w-md">
						<div
							class="liquid-glass liquid-glass--frosted rounded-container overflow-hidden shadow-[0_28px_80px_rgba(0,0,0,0.45)]"
						>
							<div class="p-8">
								<div class="mb-8 space-y-2">
									<WifiSlash class="text-foreground/50 mb-4 h-8 w-8" />
									<h1 class="text-foreground text-2xl font-medium">
										can't reach the servers
									</h1>
									<p class="text-foreground/55 text-sm">
										your session is intact. we'll reconnect automatically.
									</p>
								</div>

								<button
									type="button"
									class="interactive bg-foreground text-background hover:bg-foreground/90 focus-visible:ring-foreground/20 inline-flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-full font-medium transition-all focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100"
									onclick={() => void check()}
									disabled={isChecking}
								>
									<ArrowPath class="h-4 w-4 {isChecking ? 'animate-spin' : ''}" />
									{#if isChecking}
										<ShimmerText
											className="inline-block"
											textColor="var(--background)"
											waveColor="color-mix(in oklch, var(--background) 35%, transparent)"
											>checking</ShimmerText
										>
									{:else}
										try now
									{/if}
								</button>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</div>
