<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'

	goto(resolve('/social/friends'), { replaceState: true })
</script>
