<script lang="ts">
	/** renders the icon for a native tool row using frontend tool registry metadata. */

	import Bell from '$lib/components/icons/Bell.svelte'
	import Brain from '$lib/components/icons/Brain.svelte'
	import CalendarIcon from '$lib/components/icons/Calendar.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import CommandLine from '$lib/components/icons/CommandLine.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import Eye from '$lib/components/icons/Eye.svelte'
	import Film from '$lib/components/icons/Film.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Headphone from '$lib/components/icons/Headphone.svelte'
	import Note from '$lib/components/icons/Note.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Photo from '$lib/components/icons/Photo.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import { getNativeToolDefinition } from '$lib/tools'

	interface Props {
		toolName: string
		isFailed: boolean
	}

	let { toolName, isFailed }: Props = $props()
	let icon = $derived(getNativeToolDefinition(toolName)?.icon ?? 'sparkles')
	let iconClass = $derived(`h-4.5 w-4.5 ${isFailed ? 'text-destructive' : 'text-foreground/80'}`)
</script>

{#if icon === 'brain'}
	<Brain class={iconClass} />
{:else if icon === 'search'}
	<Search class={iconClass} />
{:else if icon === 'chat'}
	<ChatBubble class={iconClass} />
{:else if icon === 'globe'}
	<GlobeAlt class={iconClass} />
{:else if icon === 'note'}
	<Note class={iconClass} />
{:else if icon === 'folder'}
	<FinderFolder class={iconClass} />
{:else if icon === 'calendar'}
	<CalendarIcon class={iconClass} />
{:else if icon === 'bell'}
	<Bell class={iconClass} />
{:else if icon === 'document'}
	<Document class={iconClass} />
{:else if icon === 'pencil'}
	<Pencil class={iconClass} />
{:else if icon === 'photo'}
	<Photo class={iconClass} />
{:else if icon === 'film'}
	<Film class={iconClass} />
{:else if icon === 'headphone'}
	<Headphone class={iconClass} />
{:else if icon === 'terminal'}
	<CommandLine class={iconClass} />
{:else if icon === 'eye'}
	<Eye class={iconClass} />
{:else}
	<Sparkles class={iconClass} />
{/if}
