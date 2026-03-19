<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
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
			await permissions.load()
		} finally {
			isRefreshing = false
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center px-6">
	<div class="w-full max-w-sm space-y-5 text-center">
		<div
			class="bg-foreground/8 mx-auto flex h-14 w-14 items-center justify-center rounded-full text-2xl"
		>
			⏳
		</div>

		<div class="space-y-2">
			<h1 class="text-foreground/90 text-lg font-semibold">pending approval</h1>
			<p class="text-foreground/50 text-sm leading-relaxed">
				an administrator needs to approve your account before you can continue.
			</p>
		</div>

		{#if supportEmail || adminEmail}
			<div
				class="rounded-container border-foreground/10 bg-foreground/5 border px-5 py-4 text-left"
			>
				<p class="text-foreground/40 mb-3 text-xs font-medium tracking-wide uppercase">
					need help?
				</p>
				<div class="space-y-2">
					{#if supportEmail}
						<a
							href="mailto:{supportEmail}"
							class="text-foreground/65 hover:text-foreground/90 flex items-center gap-2 text-sm transition-colors"
						>
							{supportEmail}
						</a>
					{/if}
					{#if adminEmail && adminEmail !== supportEmail}
						<a
							href="mailto:{adminEmail}"
							class="text-foreground/65 hover:text-foreground/90 flex items-center gap-2 text-sm transition-colors"
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
				class="rounded-pill border-foreground/12 bg-foreground/6 text-foreground/70 hover:bg-foreground/10 hover:text-foreground/90 inline-flex items-center gap-2 border px-4 py-2 text-sm transition-colors disabled:opacity-50"
				onclick={handleRefresh}
				disabled={isRefreshing}
			>
				<ArrowPath class="h-4 w-4 {isRefreshing ? 'animate-spin' : ''}" />
				{#if isRefreshing}<ShimmerText className="inline-block">checking</ShimmerText>{:else}refresh{/if}
			</button>
			<button
				type="button"
				class="rounded-pill border-foreground/10 text-foreground/45 hover:bg-foreground/5 hover:text-foreground/70 border bg-transparent px-4 py-2 text-sm transition-colors"
				onclick={handleLogout}
			>
				log out
			</button>
		</div>
	</div>
</div>
