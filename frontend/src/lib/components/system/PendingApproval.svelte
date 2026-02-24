<script lang="ts">
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import { permissions } from '$lib/stores/permissions.svelte'
	import { session } from '$lib/stores/session.svelte'

	interface Props {
		supportEmail?: string | null
		adminEmail?: string | null
	}

	let { supportEmail = null, adminEmail = null }: Props = $props()

	let isRefreshing = $state(false)

	function handleLogout() {
		session.clear()
		window.location.href = '/login'
	}

	async function handleRefresh() {
		if (isRefreshing) return
		isRefreshing = true
		try {
			await permissions.refresh()
		} finally {
			isRefreshing = false
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center px-6">
	<div class="w-full max-w-sm space-y-5 text-center">
		<div
			class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-white/8 text-2xl"
		>
			⏳
		</div>

		<div class="space-y-2">
			<h1 class="text-lg font-semibold text-white/90">pending approval</h1>
			<p class="text-sm leading-relaxed text-white/50">
				an administrator needs to approve your account before you can continue.
			</p>
		</div>

		{#if supportEmail || adminEmail}
			<div class="rounded-container border border-white/10 bg-white/5 px-5 py-4 text-left">
				<p class="mb-3 text-xs font-medium tracking-wide text-white/40 uppercase">
					need help?
				</p>
				<div class="space-y-2">
					{#if supportEmail}
						<a
							href="mailto:{supportEmail}"
							class="flex items-center gap-2 text-sm text-white/65 transition-colors hover:text-white/90"
						>
							{supportEmail}
						</a>
					{/if}
					{#if adminEmail && adminEmail !== supportEmail}
						<a
							href="mailto:{adminEmail}"
							class="flex items-center gap-2 text-sm text-white/65 transition-colors hover:text-white/90"
						>
							{adminEmail}
						</a>
					{/if}
				</div>
			</div>
		{/if}

		<div class="flex items-center justify-center gap-3">
			<button
				type="button"
				class="rounded-pill inline-flex items-center gap-2 border border-white/12 bg-white/6 px-4 py-2 text-sm text-white/70 transition-colors hover:bg-white/10 hover:text-white/90 disabled:opacity-50"
				onclick={handleRefresh}
				disabled={isRefreshing}
			>
				<ArrowPath class="h-4 w-4 {isRefreshing ? 'animate-spin' : ''}" />
				{isRefreshing ? 'checking...' : 'refresh'}
			</button>
			<button
				type="button"
				class="rounded-pill border border-white/10 bg-transparent px-4 py-2 text-sm text-white/45 transition-colors hover:bg-white/5 hover:text-white/70"
				onclick={handleLogout}
			>
				log out
			</button>
		</div>
	</div>
</div>
