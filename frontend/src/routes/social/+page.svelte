<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'

	if (browser) {
		goto(resolve('/social/friends'), { replaceState: true })
	}
</script>
