<script lang="ts">
	import type { components } from '$lib/api/types'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import CitationWidget from '$lib/components/widgets/CitationWidget.svelte'

	type Citation = components['schemas']['Citation']

	interface Props {
		open: boolean
		citations: Citation[]
		onClose: () => void
	}

	let { open, citations, onClose }: Props = $props()

	/** deduplicate by source_type + source_id */
	const unique = $derived.by(() => {
		const result: Citation[] = []
		const keys: string[] = []
		for (const c of citations) {
			const key = `${c.source_type}:${c.source_id}`
			if (!keys.includes(key)) {
				keys.push(key)
				result.push(c)
			}
		}
		return result
	})
</script>

<BaseModal {open} title="sources" {onClose} widthClassName="max-w-lg">
	<div class="flex flex-col gap-2">
		{#each unique as c (c.source_type + ':' + c.source_id)}
			<CitationWidget citation={c} layout="list" />
		{/each}
	</div>
</BaseModal>
