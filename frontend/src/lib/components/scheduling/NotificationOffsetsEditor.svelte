<script lang="ts">
	import Bell from '$lib/components/icons/Bell.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import {
		NOTIFICATION_OFFSET_PRESETS,
		describeNotificationOffset,
		describeNotificationOffsets,
		normalizeNotificationOffsets,
		offsetToMinutes,
		type NotificationOffsetUnit,
	} from '$lib/utils/recurrence'

	interface Props {
		value?: number[]
		disabled?: boolean
		onChange: (value: number[]) => void
	}

	let { value = [], disabled = false, onChange }: Props = $props()

	let customAmount = $state(15)
	let customUnit = $state<NotificationOffsetUnit>('minutes')
	let customOpen = $state(false)

	const normalizedOffsets = $derived(normalizeNotificationOffsets(value))
	const customOffsets = $derived(
		normalizedOffsets.filter(
			(offset) => !NOTIFICATION_OFFSET_PRESETS.some((preset) => preset.value === offset)
		)
	)
	const showCustom = $derived(customOpen || customOffsets.length > 0)
	const summary = $derived(describeNotificationOffsets(normalizedOffsets))

	function commit(next: number[]): void {
		if (disabled) return
		onChange(normalizeNotificationOffsets(next))
	}

	function togglePreset(offset: number): void {
		if (normalizedOffsets.includes(offset)) {
			commit(normalizedOffsets.filter((item) => item !== offset))
			return
		}
		commit([...normalizedOffsets, offset])
	}

	function removeOffset(offset: number): void {
		commit(normalizedOffsets.filter((item) => item !== offset))
	}

	function addCustom(): void {
		const minutes = offsetToMinutes(customAmount, customUnit)
		customOpen = true
		commit([...normalizedOffsets, minutes])
	}

	function toggleCustom(): void {
		if (disabled) return
		customOpen = !customOpen
	}

	function normalizeAmount(): void {
		customAmount = Math.max(1, Math.min(9999, Math.trunc(Number(customAmount) || 1)))
	}

	const chipBaseClass =
		'rounded-pill inline-flex min-h-8 cursor-pointer items-center justify-center gap-1.5 border px-3 text-[0.78rem] font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const activeChipClass =
		'border-[color-mix(in_oklch,var(--accent-primary)_36%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_20%,transparent)] text-foreground'
	const quietChipClass =
		'border-foreground/10 bg-foreground/5 text-foreground/70 hover:bg-foreground/8 hover:text-foreground'
	const inputClass =
		'border-foreground/12 bg-foreground/5 text-foreground/90 min-h-9 min-w-0 rounded-xl border px-3 py-2 text-sm outline-none transition-colors focus:border-[color-mix(in_oklch,var(--accent-primary)_44%,transparent)] disabled:cursor-not-allowed disabled:opacity-55'
</script>

<div class="flex min-w-0 flex-col gap-3">
	<div class="flex min-w-0 items-start gap-3">
		<div
			class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
		>
			<Bell class="h-4 w-4" />
		</div>
		<div class="min-w-0 flex-1">
			<div class="text-foreground/50 text-xs font-semibold">notify</div>
			<div class="text-foreground/82 mt-0.5 min-w-0 text-sm leading-5">{summary}</div>
		</div>
	</div>

	<div class="flex flex-wrap gap-2">
		{#each NOTIFICATION_OFFSET_PRESETS as preset (preset.value)}
			<button
				type="button"
				class="{chipBaseClass} {normalizedOffsets.includes(preset.value)
					? activeChipClass
					: quietChipClass}"
				{disabled}
				onclick={() => togglePreset(preset.value)}
			>
				{#if normalizedOffsets.includes(preset.value)}
					<Check class="h-3.5 w-3.5" />
				{:else}
					<Bell class="h-3.5 w-3.5" />
				{/if}
				<span>{preset.label}</span>
			</button>
		{/each}
		<button
			type="button"
			class="{chipBaseClass} {showCustom ? activeChipClass : quietChipClass}"
			{disabled}
			onclick={toggleCustom}
		>
			<Plus class="h-3.5 w-3.5" />
			<span>custom</span>
		</button>
	</div>

	{#if showCustom}
		<div class="border-foreground/10 bg-foreground/4 grid gap-3 rounded-[14px] border p-3">
			<div
				class="grid grid-cols-[minmax(4rem,6rem)_minmax(0,1fr)_auto] gap-2 max-[520px]:grid-cols-1"
			>
				<input
					type="number"
					min="1"
					max="9999"
					bind:value={customAmount}
					class={inputClass}
					{disabled}
					onblur={normalizeAmount}
					aria-label="custom notification amount"
				/>
				<select
					bind:value={customUnit}
					class={inputClass}
					{disabled}
					aria-label="custom notification unit"
				>
					<option value="minutes">minutes before</option>
					<option value="hours">hours before</option>
					<option value="days">days before</option>
					<option value="weeks">weeks before</option>
					<option value="months">months before</option>
				</select>
				<button
					type="button"
					class="{chipBaseClass} {quietChipClass}"
					disabled={disabled || normalizedOffsets.length >= 8}
					onclick={addCustom}
				>
					<Plus class="h-3.5 w-3.5" />
					<span>add</span>
				</button>
			</div>

			{#if customOffsets.length > 0}
				<div class="flex flex-wrap gap-2">
					{#each customOffsets as offset (offset)}
						<button
							type="button"
							class="{chipBaseClass} {activeChipClass}"
							{disabled}
							onclick={() => removeOffset(offset)}
							aria-label={`remove ${describeNotificationOffset(offset)} notification`}
						>
							<span>{describeNotificationOffset(offset)}</span>
							<XMark class="h-3.5 w-3.5" />
						</button>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>
