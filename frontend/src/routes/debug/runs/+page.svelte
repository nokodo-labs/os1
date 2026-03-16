<script lang="ts">
	import { resolve } from '$app/paths'
	import { api } from '$lib/api/client'
	import { onDestroy, onMount } from 'svelte'

	interface ActiveRun {
		run_id: string
		thread_id: string
		agent_id: string
		user_id: string
		state: string
		started_at: string
		updated_at: string
	}

	interface CacheInfo {
		name: string
		count: number
	}

	let runs = $state<ActiveRun[]>([])
	let loading = $state(false)
	let error = $state<string | null>(null)
	let lastFetched = $state<Date | null>(null)
	let autoRefresh = $state(true)
	let refreshInterval = $state(5000)

	// sw / cache diagnostics
	let caches_ = $state<CacheInfo[]>([])
	let swStatus = $state('unknown')
	let swScriptUrl = $state<string | null>(null)

	let timer: ReturnType<typeof setInterval> | null = null

	async function fetchRuns() {
		loading = true
		error = null
		try {
			// path available after api types regen
			const { data, response } = await api.GET('/v1/runs', {})
			if (!response.ok) {
				error = `HTTP ${response.status}: ${response.statusText}`
				return
			}
			runs = (data ?? []) as ActiveRun[]
			lastFetched = new Date()
		} catch (err) {
			error = err instanceof Error ? err.message : String(err)
		} finally {
			loading = false
		}
	}

	async function probeSwAndCaches() {
		if ('serviceWorker' in navigator) {
			const reg = await navigator.serviceWorker.getRegistration()
			if (reg) {
				const sw = reg.active ?? reg.waiting ?? reg.installing
				swStatus = sw?.state ?? 'no worker'
				swScriptUrl = sw?.scriptURL ?? null
			} else {
				swStatus = 'not registered'
			}
		} else {
			swStatus = 'not supported'
		}

		if ('caches' in window) {
			const names = await window.caches.keys()
			const infos: CacheInfo[] = []
			for (const name of names) {
				const cache = await window.caches.open(name)
				const keys = await cache.keys()
				infos.push({ name, count: keys.length })
			}
			caches_ = infos
		}
	}

	async function nukeAllCaches() {
		if (!('caches' in window)) return
		const names = await window.caches.keys()
		await Promise.all(names.map((n) => window.caches.delete(n)))
		await probeSwAndCaches()
	}

	async function forceSwUpdate() {
		if (!('serviceWorker' in navigator)) return
		const reg = await navigator.serviceWorker.getRegistration()
		if (reg) {
			await reg.update()
			if (reg.waiting) {
				reg.waiting.postMessage({ type: 'SKIP_WAITING' })
			}
		}
		await probeSwAndCaches()
	}

	async function unregisterSw() {
		if (!('serviceWorker' in navigator)) return
		const reg = await navigator.serviceWorker.getRegistration()
		if (reg) {
			await reg.unregister()
		}
		swStatus = 'unregistered'
		swScriptUrl = null
	}

	function startAutoRefresh() {
		stopAutoRefresh()
		if (autoRefresh) {
			timer = setInterval(fetchRuns, refreshInterval)
		}
	}

	function stopAutoRefresh() {
		if (timer) {
			clearInterval(timer)
			timer = null
		}
	}

	function relativeTime(iso: string): string {
		const diff = Date.now() - new Date(iso).getTime()
		const secs = Math.floor(diff / 1000)
		if (secs < 60) return `${secs}s ago`
		const mins = Math.floor(secs / 60)
		if (mins < 60) return `${mins}m ago`
		return `${Math.floor(mins / 60)}h ${mins % 60}m ago`
	}

	$effect(() => {
		if (autoRefresh) {
			startAutoRefresh()
		} else {
			stopAutoRefresh()
		}
	})

	onMount(async () => {
		await Promise.all([fetchRuns(), probeSwAndCaches()])
	})

	onDestroy(() => {
		stopAutoRefresh()
	})
</script>

