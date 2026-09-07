<script lang="ts">
	import Clip from '$lib/components/icons/Clip.svelte'
	import Funnel from '$lib/components/icons/Funnel.svelte'
	import SortIcon from '$lib/components/icons/SortIcon.svelte'
	import { MenuItem } from '$lib/components/primitives'
</script>

<MenuItem icon={SortIcon} data-row="sort-unselected">sort</MenuItem>
<MenuItem icon={SortIcon} selected data-row="sort-selected">sort</MenuItem>
<MenuItem icon={Clip} data-row="clip-unselected">all sources</MenuItem>
<MenuItem icon={Clip} selected data-row="clip-selected">all sources</MenuItem>
<MenuItem icon={Funnel} data-row="funnel-unselected">all</MenuItem>
<MenuItem icon={Funnel} selected data-row="funnel-selected">all</MenuItem>
