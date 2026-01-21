<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { onMount } from 'svelte'

	onMount(() => {
		void goto(resolve('/dashboard'))
	})
</script>
