<script lang="ts">
	import { SEARCH_RESOURCE_TYPES, type SearchResourceType } from '$lib/api/streaming'
	import ChatBottomPanel from '$lib/components/chat/ChatBottomPanel.svelte'
	import Switch from '$lib/components/primitives/ResolverSwitch.svelte'
	import {
		resourceAccentColor,
		resourceVisual,
		type ResourceVisualType,
	} from '$lib/resources/resourceVisuals'

	interface Props {
		open: boolean
		selectedTypes: SearchResourceType[]
		onChange: (types: SearchResourceType[]) => void
		onClose: () => void
	}

	let { open, selectedTypes, onChange, onClose }: Props = $props()

	type SearchTypeOption = {
		type: SearchResourceType
		label: string
		visualType: ResourceVisualType
	}

	const options: SearchTypeOption[] = [
		{ type: 'thread', label: 'chats', visualType: 'thread' },
		{ type: 'note', label: 'notes', visualType: 'note' },
		{ type: 'reminder', label: 'reminders', visualType: 'reminder_list' },
		{ type: 'calendar_event', label: 'calendar', visualType: 'calendar' },
		{ type: 'project', label: 'projects', visualType: 'project' },
	]

	const normalizedSelectedTypes = $derived.by(() => {
		const selected = new Set(selectedTypes)
		const normalized = SEARCH_RESOURCE_TYPES.filter((type) => selected.has(type))
		return normalized.length > 0 ? normalized : SEARCH_RESOURCE_TYPES
	})
	const selectedSet = $derived(new Set(normalizedSelectedTypes))
	function toggleType(type: SearchResourceType): void {
		if (selectedSet.has(type) && normalizedSelectedTypes.length === 1) return
		const next = selectedSet.has(type)
			? normalizedSelectedTypes.filter((selectedType) => selectedType !== type)
			: [...normalizedSelectedTypes, type]
		onChange(SEARCH_RESOURCE_TYPES.filter((selectedType) => next.includes(selectedType)))
	}
</script>

<ChatBottomPanel {open} {onClose} ariaLabel="search settings">
	<div class="px-4 pt-3 pb-2">
		<div class="text-foreground/45 pt-1 pb-2 text-[11px] font-semibold tracking-widest">
			search in
		</div>

		<div class="space-y-0.5">
			{#each options as option (option.type)}
				{@const visual = resourceVisual(option.visualType)}
				{@const Icon = visual.icon}
				{@const selected = selectedSet.has(option.type)}
				<button
					type="button"
					class="rounded-pill hover:bg-foreground/8 flex w-full cursor-pointer items-center gap-3 px-2 py-2.5 transition-colors duration-150"
					onclick={() => toggleType(option.type)}
				>
					<Icon
						class="h-5 w-5 shrink-0"
						color={resourceAccentColor(option.visualType)}
						strokeWidth="2"
					/>
					<span
						class="text-foreground/80 min-w-0 flex-1 truncate text-left text-sm font-medium"
					>
						{option.label}
					</span>
					<Switch
						size="sm"
						checked={selected}
						disabled={selected && normalizedSelectedTypes.length === 1}
						ariaLabel={`${option.label} search`}
						onchange={() => toggleType(option.type)}
					/>
				</button>
			{/each}
		</div>
	</div>
</ChatBottomPanel>
