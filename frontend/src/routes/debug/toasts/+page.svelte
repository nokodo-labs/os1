<script lang="ts">
	import type { EphemeralVariant } from '$lib/stores/notifications.svelte'
	import { notifications } from '$lib/stores/notifications.svelte'

	const variants: EphemeralVariant[] = ['error', 'success', 'info', 'warning']

	function fireNotification() {
		const id = `debug-${Date.now()}`
		notifications.toasts = [
			...notifications.toasts,
			{
				id,
				type: 'notification',
				title: 'test notification',
				body: 'this is a notification-backed toast with body text.',
				iconUrl: null,
				imageUrl: null,
				addedAt: Date.now(),
			},
		]
	}

	function fireEphemeral(variant: EphemeralVariant) {
		notifications.pushEphemeralToast(variant, `test ${variant} toast`)
	}

	function fireAll() {
		fireNotification()
		for (const v of variants) {
			setTimeout(() => fireEphemeral(v), 200 * (variants.indexOf(v) + 1))
		}
	}
</script>

<div class="mx-auto w-full max-w-4xl px-6 pt-10 pb-24">
	<h1 class="text-xl font-semibold">toast playground</h1>
	<p class="text-muted-foreground mt-2 text-sm">
		fire ephemeral and notification toasts to test rendering, dismiss, and stacking.
	</p>

	<div class="mt-8 space-y-6">
		<!-- notification type -->
		<section>
			<h2 class="text-foreground/70 text-sm font-medium">type: notification</h2>
			<p class="text-muted-foreground mt-1 text-xs">
				liquid glass banner (desktop top-right, mobile full-width top). swipe to dismiss.
			</p>
			<button
				type="button"
				class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:bg-foreground/10 mt-3 rounded-lg border px-4 py-2 text-sm transition"
				onclick={fireNotification}
			>
				fire notification toast
			</button>
		</section>

		<!-- ephemeral variants -->
		<section>
			<h2 class="text-foreground/70 text-sm font-medium">type: ephemeral</h2>
			<p class="text-muted-foreground mt-1 text-xs">
				colored pill at bottom-center. auto-dismiss after 5s.
			</p>
			<div class="mt-3 flex flex-wrap gap-2">
				{#each variants as variant (variant)}
					<button
						type="button"
						class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:bg-foreground/10 rounded-lg border px-4 py-2 text-sm transition"
						onclick={() => fireEphemeral(variant)}
					>
						{variant}
					</button>
				{/each}
			</div>
		</section>

		<!-- fire all -->
		<section>
			<h2 class="text-foreground/70 text-sm font-medium">stress test</h2>
			<p class="text-muted-foreground mt-1 text-xs">
				fires one notification + all four ephemeral variants with staggered timing.
			</p>
			<button
				type="button"
				class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:bg-foreground/10 mt-3 rounded-lg border px-4 py-2 text-sm transition"
				onclick={fireAll}
			>
				fire all
			</button>
		</section>

		<!-- active toasts -->
		<section>
			<h2 class="text-foreground/70 text-sm font-medium">
				active toasts ({notifications.toasts.length})
			</h2>
			{#if notifications.toasts.length === 0}
				<p class="text-muted-foreground mt-2 text-xs italic">none</p>
			{:else}
				<ul class="text-foreground/60 mt-2 space-y-1 text-xs">
					{#each notifications.toasts as t (t.id)}
						<li class="flex items-center gap-2">
							<span class="text-foreground/40 font-mono text-[10px]"
								>{t.id.slice(0, 16)}</span
							>
							<span class="bg-foreground/8 rounded px-1.5 py-0.5 font-medium"
								>{t.type}</span
							>
							{#if t.variant}
								<span class="bg-foreground/8 rounded px-1.5 py-0.5"
									>{t.variant}</span
								>
							{/if}
							<span class="truncate">{t.title}</span>
							<button
								type="button"
								class="text-foreground/40 hover:text-foreground/70 ml-auto"
								onclick={() => notifications.dismissToast(t.id)}
							>
								dismiss
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	</div>
</div>
