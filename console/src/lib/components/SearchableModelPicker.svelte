<script lang="ts">
	import { ChevronDown, Search, X } from '@lucide/svelte'

	interface Item {
		value: string
		label: string
		sublabel?: string
	}

	interface Props {
		items: Item[]
		value: string
		placeholder?: string
		emptyLabel?: string
		searchPlaceholder?: string
		allowClear?: boolean
		clearLabel?: string
		onChange: (value: string) => void
	}

	let {
		items,
		value,
		placeholder = 'select...',
		emptyLabel = 'none',
		searchPlaceholder = 'search...',
		allowClear = true,
		clearLabel = 'none',
		onChange,
	}: Props = $props()

	let isOpen = $state(false)
	let query = $state('')
	let triggerEl = $state<HTMLButtonElement | null>(null)
	let menuEl = $state<HTMLDivElement | null>(null)
	let searchEl = $state<HTMLInputElement | null>(null)
	let dropUp = $state(false)
	let menuMaxHeight = $state(280)

	const selected = $derived(items.find((i) => i.value === value) ?? null)
	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase()
		if (!q) return items
		return items.filter(
			(i) =>
				i.label.toLowerCase().includes(q) ||
				(i.sublabel ?? '').toLowerCase().includes(q) ||
				i.value.toLowerCase().includes(q)
		)
	})

	function open() {
		if (isOpen) return
		isOpen = true
		query = ''
		queueMicrotask(() => {
			recomputePlacement()
			searchEl?.focus()
		})
	}

	function close() {
		isOpen = false
	}

	function toggle() {
		if (isOpen) close()
		else open()
	}

	function pick(v: string) {
		onChange(v)
		close()
	}

	function recomputePlacement() {
		if (!triggerEl) return
		const rect = triggerEl.getBoundingClientRect()
		const vh = window.innerHeight
		const margin = 12
		const spaceBelow = vh - rect.bottom - margin
		const spaceAbove = rect.top - margin
		if (spaceBelow < 200 && spaceAbove > spaceBelow) {
			dropUp = true
			menuMaxHeight = Math.max(160, Math.min(360, spaceAbove))
		} else {
			dropUp = false
			menuMaxHeight = Math.max(160, Math.min(360, spaceBelow))
		}
	}

	function handleDocPointer(e: PointerEvent) {
		if (!isOpen) return
		const t = e.target as Node | null
		if (!t) return
		if (triggerEl?.contains(t)) return
		if (menuEl?.contains(t)) return
		close()
	}

	function handleKey(e: KeyboardEvent) {
		if (!isOpen) return
		if (e.key === 'Escape') {
			e.preventDefault()
			close()
			triggerEl?.focus()
		}
	}

	$effect(() => {
		if (!isOpen) return
		const onScroll = () => recomputePlacement()
		const onResize = () => recomputePlacement()
		window.addEventListener('scroll', onScroll, true)
		window.addEventListener('resize', onResize)
		document.addEventListener('pointerdown', handleDocPointer, true)
		document.addEventListener('keydown', handleKey, true)
		return () => {
			window.removeEventListener('scroll', onScroll, true)
			window.removeEventListener('resize', onResize)
			document.removeEventListener('pointerdown', handleDocPointer, true)
			document.removeEventListener('keydown', handleKey, true)
		}
	})
</script>

<div class="relative">
	<button
		type="button"
		bind:this={triggerEl}
		class="flex w-full items-center justify-between gap-2 rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 hover:border-zinc-700 focus:outline-none"
		onclick={toggle}
		aria-haspopup="listbox"
		aria-expanded={isOpen}
	>
		<span class="min-w-0 flex-1 text-left">
			{#if selected}
				<span class="wrap-anywhere text-zinc-100">{selected.label}</span>
				{#if selected.sublabel}
					<span class="ml-2 text-xs wrap-anywhere text-zinc-500">
						{selected.sublabel}
					</span>
				{/if}
			{:else}
				<span class="text-zinc-500">{placeholder}</span>
			{/if}
		</span>
		<ChevronDown class="h-4 w-4 shrink-0 text-zinc-500" />
	</button>

	{#if isOpen}
		<div
			bind:this={menuEl}
			class="absolute right-0 left-0 z-50 flex flex-col rounded-xl border border-zinc-800 bg-zinc-950 shadow-xl"
			class:bottom-full={dropUp}
			class:top-full={!dropUp}
			class:mb-1={dropUp}
			class:mt-1={!dropUp}
			style="max-height: {menuMaxHeight}px;"
			role="listbox"
		>
			<div class="flex items-center gap-2 border-b border-zinc-800 px-3 py-2">
				<Search class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
				<input
					bind:this={searchEl}
					bind:value={query}
					placeholder={searchPlaceholder}
					class="min-w-0 flex-1 bg-transparent text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
				/>
				{#if query}
					<button
						type="button"
						class="text-zinc-500 hover:text-zinc-300"
						onclick={() => (query = '')}
						aria-label="clear search"
					>
						<X class="h-3.5 w-3.5" />
					</button>
				{/if}
			</div>

			<div class="min-h-0 flex-1 overflow-x-hidden overflow-y-auto p-1">
				{#if allowClear}
					<button
						type="button"
						class="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-sm hover:bg-zinc-900 {value ===
						''
							? 'bg-zinc-900 text-zinc-100'
							: 'text-zinc-400'}"
						onclick={() => pick('')}
					>
						<span class="min-w-0 wrap-anywhere">{clearLabel}</span>
					</button>
				{/if}
				{#each filtered as item (item.value)}
					<button
						type="button"
						class="flex w-full min-w-0 flex-col items-start rounded-lg px-2 py-1.5 text-left text-sm hover:bg-zinc-900 {item.value ===
						value
							? 'bg-zinc-900 text-zinc-100'
							: 'text-zinc-200'}"
						onclick={() => pick(item.value)}
					>
						<span class="w-full min-w-0 font-medium wrap-anywhere whitespace-normal">
							{item.label}
						</span>
						{#if item.sublabel}
							<span
								class="w-full min-w-0 text-xs wrap-anywhere whitespace-normal text-zinc-500"
							>
								{item.sublabel}
							</span>
						{/if}
					</button>
				{:else}
					<div class="px-2 py-3 text-center text-xs text-zinc-500">{emptyLabel}</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
