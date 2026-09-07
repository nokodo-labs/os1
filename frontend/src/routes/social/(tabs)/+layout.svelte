<script lang="ts">
	import { page } from '$app/state'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import Users from '$lib/components/icons/Users.svelte'
	import TabIslandScaffold from '$lib/components/layouts/TabIslandScaffold.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	const sections = [
		{ id: 'friends', label: 'friends', icon: Users, href: '/social/friends' as const },
		{ id: 'groups', label: 'groups', icon: UserGroup, href: '/social/groups' as const },
	]

	const activeSection = $derived(
		page.url.pathname.includes('/groups') ? sections[1] : sections[0]
	)
	const activeId = $derived(activeSection.id)
</script>

<TabIslandScaffold {sections} {activeId}>
	<div class="flex flex-1 flex-col gap-6 py-4">
		<!-- one title for the whole app, naming both the app and the tab you are in, so it
		     lives here and carries its own view transition name across tab changes. -->
		<div class="flex items-center" style="view-transition-name: social-page-header;">
			<PageTitle
				icon={Users}
				label="social · {activeSection.label}"
				iconColor="text-(--accent-primary)"
			/>
		</div>

		{@render children()}
	</div>
</TabIslandScaffold>
