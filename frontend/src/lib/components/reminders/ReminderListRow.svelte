<script lang="ts">
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import EllipsisVertical from '$lib/components/icons/EllipsisVertical.svelte'
	import { device } from '$lib/stores/device.svelte'

	type Leading =
		| {
				type: 'checkbox'
		  }
		| {
				type: 'emoji'
				emoji: string
				color?: string | null
		  }

	interface Props {
		title: string
		count?: number | null
		selected: boolean
		leading: Leading
		onSelect: () => void
		onMenu?: () => void
	}

	let { title, count = null, selected, leading, onSelect, onMenu }: Props = $props()
</script>

<div
	role="button"
	tabindex="0"
	class="group rounded-container flex w-full cursor-pointer items-center gap-3 border border-transparent bg-transparent px-3 py-2.5 text-left transition-all duration-200 hover:border-white/10 hover:bg-white/5 {selected
		? 'shadow-[inset_0_2px_8px_rgba(255,255,255,0.1)]'
		: ''}"
	style={selected
		? 'background-color: var(--accent-bg); border-color: var(--accent-border);'
		: ''}
	onclick={onSelect}
	onkeydown={(event) => {
		if (event.key !== 'Enter' && event.key !== ' ') return
		event.preventDefault()
		onSelect()
	}}
>
	{#if leading.type === 'checkbox'}
		<span class="flex h-8 w-8 items-center justify-center rounded-xl bg-white/8 text-white/80">
			<CheckBox className="h-5 w-5" />
		</span>
	{:else}
		<span
			class="flex h-8 w-8 items-center justify-center rounded-xl text-white"
			style:background-color={leading.color ?? 'rgba(255,255,255,0.08)'}
		>
			<span class="text-sm">{leading.emoji}</span>
		</span>
	{/if}

	<span class="flex min-w-0 flex-1 items-center gap-2">
		<span class="min-w-0 truncate text-[0.95rem] font-medium text-white/90">{title}</span>
		{#if count !== null && count > 0}
			<span class="text-xs text-white/55">{count}</span>
		{/if}
	</span>

	{#if onMenu}
		<button
			type="button"
			class="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-transparent bg-transparent text-white/65 transition-all duration-150 hover:border-white/10 hover:bg-white/5 hover:text-white {device.isTouch ||
			!device.hasHover
				? 'opacity-100'
				: 'opacity-0 group-hover:opacity-100'}"
			aria-label="list options"
			onclick={(event) => {
				event.stopPropagation()
				onMenu()
			}}
		>
			<EllipsisVertical className="h-4 w-4" />
		</button>
	{/if}

	<ChevronRight className="h-4 w-4 text-white/35 transition-colors group-hover:text-white/55" />
</div>
