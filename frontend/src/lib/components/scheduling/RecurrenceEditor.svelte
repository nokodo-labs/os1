<script lang="ts">
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import ClockRotateRight from '$lib/components/icons/ClockRotateRight.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { DropdownSelect } from '$lib/components/primitives'
	import {
		FREQUENCY_OPTIONS,
		MONTH_OPTIONS,
		WEEKDAY_OPTIONS,
		buildRecurrence,
		describeRecurrence,
		formatNumberList,
		getQuickRecurrencePresets,
		parseNumberList,
		parseRRule,
		recurrenceFromRule,
		type Recurrence,
		type RecurrenceEndMode,
		type RecurrenceFrequency,
		type WeekdayCode,
	} from '$lib/utils/recurrence'

	interface Props {
		value?: Recurrence | null
		anchorDate?: string | Date | null
		timezone?: string | null
		disabled?: boolean
		onChange: (value: Recurrence | null) => void
	}

	let {
		value = null,
		anchorDate = null,
		timezone = null,
		disabled = false,
		onChange,
	}: Props = $props()

	let enabled = $state(false)
	let frequency = $state<RecurrenceFrequency>('DAILY')
	let interval = $state(1)
	let byDays = $state<WeekdayCode[]>([])
	let monthDaysInput = $state('')
	let selectedMonths = $state<number[]>([])
	let hoursInput = $state('')
	let minutesInput = $state('')
	let endMode = $state<RecurrenceEndMode>('never')
	let untilDate = $state('')
	let count = $state(10)
	let customOpen = $state(false)
	let previousValueKey = $state('')
	const endModeOptions = [
		{ value: 'never', label: 'never' },
		{ value: 'on', label: 'on date' },
		{ value: 'after', label: 'after occurrences' },
	]

	const quickPresets = $derived(getQuickRecurrencePresets(anchorDate))
	const currentRule = $derived(value?.rrule?.[0]?.trim() ?? '')
	const customRuleActive = $derived(Boolean(currentRule) && !isQuickPresetRule(currentRule))
	const showCustom = $derived(customOpen || customRuleActive)
	const previewRecurrence = $derived.by(() => {
		if (!enabled) return null
		return buildCurrentRecurrence()
	})
	const previewLabel = $derived(describeRecurrence(previewRecurrence, anchorDate))

	$effect(() => {
		const key = `${value?.rrule?.[0] ?? ''}|${value?.timezone ?? ''}`
		if (key === previousValueKey) return
		previousValueKey = key
		hydrate(value)
	})

	function hydrate(next: Recurrence | null | undefined): void {
		const rule = next?.rrule?.[0]?.trim()
		if (!rule) {
			enabled = false
			frequency = 'DAILY'
			interval = 1
			byDays = []
			monthDaysInput = ''
			selectedMonths = []
			hoursInput = ''
			minutesInput = ''
			endMode = 'never'
			untilDate = ''
			count = 10
			customOpen = false
			return
		}

		const parsed = parseRRule(rule)
		enabled = true
		frequency = parsed.frequency
		interval = parsed.interval
		byDays = parsed.byDays
		monthDaysInput = formatNumberList(parsed.byMonthDays)
		selectedMonths = parsed.byMonths
		hoursInput = formatNumberList(parsed.byHours)
		minutesInput = formatNumberList(parsed.byMinutes)
		endMode = parsed.endMode
		untilDate = parsed.untilDate
		count = parsed.count
		customOpen = !isQuickPresetRule(rule)
	}

	function isQuickPresetRule(rule: string): boolean {
		return quickPresets.some((preset) => preset.rrule === rule)
	}

	function buildCurrentRecurrence(): Recurrence | null {
		return buildRecurrence({
			frequency,
			interval,
			byDays,
			byMonthDays: parseNumberList(monthDaysInput, 1, 31),
			byMonths: selectedMonths,
			byHours: parseNumberList(hoursInput, 0, 23),
			byMinutes: parseNumberList(minutesInput, 0, 59),
			endMode,
			untilDate,
			count,
			timezone,
		})
	}

	function commitCurrent(): void {
		if (disabled) return
		if (!enabled) {
			onChange(null)
			return
		}
		onChange(buildCurrentRecurrence())
	}

	function setNoRepeat(): void {
		if (disabled) return
		enabled = false
		customOpen = false
		onChange(null)
	}

	function applyQuick(rule: string): void {
		if (disabled) return
		const next = recurrenceFromRule(rule, timezone)
		customOpen = false
		hydrate(next)
		onChange(next)
	}

	function toggleCustom(): void {
		if (disabled) return
		customOpen = !customOpen
	}

	function toggleWeekday(day: WeekdayCode): void {
		if (disabled) return
		enabled = true
		customOpen = true
		byDays = byDays.includes(day) ? byDays.filter((item) => item !== day) : [...byDays, day]
		commitCurrent()
	}

	function toggleMonth(month: number): void {
		if (disabled) return
		enabled = true
		customOpen = true
		selectedMonths = selectedMonths.includes(month)
			? selectedMonths.filter((item) => item !== month)
			: [...selectedMonths, month].toSorted((a, b) => a - b)
		commitCurrent()
	}

	function setFrequency(value: RecurrenceFrequency): void {
		if (disabled) return
		enabled = true
		customOpen = true
		frequency = value
		commitCurrent()
	}

	function setEndMode(value: RecurrenceEndMode): void {
		if (disabled) return
		enabled = true
		customOpen = true
		endMode = value
		commitCurrent()
	}

	function normalizeInterval(): void {
		interval = Math.max(1, Math.min(999, Math.trunc(Number(interval) || 1)))
	}

	function normalizeCount(): void {
		count = Math.max(1, Math.min(9999, Math.trunc(Number(count) || 1)))
	}

	const chipBaseClass =
		'rounded-pill inline-flex min-h-8 cursor-pointer items-center justify-center gap-1.5 border px-3 text-[0.78rem] font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const activeChipClass =
		'border-[color-mix(in_oklch,var(--accent-primary)_36%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_20%,transparent)] text-foreground'
	const quietChipClass =
		'border-foreground/10 bg-foreground/5 text-foreground/70 hover:bg-foreground/8 hover:text-foreground'
	const inputClass =
		'border-foreground/12 bg-foreground/5 text-foreground/90 placeholder:text-foreground/35 min-h-9 min-w-0 rounded-xl border px-3 py-2 text-sm outline-none transition-colors focus:border-[color-mix(in_oklch,var(--accent-primary)_44%,transparent)] disabled:cursor-not-allowed disabled:opacity-55'
