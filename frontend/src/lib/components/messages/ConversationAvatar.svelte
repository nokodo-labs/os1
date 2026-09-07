<script lang="ts">
	/**
	 * the faces of a conversation: one for a DM, a 2x2 grid for a group.
	 * shared so rows and requests read as the same object.
	 */

	import User from '$lib/components/icons/User.svelte'
	import { getUserInitials } from '$lib/utils'
	import type { ConversationFace } from '$lib/utils/conversationDisplay'

	interface Props {
		faces: ConversationFace[]
		isGroup: boolean
		sizeClass?: string
		textClass?: string
	}

	let { faces, isGroup, sizeClass = 'size-11', textClass = 'text-sm' }: Props = $props()

	const lead = $derived(faces[0] ?? null)
	const stack = $derived(faces.slice(0, 4))
</script>

<div class="relative shrink-0 {sizeClass}">
	{#if isGroup && stack.length > 1}
		<div class="grid size-full grid-cols-2 grid-rows-2 gap-0.5 overflow-hidden rounded-full">
			{#each stack as face (face.id)}
				{#if face.avatarUrl}
					<img src={face.avatarUrl} alt={face.label} class="h-full w-full object-cover" />
				{:else}
					<div
						class="flex h-full w-full items-center justify-center bg-(--accent-primary)/15 text-[0.6rem] font-semibold text-(--accent-primary)"
					>
						{getUserInitials(face.label)}
					</div>
				{/if}
			{/each}
		</div>
	{:else if lead?.avatarUrl}
		<img src={lead.avatarUrl} alt={lead.label} class="size-full rounded-full object-cover" />
	{:else}
		<div
			class="flex size-full items-center justify-center rounded-full bg-(--accent-primary)/15 font-semibold text-(--accent-primary) {textClass}"
		>
			{#if lead}{getUserInitials(lead.label)}{:else}<User class="h-5 w-5" />{/if}
		</div>
	{/if}
</div>