<div class="mx-auto w-full max-w-5xl px-6 pt-10 pb-24">
	<div class="mb-6 flex items-center gap-3">
		<a href={resolve('/debug')} class="text-sm text-foreground/50 transition hover:text-foreground/75">
			← debug
		</a>
	</div>

	<h1 class="text-xl font-semibold">runs</h1>
	<p class="text-muted-foreground mt-2 text-sm">
		monitor in-memory agent runs and service worker cache state.
	</p>

	<!-- controls -->
	<div class="mt-6 flex flex-wrap items-center gap-3">
		<button
			type="button"
			class="rounded-lg border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-xs font-medium text-foreground/75 transition hover:bg-foreground/10"
			onclick={fetchRuns}
			disabled={loading}
		>
			{loading ? 'loading…' : 'refresh'}
		</button>
		<label class="flex items-center gap-2 text-xs text-foreground/60">
			<input type="checkbox" bind:checked={autoRefresh} class="accent-green-400" />
			auto-refresh ({refreshInterval / 1000}s)
		</label>
		{#if lastFetched}
			<span class="text-xs text-foreground/40">
				last: {lastFetched.toLocaleTimeString()}
			</span>
		{/if}
		{#if error}
			<span class="text-xs text-red-400">{error}</span>
		{/if}
	</div>

	<!-- runs list -->
	<div class="mt-6 space-y-3">
		{#if runs.length === 0 && !loading}
			<div class="rounded-xl border border-foreground/10 bg-foreground/5 p-5 text-sm text-foreground/40">
				no runs
			</div>
		{/if}

		{#each runs as run (run.run_id)}
			<div class="rounded-xl border border-foreground/10 bg-foreground/5 p-5">
				<div class="flex items-start justify-between gap-4">
					<div class="min-w-0 flex-1">
						<div class="flex items-center gap-2">
							<span class="text-sm font-semibold text-green-400">
								{run.state}
							</span>
							<span
								class="inline-block h-2 w-2 animate-pulse rounded-full bg-green-400"
							></span>
						</div>
						<div class="mt-1 space-y-0.5 text-xs text-foreground/50">
							<div>
								<span class="text-foreground/30">run:</span>
								<code class="text-foreground/60">{run.run_id}</code>
							</div>
							<div>
								<span class="text-foreground/30">thread:</span>
								<a
									href={resolve(`/c/${run.thread_id}`)}
									class="text-blue-400/80 hover:text-blue-400"
								>
									{run.thread_id}
								</a>
							</div>
							<div>
								<span class="text-foreground/30">agent:</span>
								<code class="text-foreground/60">{run.agent_id}</code>
							</div>
						</div>
					</div>

					<div class="flex shrink-0 flex-col items-end gap-1 text-xs text-foreground/40">
						<div>started {relativeTime(run.started_at)}</div>
						<div>updated {relativeTime(run.updated_at)}</div>
					</div>
				</div>

				<div class="mt-3">
					<a
						href={resolve(`/c/${run.thread_id}`)}
						class="rounded-lg border border-foreground/10 bg-foreground/5 px-2.5 py-1 text-xs text-foreground/60 transition hover:bg-foreground/10"
					>
						open thread
					</a>
				</div>
			</div>
		{/each}
	</div>

	<!-- service worker / cache diagnostics -->
	<div class="mt-10">
		<h2 class="text-lg font-semibold">service worker & caches</h2>
		<p class="text-muted-foreground mt-1 text-sm">
			inspect the active service worker and Cache Storage entries on this device.
		</p>

		<div class="mt-4 rounded-xl border border-foreground/10 bg-foreground/5 p-5">
			<div class="text-sm font-semibold text-foreground/85">service worker</div>
			<div class="mt-2 space-y-1 text-xs text-foreground/50">
				<div>
					<span class="text-foreground/30">status:</span>
					<span class="text-foreground/60">{swStatus}</span>
				</div>
				{#if swScriptUrl}
					<div>
						<span class="text-foreground/30">script:</span>
						<code class="break-all text-foreground/60">{swScriptUrl}</code>
					</div>
				{/if}
			</div>
			<div class="mt-3 flex flex-wrap items-center gap-2">
				<button
					type="button"
					class="rounded-lg border border-foreground/10 bg-foreground/5 px-2.5 py-1 text-xs text-foreground/60 transition hover:bg-foreground/10"
					onclick={forceSwUpdate}
				>
					force update + activate
				</button>
				<button
					type="button"
					class="rounded-lg border border-red-500/20 bg-red-500/5 px-2.5 py-1 text-xs text-red-400/80 transition hover:bg-red-500/10"
					onclick={unregisterSw}
				>
					unregister SW
				</button>
				<button
					type="button"
					class="rounded-lg border border-foreground/10 bg-foreground/5 px-2.5 py-1 text-xs text-foreground/60 transition hover:bg-foreground/10"
					onclick={probeSwAndCaches}
				>
					refresh info
				</button>
			</div>
		</div>

		<div class="mt-4 rounded-xl border border-foreground/10 bg-foreground/5 p-5">
			<div class="flex items-center justify-between">
				<div class="text-sm font-semibold text-foreground/85">cache storage</div>
				<button
					type="button"
					class="rounded-lg border border-red-500/20 bg-red-500/5 px-2.5 py-1 text-xs text-red-400/80 transition hover:bg-red-500/10"
					onclick={nukeAllCaches}
				>
					purge all caches
				</button>
			</div>
			{#if caches_.length === 0}
				<div class="mt-3 text-xs text-foreground/40">no caches found</div>
			{:else}
				<div class="mt-3 space-y-1.5">
					{#each caches_ as cache (cache.name)}
						<div
							class="flex items-center justify-between rounded-lg border border-foreground/5 bg-foreground/2 px-3 py-2 text-xs"
						>
							<code class="text-foreground/60">{cache.name}</code>
							<span class="text-foreground/40">{cache.count} entries</span>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>
