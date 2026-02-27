<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import Home from '$lib/components/icons/Home.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'

	const status = $derived.by(() => page.status ?? 500)
	const currentError = $derived.by(() => page.error)

	const errorTitle = $derived.by(() => {
		if (status === 404) return 'page not found'
		if (status >= 500) return 'something went wrong'
		return 'something went wrong'
	})

	const message = $derived.by(() => {
		if (status === 404) return "the page you're looking for doesn't exist"
		const err = currentError
		if (
			err &&
			typeof err === 'object' &&
			'message' in err &&
			typeof (err as { message?: unknown }).message === 'string'
		)
			return (err as { message: string }).message
		return 'an unexpected error happened'
	})

	$effect(() => {
		pageTitleStore.pageTitle = status === 404 ? 'page not found' : 'error'
	})
</script>

<div class="relative flex min-h-0 flex-1 items-center justify-center px-6 py-10">
	<div
		class="liquid-glass liquid-glass--frosted rounded-container w-full max-w-lg overflow-hidden shadow-[0_30px_90px_rgba(0,0,0,0.45)]"
	>
		<div class="relative z-10 px-7 py-7">
			<div class="text-center">
				<div
					class="text-foreground/90 text-[4.75rem] leading-none font-semibold tracking-tight"
				>
					{status}
				</div>
				<div class="text-foreground/85 mt-3 text-xl font-semibold">{errorTitle}</div>
				<div class="text-foreground/60 mt-2 text-sm">{message}</div>
			</div>

			<div class="mt-6 flex justify-center">
				<button
					type="button"
					class="group border-foreground/10 bg-foreground/8 text-foreground/85 hover:bg-foreground/12 hover:text-foreground inline-flex cursor-pointer items-center gap-2 rounded-full border px-4 py-2.5 text-sm font-medium transition-colors duration-150 active:scale-[0.99]"
					onclick={() => void goto(resolve('/'), { keepFocus: true, noScroll: true })}
					aria-label="go home"
				>
					<Home
						variant="solid"
						class="text-foreground/70 group-hover:text-foreground/85 size-4 transition-colors duration-150"
					/>
					go home
				</button>
			</div>
		</div>
	</div>
</div>
