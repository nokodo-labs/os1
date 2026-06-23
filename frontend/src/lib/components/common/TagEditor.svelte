<script lang="ts">
	import XMark from '$lib/components/icons/XMark.svelte'

	interface Props {
		value?: string[]
		disabled?: boolean
		placeholder?: string
		inputId?: string
		class?: string
	}

	let {
		value = $bindable<string[]>([]),
		disabled = false,
		placeholder = 'add tag',
		inputId,
		class: className = '',
	}: Props = $props()

	let draft = $state('')
	let inputEl: HTMLInputElement | null = $state(null)

	function normalizeTags(tags: string[]): string[] {
		const normalized: string[] = []
		for (const tag of tags) {
			const trimmed = tag.trim()
			if (!trimmed || normalized.includes(trimmed)) continue
			normalized.push(trimmed)
		}
		return normalized
	}

	function addText(text: string): void {
		if (disabled) return
		const parts = text
			.split(',')
			.map((part) => part.trim())
			.filter(Boolean)
		if (parts.length === 0) return
		value = normalizeTags([...value, ...parts])
		draft = ''
	}

	function removeTag(tag: string): void {
		if (disabled) return
		value = value.filter((item) => item !== tag)
		inputEl?.focus()
	}

	function handleKeyDown(event: KeyboardEvent): void {
		if (disabled) return
		if (event.key === 'Enter' || event.key === ',') {
			event.preventDefault()
			addText(draft)
			return
		}
		if (event.key === 'Backspace' && draft === '' && value.length > 0) {
			event.preventDefault()
			const next = value.slice(0, -1)
			draft = value[value.length - 1] ?? ''
			value = next
		}
	}

	function handlePaste(event: ClipboardEvent): void {
		if (disabled) return
		const text = event.clipboardData?.getData('text') ?? ''
		if (!text.includes(',')) return
		event.preventDefault()
		addText(text)
	}

	function handleBlur(): void {
		addText(draft)
	}
</script>

<div
	class="border-foreground/12 bg-foreground/4 focus-within:bg-foreground/6 col-span-full flex min-h-10 min-w-0 flex-wrap items-center gap-2 rounded-xl border px-2 py-2 transition-colors duration-150 focus-within:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] {className}"
>
	{#each value as tag (tag)}
		<button
			type="button"
			class="rounded-pill border-foreground/10 bg-foreground/8 text-foreground/82 hover:bg-foreground/12 inline-flex min-h-7 cursor-pointer items-center gap-1.5 border px-2.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-55"
			{disabled}
			onclick={() => removeTag(tag)}
			aria-label={`remove ${tag}`}
		>
			<span class="max-w-36 truncate">{tag}</span>
			<XMark class="h-3.5 w-3.5" />
		</button>
	{/each}
	<input
		id={inputId}
		bind:this={inputEl}
		bind:value={draft}
		type="text"
		class="placeholder:text-foreground/35 text-foreground/90 min-h-7 min-w-24 flex-1 border-none bg-transparent px-1 text-sm outline-none disabled:cursor-not-allowed disabled:opacity-55"
		{placeholder}
		{disabled}
		onkeydown={handleKeyDown}
		onpaste={handlePaste}
		onblur={handleBlur}
	/>
</div>
