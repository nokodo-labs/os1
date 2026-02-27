<script lang="ts">
	import Tooltip from '$lib/components/Tooltip.svelte'

	interface SwitchProps {
		checked?: boolean
		id?: string
		ariaLabelledbyId?: string
		tooltip?: boolean | string
		disabled?: boolean
		onchange?: (checked: boolean) => void
	}

	let {
		checked = $bindable(true),
		id = '',
		ariaLabelledbyId = '',
		tooltip = false,
		disabled = false,
		onchange,
	}: SwitchProps = $props()

	function handleToggle() {
		if (disabled) return
		checked = !checked
		onchange?.(checked)
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === ' ' || event.key === 'Enter') {
			event.preventDefault()
			handleToggle()
		}
	}

	const tooltipContent = $derived(
		typeof tooltip === 'string'
			? tooltip
			: tooltip === true
				? checked
					? 'enabled'
					: 'disabled'
				: ''
	)
</script>

<Tooltip content={tooltipContent} placement="top">
	<button
		type="button"
		role="switch"
		aria-checked={checked}
		aria-labelledby={ariaLabelledbyId || undefined}
		{id}
		{disabled}
		onclick={handleToggle}
		onkeydown={handleKeydown}
		class="mx-px flex h-4.5 min-h-4.5 w-8 shrink-0 cursor-pointer items-center rounded-full px-0.5 outline-1 outline-white/15
			transition-colors duration-200
			{checked ? 'bg-(--accent-primary)' : 'bg-foreground/10'}
			{disabled ? 'cursor-not-allowed opacity-40' : ''}"
	>
		<span
			class="bg-background pointer-events-none block size-3.5 shrink-0 rounded-full shadow-sm transition-transform duration-200
				{checked ? 'translate-x-3.5' : 'translate-x-0'}"
		></span>
	</button>
</Tooltip>
