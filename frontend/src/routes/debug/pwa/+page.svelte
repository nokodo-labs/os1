<script lang="ts">
	import { resolve } from '$app/paths'
	import WifiSlash from '$lib/components/icons/WifiSlash.svelte'
	import { installPrompt } from '$lib/stores/installPrompt.svelte'
	import { network } from '$lib/stores/network.svelte'
	import { swUpdate } from '$lib/stores/serviceWorker.svelte'

	let offlineOverride = $state(false)
	let updateOverride = $state(false)
	let installOverride = $state(false)

	// stash originals so we can restore on toggle-off
	let stashedOnline: boolean | null = $state(null)
	let stashedUpdate: boolean | null = $state(null)
	let stashedCanInstall: boolean | null = $state(null)

	function toggleOffline() {
		if (!offlineOverride) {
			stashedOnline = network.online
			network.online = false
			offlineOverride = true
		} else {
			network.online = stashedOnline ?? true
			stashedOnline = null
			offlineOverride = false
		}
	}

	function toggleUpdate() {
		if (!updateOverride) {
			stashedUpdate = swUpdate.updateAvailable
			swUpdate.updateAvailable = true
			updateOverride = true
		} else {
			swUpdate.updateAvailable = stashedUpdate ?? false
			stashedUpdate = null
			updateOverride = false
		}
	}

	function toggleInstall() {
		if (!installOverride) {
			stashedCanInstall = installPrompt.canInstall
			installPrompt.canInstall = true
			installPrompt.dismissed = false
			installOverride = true
		} else {
			installPrompt.canInstall = stashedCanInstall ?? false
			stashedCanInstall = null
			installOverride = false
		}
	}
</script>

<div class="mx-auto w-full max-w-4xl px-6 pt-10 pb-24">
	<div class="mb-6 flex items-center gap-3">
		<a
			href={resolve('/debug')}
			class="text-foreground/50 hover:text-foreground/75 text-sm transition"
		>
			← debug
		</a>
	</div>

	<h1 class="text-xl font-semibold">pwa debug</h1>
	<p class="text-muted-foreground mt-2 text-sm">
		test PWA ui components: offline banner, update toast, install prompt.
	</p>

	<div class="mt-8 space-y-4">
		<!-- offline banner trigger -->
		<div class="border-foreground/10 bg-foreground/5 rounded-xl border p-5">
			<div class="flex items-center justify-between">
				<div>
					<div class="text-foreground/85 flex items-center gap-2 text-sm font-semibold">
						<WifiSlash />
						offline banner
					</div>
					<div class="text-foreground/55 mt-1 text-sm">
						toggles <code class="text-xs">network.online</code> to show/hide the banner.
					</div>
				</div>
				<button
					type="button"
					class="rounded-lg border px-3 py-1.5 text-xs font-medium transition {offlineOverride
						? 'border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20'
						: 'border-foreground/10 bg-foreground/5 text-foreground/75 hover:bg-foreground/10'}"
					onclick={toggleOffline}
				>
					{offlineOverride ? 'restore' : 'simulate offline'}
				</button>
			</div>
			<div class="text-foreground/40 mt-3 text-xs">
				actual: <span class="text-foreground/60"
					>{navigator.onLine ? 'online' : 'offline'}</span
				>
				· store:
				<span class="text-foreground/60">{network.online ? 'online' : 'offline'}</span>
			</div>
		</div>

		<!-- update toast trigger -->
		<div class="border-foreground/10 bg-foreground/5 rounded-xl border p-5">
			<div class="flex items-center justify-between">
				<div>
					<div class="text-foreground/85 text-sm font-semibold">update toast</div>
					<div class="text-foreground/55 mt-1 text-sm">
						toggles <code class="text-xs">swUpdate.updateAvailable</code> to show/hide the
						toast.
					</div>
				</div>
				<button
					type="button"
					class="rounded-lg border px-3 py-1.5 text-xs font-medium transition {updateOverride
						? 'border-amber-500/30 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20'
						: 'border-foreground/10 bg-foreground/5 text-foreground/75 hover:bg-foreground/10'}"
					onclick={toggleUpdate}
				>
					{updateOverride ? 'restore' : 'simulate update'}
				</button>
			</div>
			<div class="text-foreground/40 mt-3 text-xs">
				store: <span class="text-foreground/60"
					>{swUpdate.updateAvailable ? 'update available' : 'up to date'}</span
				>
			</div>
		</div>

		<!-- install prompt trigger -->
		<div class="border-foreground/10 bg-foreground/5 rounded-xl border p-5">
			<div class="flex items-center justify-between">
				<div>
					<div class="text-foreground/85 text-sm font-semibold">install prompt</div>
					<div class="text-foreground/55 mt-1 text-sm">
						toggles <code class="text-xs">installPrompt.canInstall</code> to show/hide the
						dialog.
					</div>
				</div>
				<button
					type="button"
					class="rounded-lg border px-3 py-1.5 text-xs font-medium transition {installOverride
						? 'border-green-500/30 bg-green-500/10 text-green-400 hover:bg-green-500/20'
						: 'border-foreground/10 bg-foreground/5 text-foreground/75 hover:bg-foreground/10'}"
					onclick={toggleInstall}
				>
					{installOverride ? 'restore' : 'simulate prompt'}
				</button>
			</div>
			<div class="text-foreground/40 mt-3 text-xs">
				canInstall: <span class="text-foreground/60">{installPrompt.canInstall}</span>
				· isInstalled: <span class="text-foreground/60">{installPrompt.isInstalled}</span>
				· dismissed: <span class="text-foreground/60">{installPrompt.dismissed}</span>
			</div>
		</div>

		<!-- offline page link -->
		<div class="border-foreground/10 bg-foreground/5 rounded-xl border p-5">
			<div class="flex items-center justify-between">
				<div>
					<div class="text-foreground/85 text-sm font-semibold">offline page</div>
					<div class="text-foreground/55 mt-1 text-sm">
						preview the static offline fallback served by the service worker.
					</div>
				</div>
				<a
					href="/offline.html"
					target="_blank"
					rel="external noopener"
					class="border-foreground/10 bg-foreground/5 text-foreground/75 hover:bg-foreground/10 rounded-lg border px-3 py-1.5 text-xs font-medium transition"
				>
					open offline page
				</a>
			</div>
		</div>
	</div>
</div>
