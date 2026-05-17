<script lang="ts">
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'

	type AssetSource = 'default' | 'cdn' | 'custom' | 'disabled'

	type Props = {
		id: string
		title: string
		description?: string
		source?: AssetSource
		url?: string
		defaultUrl: string
		cdnUrl?: string
		allowDisabled?: boolean
		customPlaceholder?: string
	}

	let {
		id,
		title,
		description = '',
		source = $bindable<AssetSource>('default'),
		url = $bindable(''),
		defaultUrl,
		cdnUrl = '',
		allowDisabled = false,
		customPlaceholder = 'https://cdn.example.com/path/file.png',
	}: Props = $props()

	const resolvedLabel = $derived.by(() => {
		if (source === 'disabled') return 'omitted from generated output'
		if (source === 'custom') return url.trim() || 'waiting for custom URL'
		if (source === 'cdn') return cdnUrl || 'set public CDN origin to use CDN-default'
		return defaultUrl
	})
</script>

<div class="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/35 p-3">
	<div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
		<div class="min-w-0 space-y-1">
			<Label for={`${id}_source`}>{title}</Label>
			{#if description}
				<p class="text-xs text-zinc-500">{description}</p>
			{/if}
			<p class="text-xs break-all text-zinc-400">
				<code class="text-zinc-300">{resolvedLabel}</code>
			</p>
		</div>
		<select
			id={`${id}_source`}
			bind:value={source}
			class="h-10 rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-500 md:w-40"
		>
			<option value="default">default</option>
			<option value="cdn">CDN-default</option>
			<option value="custom">custom URL</option>
			{#if allowDisabled}
				<option value="disabled">disabled</option>
			{/if}
		</select>
	</div>
	{#if source === 'custom'}
		<Input
			id={`${id}_url`}
			bind:value={url}
			placeholder={customPlaceholder}
			class="rounded-xl"
		/>
	{/if}
</div>
