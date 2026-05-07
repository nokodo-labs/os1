<script lang="ts">
	import { getMediaUrls } from '$lib/config/media'
	import type { HTMLImgAttributes } from 'svelte/elements'

	interface Props extends Omit<HTMLImgAttributes, 'src' | 'alt' | 'class'> {
		class?: string
		alt?: string
	}

	let { class: className = 'h-7 w-auto', alt = 'nokodo logo', ...rest }: Props = $props()

	const mediaUrls = $derived(getMediaUrls())
	const logoSrc = $derived(
		mediaUrls.sidebarLogo ?? 'https://nokodo.net/media/images/logo_full.svg'
	)
</script>

<img src={logoSrc} {alt} class={className} {...rest} />
