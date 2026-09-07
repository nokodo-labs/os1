<script lang="ts">
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'

	interface Props {
		target: HTMLElement | null
		threshold?: number
		/** anchor to the viewport instead of the in-flow scroll shell; adds the safe-area inset so it clears the home indicator */
		fixed?: boolean
		/** extra positioning, e.g. horizontal offset for page-level usage */
		style?: string
		label?: string
	}

	let {
		target,
		threshold = 96,
		fixed = false,
		style = '',
		label = 'scroll to top',
	}: Props = $props()

	// sit 1.5rem above the bottom. viewport-anchored usage (fixed) also adds the safe-area inset
	// so it clears the home indicator; in-flow usage sits inside a container that already handles it.
	const positionClass = $derived(
		fixed
			? 'fixed inset-x-0 bottom-[calc(var(--safe-area-bottom)+1.5rem)]'
			: 'absolute inset-x-0 bottom-6'
	)

	let visible = $state(false)

	function updateVisible(): void {
		const el = target
		if (!el) {
			visible = false
			return
		}
		// hide at both ends: near the top (nothing above) and near the bottom (nothing below).
		const max = el.scrollHeight - el.clientHeight
		const atTop = el.scrollTop <= threshold
		const atBottom = el.scrollTop >= max - threshold
		visible = !atTop && !atBottom
	}

	function scrollToTop(): void {
		target?.scrollTo({ top: 0, behavior: 'smooth' })
	}

	$effect(() => {
		const el = target
		if (!el) {
			visible = false
			return
		}

		updateVisible()
		const onScroll = () => updateVisible()
		el.addEventListener('scroll', onScroll, { passive: true })
		return () => el.removeEventListener('scroll', onScroll)
	})
</script>

{#snippet button()}
	<LiquidGlass
		tag="button"
		type="button"
		class="border-foreground/10 text-foreground/85 hover:bg-foreground/10 hover:text-foreground pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full border transition-colors"
		cornerRadius={18}
		aria-label={label}
		onpointerdown={(event: PointerEvent) => event.preventDefault()}
		onclick={scrollToTop}
	>
		<ArrowUp class="h-4 w-4" />
	</LiquidGlass>
{/snippet}

{#if visible}
	<div class="pointer-events-none {positionClass} z-20 flex justify-center" {style}>
		{@render button()}
	</div>
{/if}
