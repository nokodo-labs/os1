<script lang="ts">
	import { session } from '$lib/stores/session.svelte'

	interface Props {
		supportEmail?: string | null
		adminEmail?: string | null
	}

	let { supportEmail = null, adminEmail = null }: Props = $props()

	function handleLogout() {
		session.clear()
		window.location.href = '/login'
	}
</script>

<div class="flex min-h-screen items-center justify-center px-6">
	<div class="w-full max-w-md space-y-6 text-center">
		<div
			class="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-white/10 text-3xl"
		>
			⏳
		</div>

		<div class="space-y-2">
			<h1 class="text-xl font-semibold text-white/90">your account is pending approval</h1>
			<p class="text-sm text-white/50">
				an administrator needs to grant you access before you can continue. you'll be able
				to use the app as soon as your access is confirmed.
			</p>
		</div>

		{#if supportEmail || adminEmail}
			<div class="space-y-2 rounded-2xl border border-white/10 bg-white/5 px-5 py-4">
				<p class="text-xs font-medium text-white/50">need help?</p>
				{#if supportEmail}
					<a
						href="mailto:{supportEmail}"
						class="block text-sm text-white/70 transition-colors hover:text-white/90"
					>
						{supportEmail}
					</a>
				{/if}
				{#if adminEmail && adminEmail !== supportEmail}
					<a
						href="mailto:{adminEmail}"
						class="block text-sm text-white/70 transition-colors hover:text-white/90"
					>
						{adminEmail}
					</a>
				{/if}
			</div>
		{/if}

		<button
			type="button"
			class="rounded-xl border border-white/10 bg-white/5 px-6 py-2 text-sm text-white/60 transition-colors hover:bg-white/10 hover:text-white/80"
			onclick={handleLogout}
		>
			log out
		</button>
	</div>
</div>
