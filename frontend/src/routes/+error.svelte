<script lang="ts">
	import { goto } from '$app/navigation'
	import { page } from '$app/state'
	import Home from '$lib/components/icons/Home.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'

	let { status: statusProp, error } = $props<{ status?: number; error: App.Error }>()

	const status = $derived.by(() => statusProp ?? page.status ?? 500)

	const errorTitle = $derived.by(() => {
		if (status === 404) return 'page not found'
		if (status >= 500) return 'something went wrong'
		return 'something went wrong'
	})

	const message = $derived.by(() => {
		if (status === 404) return "the page you're looking for doesn't exist"
		return error?.message || 'an unexpected error happened'
	})

	$effect(() => {
		pageTitleStore.pageTitle = status === 404 ? 'page not found' : 'error'
	})
</script>

<div class="relative flex min-h-0 flex-1 items-center justify-center px-6 py-10">
	<div
		class="liquid-glass liquid-glass--frosted rounded-container w-full max-w-lg overflow-hidden shadow-[0_30px_90px_rgba(0,0,0,0.45)]"
	>
		<span class="liquid-glass__highlight" aria-hidden="true"></span>
		<div class="liquid-glass__content px-7 py-7">
			<div class="text-center">
				<div class="text-[4.75rem] leading-none font-semibold tracking-tight text-white/90">
					{status}
				</div>
				<div class="mt-3 text-xl font-semibold text-white/85">{errorTitle}</div>
				<div class="mt-2 text-sm text-white/60">{message}</div>
			</div>

			<div class="mt-6 flex justify-center">
				<button
					type="button"
					class="group inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2.5 text-sm font-medium text-white/85 transition-colors duration-150 hover:bg-white/12 hover:text-white active:scale-[0.99]"
					onclick={() => void goto('/', { keepFocus: true, noScroll: true })}
					aria-label="go home"
				>
					<Home
						className="size-4 text-white/70 transition-colors duration-150 group-hover:text-white/85"
					/>
					go home
				</button>
			</div>
		</div>
	</div>
</div>
