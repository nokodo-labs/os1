<script lang="ts">
	import { page } from '$app/state'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import Users from '$lib/components/icons/Users.svelte'
	import TabIslandScaffold from '$lib/components/layouts/TabIslandScaffold.svelte'
	import type { Snippet } from 'svelte'

	let { children }: { children: Snippet } = $props()

	const sections = [
		{ id: 'friends', label: 'friends', icon: Users, href: '/social/friends' },
		{ id: 'groups', label: 'groups', icon: UserGroup, href: '/social/groups' },
	]

	const activeId = $derived(page.url.pathname.includes('/groups') ? 'groups' : 'friends')
</script>

<TabIslandScaffold {sections} {activeId}>
	{@render children()}
</TabIslandScaffold>
