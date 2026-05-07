<script lang="ts">
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'

	type BackfillFrequency = 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom'
	type ParsedSchedule = {
		frequency: Exclude<BackfillFrequency, 'custom'>
		minute: string
		time: string
		weekday: string
		monthDay: string
	}

	const weekdays = [
		{ value: '1', label: 'monday' },
		{ value: '2', label: 'tuesday' },
		{ value: '3', label: 'wednesday' },
		{ value: '4', label: 'thursday' },
		{ value: '5', label: 'friday' },
		{ value: '6', label: 'saturday' },
		{ value: '0', label: 'sunday' },
	]

	type Props = {
		backfillEnabled?: boolean
		backfillCron?: string
		backfillBatchSize?: string
		backfillMaxLookbackDays?: string
		backfillMinInactivityHours?: string
	}

	let {
		backfillEnabled = $bindable(false),
		backfillCron = $bindable(''),
		backfillBatchSize = $bindable(''),
		backfillMaxLookbackDays = $bindable(''),
		backfillMinInactivityHours = $bindable(''),
	}: Props = $props()

	let backfillFrequency = $state<BackfillFrequency>('daily')
	let backfillTime = $state('04:00')
	let backfillMinute = $state('0')
	let backfillWeekday = $state('1')
	let backfillMonthDay = $state('1')
	let lastAppliedCron = $state<string | null>(null)

	function isIntInRange(value: string, min: number, max: number): boolean {
		if (!/^\d+$/.test(value)) return false
		const n = Number(value)
		return n >= min && n <= max
	}

	function isBackfillFrequency(value: string): value is BackfillFrequency {
		return (
			value === 'hourly' ||
			value === 'daily' ||
			value === 'weekly' ||
			value === 'monthly' ||
			value === 'custom'
		)
	}

	function frequencyLabel(value: BackfillFrequency): string {
		if (value === 'hourly') return 'hourly'
		if (value === 'daily') return 'daily'
		if (value === 'weekly') return 'weekly'
		if (value === 'monthly') return 'monthly'
		return 'custom'
	}

	function timeFromParts(hour: string, minute: string): string | null {
		if (!isIntInRange(hour, 0, 23) || !isIntInRange(minute, 0, 59)) return null
		return `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
	}

	function parseCron(cron: string): ParsedSchedule | null {
		const parts = cron.trim().split(/\s+/)
		if (parts.length !== 5) return null
		const [minute, hour, monthDay, month, weekday] = parts
		if (month !== '*') return null
		if (hour === '*' && monthDay === '*' && weekday === '*' && isIntInRange(minute, 0, 59)) {
			return { frequency: 'hourly', minute, time: '04:00', weekday: '1', monthDay: '1' }
		}
		const time = timeFromParts(hour, minute)
		if (!time) return null
		if (monthDay === '*' && weekday === '*') {
			return { frequency: 'daily', minute, time, weekday: '1', monthDay: '1' }
		}
		if (monthDay === '*' && isIntInRange(weekday, 0, 6)) {
			return { frequency: 'weekly', minute, time, weekday, monthDay: '1' }
		}
		if (weekday === '*' && isIntInRange(monthDay, 1, 28)) {
			return { frequency: 'monthly', minute, time, weekday: '1', monthDay }
		}
		return null
	}

	function cronFromControls(): string | null {
		if (backfillFrequency === 'custom') return null
		if (backfillFrequency === 'hourly') {
			if (!isIntInRange(backfillMinute, 0, 59)) return null
			return `${Number(backfillMinute)} * * * *`
		}
		const [hour, minute] = backfillTime.split(':')
		if (!timeFromParts(hour ?? '', minute ?? '')) return null
		const normalizedMinute = String(Number(minute))
		const normalizedHour = String(Number(hour))
		if (backfillFrequency === 'daily') return `${normalizedMinute} ${normalizedHour} * * *`
		if (backfillFrequency === 'weekly') {
			if (!isIntInRange(backfillWeekday, 0, 6)) return null
			return `${normalizedMinute} ${normalizedHour} * * ${backfillWeekday}`
		}
		if (!isIntInRange(backfillMonthDay, 1, 28)) return null
		return `${normalizedMinute} ${normalizedHour} ${backfillMonthDay} * *`
	}

	function applyParsedSchedule(parsed: ParsedSchedule | null, cron: string) {
		if (!parsed) {
			backfillFrequency = cron.trim() ? 'custom' : 'daily'
			lastAppliedCron = cron
			return
		}
		backfillFrequency = parsed.frequency
		backfillTime = parsed.time
		backfillMinute = parsed.minute
		backfillWeekday = parsed.weekday
		backfillMonthDay = parsed.monthDay
		lastAppliedCron = cron
	}

	function updateCronFromControls() {
		const cron = cronFromControls()
		if (!cron) return
		backfillCron = cron
		lastAppliedCron = cron
	}

	function setBackfillFrequency(value: string) {
		if (!isBackfillFrequency(value)) return
		backfillFrequency = value
		updateCronFromControls()
	}

	function setBackfillTime(value: string) {
		backfillTime = value
		updateCronFromControls()
	}

	function setBackfillMinute(value: string) {
		backfillMinute = value
		updateCronFromControls()
	}

	function setBackfillWeekday(value: string) {
		backfillWeekday = value
		updateCronFromControls()
	}

	function setBackfillMonthDay(value: string) {
		backfillMonthDay = value
		updateCronFromControls()
	}

	$effect(() => {
		if (backfillCron === lastAppliedCron) return
		applyParsedSchedule(parseCron(backfillCron), backfillCron)
	})
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>tasks</CardTitle>
		<CardDescription>background task scheduling and maintenance controls.</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		<div
			class="flex items-center justify-between gap-4 rounded-xl border border-zinc-800 bg-zinc-950 p-4"
		>
			<div class="space-y-1">
				<Label for="maintenance_backfill_enabled">thread maintenance backfill</Label>
				<p class="text-xs text-zinc-500">
					enable a scheduled sweep for old inactive threads with incomplete metadata or
					summaries.
				</p>
			</div>
			<Switch
				id="maintenance_backfill_enabled"
				checked={backfillEnabled}
				onCheckedChange={(value: boolean) => (backfillEnabled = value)}
			/>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="maintenance_backfill_frequency">schedule</Label>
				<p class="text-xs text-zinc-500">UTC cadence for the scheduled sweep.</p>
				<Select value={backfillFrequency} onValueChange={setBackfillFrequency}>
					<SelectTrigger id="maintenance_backfill_frequency" class="rounded-xl">
						{frequencyLabel(backfillFrequency)}
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="hourly">hourly</SelectItem>
						<SelectItem value="daily">daily</SelectItem>
						<SelectItem value="weekly">weekly</SelectItem>
						<SelectItem value="monthly">monthly</SelectItem>
						{#if backfillFrequency === 'custom'}
							<SelectItem value="custom">custom</SelectItem>
						{/if}
					</SelectContent>
				</Select>
			</div>
			{#if backfillFrequency === 'hourly'}
				<div class="space-y-2">
					<Label for="maintenance_backfill_minute">minute</Label>
					<p class="text-xs text-zinc-500">minute after each hour, in UTC.</p>
					<Input
						id="maintenance_backfill_minute"
						type="number"
						min="0"
						max="59"
						value={backfillMinute}
						oninput={(event) => setBackfillMinute(event.currentTarget.value)}
						class="rounded-xl"
					/>
				</div>
			{:else if backfillFrequency === 'custom'}
				<div class="space-y-2 rounded-xl border border-zinc-800 bg-zinc-950 p-3">
					<Label>custom schedule</Label>
					<p class="text-xs text-zinc-500">
						this schedule was configured outside the console. choose a cadence to
						replace it.
					</p>
				</div>
			{:else}
				<div class="space-y-2">
					<Label for="maintenance_backfill_time">time</Label>
					<p class="text-xs text-zinc-500">time of day in UTC.</p>
					<Input
						id="maintenance_backfill_time"
						type="time"
						step="60"
						value={backfillTime}
						oninput={(event) => setBackfillTime(event.currentTarget.value)}
						class="rounded-xl"
					/>
				</div>
			{/if}
			{#if backfillFrequency === 'weekly'}
				<div class="space-y-2">
					<Label for="maintenance_backfill_weekday">day</Label>
					<p class="text-xs text-zinc-500">day of week in UTC.</p>
					<Select value={backfillWeekday} onValueChange={setBackfillWeekday}>
						<SelectTrigger id="maintenance_backfill_weekday" class="rounded-xl">
							{weekdays.find((weekday) => weekday.value === backfillWeekday)?.label ??
								'monday'}
						</SelectTrigger>
						<SelectContent>
							{#each weekdays as weekday (weekday.value)}
								<SelectItem value={weekday.value}>{weekday.label}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
			{:else if backfillFrequency === 'monthly'}
				<div class="space-y-2">
					<Label for="maintenance_backfill_month_day">day</Label>
					<p class="text-xs text-zinc-500">day of month, capped at 28 for safety.</p>
					<Input
						id="maintenance_backfill_month_day"
						type="number"
						min="1"
						max="28"
						value={backfillMonthDay}
						oninput={(event) => setBackfillMonthDay(event.currentTarget.value)}
						class="rounded-xl"
					/>
				</div>
			{/if}
			<div class="space-y-2">
				<Label for="maintenance_backfill_batch">batch size</Label>
				<p class="text-xs text-zinc-500">maximum thread maintenance tasks per sweep.</p>
				<Input
					id="maintenance_backfill_batch"
					type="number"
					min="1"
					bind:value={backfillBatchSize}
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="maintenance_backfill_lookback">max lookback days</Label>
				<p class="text-xs text-zinc-500">ignore threads older than this window.</p>
				<Input
					id="maintenance_backfill_lookback"
					type="number"
					min="1"
					bind:value={backfillMaxLookbackDays}
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="maintenance_backfill_inactivity">min inactivity hours</Label>
				<p class="text-xs text-zinc-500">minimum idle time before a thread is eligible.</p>
				<Input
					id="maintenance_backfill_inactivity"
					type="number"
					min="1"
					bind:value={backfillMinInactivityHours}
					class="rounded-xl"
				/>
			</div>
		</div>
	</CardContent>
</Card>
