<script lang="ts">
	import { page } from '$app/state'
	import Film from '$lib/components/icons/Film.svelte'
	import Popcorn from '$lib/components/icons/Popcorn.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import TvRetro from '$lib/components/icons/TvRetro.svelte'
	import TabIslandScaffold from '$lib/components/layouts/TabIslandScaffold.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	const sections = [
		{ id: 'discover', label: 'discover', icon: Sparkles, href: '/media/discover' as const },
		{ id: 'search', label: 'search', icon: Search, href: '/media/search' as const },
		{ id: 'movies', label: 'movies', icon: Film, href: '/media/movies' as const },
		{ id: 'shows', label: 'shows', icon: TvRetro, href: '/media/shows' as const },
	]

	const activeSection = $derived(
		sections.find((section) => page.url.pathname.startsWith(section.href)) ?? sections[0]
	)
	const activeId = $derived(activeSection.id)
</script>

<TabIslandScaffold {sections} {activeId}>
	<div class="flex flex-1 flex-col gap-6 py-4">
		<!-- one title for the whole app, naming both the app and the tab you are in, so it
		     lives here and carries its own view transition name across tab changes. -->
		<div class="flex items-center" style="view-transition-name: media-page-header;">
			<PageTitle
				icon={Popcorn}
				label="media · {activeSection.label}"
				iconColor="text-(--accent-primary)"
			/>
		</div>

		{@render children()}
	</div>
</TabIslandScaffold>
