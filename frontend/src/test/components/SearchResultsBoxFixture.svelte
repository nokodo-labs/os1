<script lang="ts">
	import SearchResultsBox, {
		type SearchResultsKeyHandler,
		type SearchResultsSection,
	} from '$lib/components/common/SearchResultsBox.svelte'

	interface Item {
		id: string
		label: string
	}

	interface Props {
		query?: string
		sections: SearchResultsSection<Item>[]
		open?: boolean
		onSelect?: (item: Item) => void
		onDismiss?: () => void
		onKeyHandler?: (handler: SearchResultsKeyHandler) => void
	}

	let {
		query = 'a',
		sections,
		open = true,
		onSelect = () => {},
		onDismiss,
		onKeyHandler,
	}: Props = $props()
</script>

<SearchResultsBox {query} {sections} {open} {onSelect} {onDismiss} {onKeyHandler}>
	{#snippet row(item, state)}
		<button
			type="button"
			role="option"
			aria-selected={state.highlighted}
			data-row={item.id}
			onmouseenter={state.hover}
			onclick={state.select}
		>
			{item.label}
		</button>
	{/snippet}

	{#snippet footer(close)}
		<button type="button" data-footer onclick={close}>search more in-depth</button>
	{/snippet}
</SearchResultsBox>
