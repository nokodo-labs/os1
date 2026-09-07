<script lang="ts">
	import BackgroundManager, {
		type BackgroundType,
	} from '$lib/components/backgrounds/BackgroundManager.svelte'

	interface Props {
		type: BackgroundType
	}

	let { type }: Props = $props()
</script>

<!-- mirrors routes/+layout.svelte: wallpaper and app shell are siblings -->
<BackgroundManager {type} />

<div class="fixed inset-0 z-0" data-testid="app-shell">
	<div data-testid="app-content"></div>
</div>
