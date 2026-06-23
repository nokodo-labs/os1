<script lang="ts">
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import DocumentArrowDown from '$lib/components/icons/DocumentArrowDown.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Note from '$lib/components/icons/Note.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'
	import type { AccessLevel } from '$lib/stores/resourceAccess.svelte'
	import { levelLabel, resourceLabel } from './resourceAccessModal'

	interface Props {
		panelClass: string
		iconBoxClass: string
		resourceType: ResourceAccessPayload['resourceType'] | undefined
		title: string
		url: string
		currentLevel: AccessLevel | null
	}

	let { panelClass, iconBoxClass, resourceType, title, url, currentLevel }: Props = $props()
</script>

<section
	class="{panelClass} flex min-w-0 items-center gap-4 p-5 max-[680px]:flex-wrap max-[430px]:items-start max-[430px]:gap-3 max-[430px]:p-4"
>
	<div class="{iconBoxClass} max-[430px]:h-10 max-[430px]:w-10 max-[430px]:rounded-[13px]">
		{#if resourceType === 'thread'}
			<ChatBubble class="h-5 w-5" />
		{:else if resourceType === 'note'}
			<Note class="h-5 w-5" />
		{:else if resourceType === 'project'}
			<FinderFolder class="h-5 w-5" />
		{:else if resourceType === 'reminder_list'}
			<ListBullet class="h-5 w-5" />
		{:else if resourceType === 'calendar'}
			<Calendar class="h-5 w-5" />
		{:else if resourceType === 'group'}
			<UserGroup class="h-5 w-5" />
		{:else if resourceType === 'agent'}
			<Sparkles class="h-5 w-5" />
		{:else}
			<DocumentArrowDown class="h-5 w-5" />
		{/if}
	</div>
	<div class="min-w-40 flex-1">
		<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
			{resourceLabel(resourceType)}
		</p>
		<h3 class="text-foreground min-w-0 truncate text-lg font-semibold">
			{title}
		</h3>
		<p class="text-foreground/50 mt-0.5 min-w-0 truncate text-xs">
			{url}
		</p>
	</div>
	{#if currentLevel}
		<div
			class="rounded-pill shrink-0 border border-[color-mix(in_oklch,var(--accent-primary)_25%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_10%,transparent)] px-3 py-2 text-xs font-semibold text-(--accent-primary) max-[430px]:w-full max-[430px]:text-center"
		>
			{levelLabel(currentLevel)}
		</div>
	{/if}
</section>