</script>

<div class="flex min-w-0 flex-col gap-3">
	<div class="flex min-w-0 items-start gap-3">
		<div
			class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
		>
			<ArrowPath class="h-4 w-4" />
		</div>
		<div class="min-w-0 flex-1">
			<div class="text-foreground/50 text-xs font-semibold">repeat</div>
			<div class="text-foreground/82 mt-0.5 min-w-0 text-sm leading-5">{previewLabel}</div>
		</div>
	</div>

	<div class="flex flex-wrap gap-2">
		<button
			type="button"
			class="{chipBaseClass} {!enabled ? activeChipClass : quietChipClass}"
			{disabled}
			onclick={setNoRepeat}
		>
			<XMark class="h-3.5 w-3.5" />
			<span>no repeat</span>
		</button>
		{#each quickPresets as preset (preset.id)}
			<button
				type="button"
				class="{chipBaseClass} {value?.rrule?.[0] === preset.rrule
					? activeChipClass
					: quietChipClass}"
				{disabled}
				onclick={() => applyQuick(preset.rrule)}
			>
				<ClockRotateRight class="h-3.5 w-3.5" />
				<span>{preset.label}</span>
			</button>
		{/each}
		<button
			type="button"
			class="{chipBaseClass} {showCustom ? activeChipClass : quietChipClass}"
			{disabled}
			onclick={toggleCustom}
		>
			<Calendar class="h-3.5 w-3.5" />
			<span>custom</span>
		</button>
	</div>

	{#if showCustom}
		<div class="border-foreground/10 bg-foreground/4 grid gap-3 rounded-[14px] border p-3">
			<div class="grid grid-cols-[minmax(4.5rem,6rem)_minmax(0,1fr)] items-center gap-2">
				<label class="text-foreground/55 text-xs font-semibold" for="recurrence-interval">
					every
				</label>
				<div class="grid min-w-0 grid-cols-[minmax(4rem,5rem)_minmax(0,1fr)] gap-2">
					<input
						id="recurrence-interval"
						type="number"
						min="1"
						max="999"
						bind:value={interval}
						class={inputClass}
						{disabled}
						oninput={() => {
							enabled = true
							customOpen = true
							commitCurrent()
						}}
						onblur={() => {
							normalizeInterval()
							commitCurrent()
						}}
					/>
					<DropdownSelect
						options={FREQUENCY_OPTIONS}
						value={frequency}
						onchange={(value) => setFrequency(value as RecurrenceFrequency)}
						{disabled}
						ariaLabel="recurrence frequency"
						buttonClass="rounded-xl px-3"
					/>
				</div>
			</div>

			<div class="grid gap-2">
				<div class="text-foreground/55 flex items-center gap-2 text-xs font-semibold">
					<Calendar class="h-3.5 w-3.5" />
					<span>only on days</span>
				</div>
				<div class="grid grid-cols-7 gap-1">
					{#each WEEKDAY_OPTIONS as day (day.value)}
						<button
							type="button"
							class="rounded-lg px-1.5 py-1.5 text-xs font-semibold transition-colors {byDays.includes(
								day.value
							)
								? activeChipClass
								: quietChipClass}"
							{disabled}
							onclick={() => toggleWeekday(day.value)}
						>
							{day.shortLabel}
						</button>
					{/each}
				</div>
			</div>

			<div class="grid gap-2 sm:grid-cols-2">
				<label
					class="text-foreground/55 grid gap-1 text-xs font-semibold"
					for="recurrence-month-days"
				>
					<span>days of month</span>
					<input
						id="recurrence-month-days"
						type="text"
						bind:value={monthDaysInput}
						class={inputClass}
						placeholder="1, 15, 28"
						{disabled}
						oninput={() => {
							enabled = true
							customOpen = true
							commitCurrent()
						}}
					/>
				</label>
				<label
					class="text-foreground/55 grid gap-1 text-xs font-semibold"
					for="recurrence-hours"
				>
					<span>hours of day</span>
					<input
						id="recurrence-hours"
						type="text"
						bind:value={hoursInput}
						class={inputClass}
						placeholder="9, 13, 17"
						{disabled}
						oninput={() => {
							enabled = true
							customOpen = true
							commitCurrent()
						}}
					/>
				</label>
			</div>

			<div class="grid gap-2">
				<label
					class="text-foreground/55 grid gap-1 text-xs font-semibold"
					for="recurrence-minutes"
				>
					<span>minutes of hour</span>
					<input
						id="recurrence-minutes"
						type="text"
						bind:value={minutesInput}
						class={inputClass}
						placeholder="0, 30"
						{disabled}
						oninput={() => {
							enabled = true
							customOpen = true
							commitCurrent()
						}}
					/>
				</label>
			</div>

			<div class="grid gap-2">
				<div class="text-foreground/55 text-xs font-semibold">months of year</div>
				<div class="grid grid-cols-4 gap-1">
					{#each MONTH_OPTIONS as month (month.value)}
						<button
							type="button"
							class="rounded-lg px-1.5 py-1.5 text-xs font-semibold transition-colors {selectedMonths.includes(
								month.value
							)
								? activeChipClass
								: quietChipClass}"
							{disabled}
							onclick={() => toggleMonth(month.value)}
						>
							{month.shortLabel}
						</button>
					{/each}
				</div>
			</div>

			<div class="grid gap-2">
				<label class="text-foreground/55 text-xs font-semibold" for="recurrence-end-mode">
					ends
				</label>
				<div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
					<DropdownSelect
						options={endModeOptions}
						value={endMode}
						onchange={(value) => setEndMode(value as RecurrenceEndMode)}
						{disabled}
						ariaLabel="recurrence end"
						buttonClass="rounded-xl px-3"
					/>
					{#if endMode === 'on'}
						<input
							type="date"
							bind:value={untilDate}
							class={inputClass}
							{disabled}
							oninput={() => {
								enabled = true
								customOpen = true
								commitCurrent()
							}}
						/>
					{:else if endMode === 'after'}
						<input
							type="number"
							min="1"
							max="9999"
							bind:value={count}
							class={inputClass}
							{disabled}
							oninput={() => {
								enabled = true
								customOpen = true
								commitCurrent()
							}}
							onblur={() => {
								normalizeCount()
								commitCurrent()
							}}
						/>
					{:else}
						<div
							class="border-foreground/8 bg-foreground/4 text-foreground/45 min-h-9 rounded-xl border px-3 py-2 text-sm"
						>
							open ended
						</div>
					{/if}
				</div>
			</div>

			<button
				type="button"
				class="{chipBaseClass} {enabled
					? activeChipClass
					: quietChipClass} justify-self-start"
				{disabled}
				onclick={() => {
					enabled = true
					customOpen = true
					commitCurrent()
				}}
			>
				<Check class="h-3.5 w-3.5" />
				<span>apply custom</span>
			</button>
		</div>
	{/if}
</div>
