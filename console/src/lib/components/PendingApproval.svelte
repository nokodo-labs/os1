<script lang="ts">
	import { auth } from '$lib/auth.svelte'

	interface Props {
		supportEmail?: string | null
		adminEmail?: string | null
	}

	let { supportEmail = null, adminEmail = null }: Props = $props()

	async function handleLogout() {
		await auth.logout()
		window.location.href = '/login'
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-neutral-950 px-6">
	<div class="w-full max-w-md space-y-6 text-center">
		<div
			class="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-neutral-800 text-3xl"
		>
			⏳
		</div>

		<div class="space-y-2">
			<h1 class="text-xl font-semibold text-neutral-100">your account is pending approval</h1>
			<p class="text-sm text-neutral-400">
				an administrator needs to grant you console access before you can continue.
			</p>
		</div>

		{#if supportEmail || adminEmail}
			<div class="space-y-2 rounded-xl border border-neutral-800 bg-neutral-900 px-5 py-4">
				<p class="text-xs font-medium text-neutral-500">need help?</p>
				{#if supportEmail}
					<a
						href="mailto:{supportEmail}"
						class="block text-sm text-neutral-300 underline-offset-2 hover:underline"
					>
						{supportEmail}
					</a>
				{/if}
				{#if adminEmail && adminEmail !== supportEmail}
					<a
						href="mailto:{adminEmail}"
						class="block text-sm text-neutral-300 underline-offset-2 hover:underline"
					>
						{adminEmail}
					</a>
				{/if}
			</div>
		{/if}

		<button
			type="button"
			class="rounded-lg border border-neutral-700 bg-neutral-800 px-6 py-2 text-sm text-neutral-300 transition-colors hover:bg-neutral-700"
			onclick={handleLogout}
		>
			log out
		</button>
	</div>
</div>
