<script lang="ts">
	import type { HTMLImgAttributes } from 'svelte/elements'

	const OS1_LOGO_URL = 'https://nokodo.net/static/os1/sidebar-logo.svg'

	interface Props extends Omit<HTMLImgAttributes, 'src' | 'alt' | 'class'> {
		class?: string
		alt?: string
	}

	let { class: className = 'h-7 w-28 max-w-full', alt = 'OS1 logo', ...rest }: Props = $props()
</script>

<span class="inline-flex min-w-0 items-center justify-center {className}">
	<img src={OS1_LOGO_URL} {alt} class="block h-full w-full object-contain" {...rest} />
</span>
