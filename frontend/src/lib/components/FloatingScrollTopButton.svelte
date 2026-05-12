<script lang="ts">
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'

	interface Props {
		target: HTMLElement | null
		threshold?: number
		class?: string
		style?: string
		label?: string
	}

	let {
		target,
		threshold = 96,
		class: className = 'pointer-events-none absolute inset-x-0 bottom-4 z-20 flex justify-center',
		style = '',
		label = 'scroll to top',
	}: Props = $props()

	let visible = $state(false)

	function updateVisible(): void {
		visible = Boolean(target && target.scrollTop > threshold)
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

{#if visible}
	<div class={className} {style}>
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
	</div>
{/if}
