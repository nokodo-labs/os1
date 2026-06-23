<script lang="ts">
	interface Props {
		target: HTMLElement | null
		threshold?: number
		class?: string
	}

	let {
		target,
		threshold = 4,
		class: className = 'pointer-events-none absolute inset-x-0 top-0 z-[1] h-10 bg-[linear-gradient(to_bottom,black_0%,rgb(0_0_0/0.88)_10%,rgb(0_0_0/0.4)_35%,transparent_100%)] transition-opacity duration-150',
	}: Props = $props()

	let visible = $state(false)

	function updateVisible(): void {
		visible = Boolean(target && target.scrollTop > threshold)
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

<div class="{className} {visible ? 'opacity-100' : 'opacity-0'}"></div>
