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
	import { Lock } from '@lucide/svelte'

	type BackfillFrequency =
		| 'hourly'
		| 'daily'
		| 'weekdays'
		| 'weekly'
		| 'monthly'
		| 'yearly'
		| 'custom'
	type ParsedSchedule = {
		frequency: Exclude<BackfillFrequency, 'custom'>
		minute: string
		time: string
		weekday: string
		monthDay: string
		month: string
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

	const months = [
		{ value: '1', label: 'january' },
		{ value: '2', label: 'february' },
		{ value: '3', label: 'march' },
		{ value: '4', label: 'april' },
		{ value: '5', label: 'may' },
		{ value: '6', label: 'june' },
		{ value: '7', label: 'july' },
		{ value: '8', label: 'august' },
		{ value: '9', label: 'september' },
		{ value: '10', label: 'october' },
		{ value: '11', label: 'november' },
		{ value: '12', label: 'december' },
	]

	type Props = {
		taskiqQueueName?: string
		taskiqResultTtlSeconds?: string
		taskiqMaxConnections?: string
		taskiqAutoWorkersMax?: string
		taskiqSchedulePrefix?: string
		maintenanceInactivityHours?: string
		maintenanceQueuedSupersedeAfterMinutes?: string
		maintenanceActiveSupersedeAfterMinutes?: string
		maintenanceRunnerTimeoutSeconds?: string
		maintenanceStaleTaskCleanupAfterMinutes?: string
		backfillEnabled?: boolean
		backfillCron?: string
		backfillBatchSize?: string
		backfillMaxLookbackDays?: string
		backfillMinInactivityHours?: string
	}

	let {
		taskiqQueueName = '',
		taskiqResultTtlSeconds = '',
		taskiqMaxConnections = '',
		taskiqAutoWorkersMax = '',
		taskiqSchedulePrefix = '',
		maintenanceInactivityHours = $bindable(''),
		maintenanceQueuedSupersedeAfterMinutes = $bindable(''),
		maintenanceActiveSupersedeAfterMinutes = $bindable(''),
		maintenanceRunnerTimeoutSeconds = $bindable(''),
		maintenanceStaleTaskCleanupAfterMinutes = $bindable(''),
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
	let backfillMonth = $state('1')
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
			value === 'weekdays' ||
			value === 'weekly' ||
			value === 'monthly' ||
			value === 'yearly' ||
			value === 'custom'
		)
	}

	function frequencyLabel(value: BackfillFrequency): string {
		if (value === 'hourly') return 'hourly'
		if (value === 'daily') return 'daily'
		if (value === 'weekdays') return 'business days'
		if (value === 'weekly') return 'weekly'
		if (value === 'monthly') return 'monthly'
		if (value === 'yearly') return 'annually'
		return 'custom'
	}

	function displayValue(value: string, suffix = ''): string {
		const trimmed = value.trim()
		if (!trimmed) return 'not set'
		if (!suffix) return trimmed
		return `${trimmed} ${suffix}`
	}

	function rawValue(value: string, fallback = '(not set)'): string {
		return value.trim() || fallback
	}

	function timeFromParts(hour: string, minute: string): string | null {
		if (!isIntInRange(hour, 0, 23) || !isIntInRange(minute, 0, 59)) return null
		return `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
	}

	function parseCron(cron: string): ParsedSchedule | null {
		const parts = cron.trim().split(/\s+/)
		if (parts.length !== 5) return null
		const [minute, hour, monthDay, month, weekday] = parts
		if (hour === '*' && monthDay === '*' && weekday === '*' && isIntInRange(minute, 0, 59)) {
			return {
				frequency: 'hourly',
				minute,
				time: '04:00',
				weekday: '1',
				monthDay: '1',
				month: '1',
			}
		}
		const time = timeFromParts(hour, minute)
		if (!time) return null
		if (month === '*' && monthDay === '*' && weekday === '*') {
			return { frequency: 'daily', minute, time, weekday: '1', monthDay: '1', month: '1' }
		}
		if (month === '*' && monthDay === '*' && weekday === '1-5') {
			return {
				frequency: 'weekdays',
				minute,
				time,
				weekday: '1',
				monthDay: '1',
				month: '1',
			}
		}
		if (month === '*' && monthDay === '*' && isIntInRange(weekday, 0, 6)) {
			return { frequency: 'weekly', minute, time, weekday, monthDay: '1', month: '1' }
		}
		if (month === '*' && weekday === '*' && isIntInRange(monthDay, 1, 28)) {
			return { frequency: 'monthly', minute, time, weekday: '1', monthDay, month: '1' }
		}
		if (weekday === '*' && isIntInRange(monthDay, 1, 28) && isIntInRange(month, 1, 12)) {
			return { frequency: 'yearly', minute, time, weekday: '1', monthDay, month }
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
		if (backfillFrequency === 'weekdays') return `${normalizedMinute} ${normalizedHour} * * 1-5`
		if (backfillFrequency === 'weekly') {
			if (!isIntInRange(backfillWeekday, 0, 6)) return null
			return `${normalizedMinute} ${normalizedHour} * * ${backfillWeekday}`
		}
		if (backfillFrequency === 'monthly') {
			if (!isIntInRange(backfillMonthDay, 1, 28)) return null
			return `${normalizedMinute} ${normalizedHour} ${backfillMonthDay} * *`
		}
		if (!isIntInRange(backfillMonthDay, 1, 28) || !isIntInRange(backfillMonth, 1, 12)) {
			return null
		}
		return `${normalizedMinute} ${normalizedHour} ${backfillMonthDay} ${backfillMonth} *`
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
		backfillMonth = parsed.month
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

	function setBackfillMonth(value: string) {
		backfillMonth = value
		updateCronFromControls()
	}

	function setBackfillCustomCron(value: string) {
		backfillCron = value
		lastAppliedCron = value
	}

	$effect(() => {
		if (backfillCron === lastAppliedCron) return
		applyParsedSchedule(parseCron(backfillCron), backfillCron)
	})
</script>

<div class="space-y-6">
	<Card class="border-zinc-800 bg-zinc-900">
		<CardHeader>
			<CardTitle>TaskIQ</CardTitle>
			<CardDescription>queue and dynamic schedule topology.</CardDescription>
		</CardHeader>
		<CardContent class="space-y-5">
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<div class="flex items-center justify-between gap-2">
						<Label for="taskiq_queue_name">queue name</Label>
						<span
							class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
						>
							<Lock class="h-3 w-3" />
							env-only
						</span>
					</div>
					<Input
						id="taskiq_queue_name"
						value={rawValue(taskiqQueueName)}
						disabled
						class="rounded-xl font-mono"
					/>
					<p class="text-xs text-zinc-500">API, workers, and scheduler must agree.</p>
				</div>
				<div class="space-y-2">
					<div class="flex items-center justify-between gap-2">
						<Label for="taskiq_schedule_prefix">schedule prefix</Label>
						<span
							class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
						>
							<Lock class="h-3 w-3" />
							env-only
						</span>
					</div>
					<Input
						id="taskiq_schedule_prefix"
						value={rawValue(taskiqSchedulePrefix)}
						disabled
						class="rounded-xl font-mono"
					/>
					<p class="text-xs text-zinc-500">Redis key prefix for dynamic schedules.</p>
				</div>
				<div class="space-y-2">
					<div class="flex items-center justify-between gap-2">
						<Label for="taskiq_result_ttl">result TTL</Label>
						<span
							class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
						>
							<Lock class="h-3 w-3" />
							env-only
						</span>
					</div>
					<Input
						id="taskiq_result_ttl"
						value={displayValue(taskiqResultTtlSeconds, 'seconds')}
						disabled
						class="rounded-xl"
					/>
					<p class="text-xs text-zinc-500">TaskIQ result backend retention.</p>
				</div>
				<div class="space-y-2">
					<div class="flex items-center justify-between gap-2">
						<Label for="taskiq_max_connections">max Redis connections</Label>
						<span
							class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
						>
							<Lock class="h-3 w-3" />
							env-only
						</span>
					</div>
					<Input
						id="taskiq_max_connections"
						value={rawValue(taskiqMaxConnections)}
						disabled
						class="rounded-xl"
					/>
					<p class="text-xs text-zinc-500">
						shared across broker, scheduler, and result backend.
					</p>
				</div>
				<div class="space-y-2">
					<div class="flex items-center justify-between gap-2">
						<Label for="taskiq_auto_workers_max">auto worker max</Label>
						<span
							class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
						>
							<Lock class="h-3 w-3" />
							env-only
						</span>
					</div>
					<Input
						id="taskiq_auto_workers_max"
						value={rawValue(taskiqAutoWorkersMax)}
						disabled
						class="rounded-xl"
					/>
					<p class="text-xs text-zinc-500">
						optional ceiling for --workers auto. unset leaves it uncapped.
					</p>
				</div>
			</div>

			<div class="grid gap-3 md:grid-cols-3">
				<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-3">
					<p class="text-xs font-medium text-zinc-300">worker concurrency</p>
					<p class="mt-1 text-xs text-zinc-500">deployment command</p>
				</div>
				<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-3">
					<p class="text-xs font-medium text-zinc-300">task priority</p>
					<p class="mt-1 text-xs text-zinc-500">FIFO queue</p>
				</div>
				<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-3">
					<p class="text-xs font-medium text-zinc-300">scheduled task cap</p>
					<p class="mt-1 text-xs text-zinc-500">domain batch settings</p>
				</div>
			</div>
		</CardContent>
	</Card>

	<Card class="border-zinc-800 bg-zinc-900">
		<CardHeader>
			<CardTitle>thread maintenance</CardTitle>
			<CardDescription>live metadata, summaries, and recovery policy.</CardDescription>
		</CardHeader>
		<CardContent class="space-y-5">
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="maintenance_inactivity_hours">inactivity delay</Label>
					<p class="text-xs text-zinc-500">
						hours before deferred summary maintenance runs after activity stops.
					</p>
					<Input
						id="maintenance_inactivity_hours"
						type="number"
						min="1"
						placeholder="8"
						bind:value={maintenanceInactivityHours}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="maintenance_queued_supersede">queued replacement delay</Label>
					<p class="text-xs text-zinc-500">
						minutes a zero-progress queued task can idle before replacement.
					</p>
					<Input
						id="maintenance_queued_supersede"
						type="number"
						min="1"
						placeholder="5"
						bind:value={maintenanceQueuedSupersedeAfterMinutes}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="maintenance_active_supersede">active replacement delay</Label>
					<p class="text-xs text-zinc-500">
						minutes an active task can go silent before replacement.
					</p>
					<Input
						id="maintenance_active_supersede"
						type="number"
						min="1"
						placeholder="30"
						bind:value={maintenanceActiveSupersedeAfterMinutes}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="maintenance_runner_timeout">runner timeout</Label>
					<p class="text-xs text-zinc-500">
						seconds before thread-related durable task runners fail.
					</p>
					<Input
						id="maintenance_runner_timeout"
						type="number"
						min="1"
						placeholder="1800"
						bind:value={maintenanceRunnerTimeoutSeconds}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="maintenance_cleanup_delay">cleanup delay</Label>
					<p class="text-xs text-zinc-500">
						minutes before startup cleanup fails stale thread-related tasks.
					</p>
					<Input
						id="maintenance_cleanup_delay"
						type="number"
						min="1"
						placeholder="45"
						bind:value={maintenanceStaleTaskCleanupAfterMinutes}
						class="rounded-xl"
					/>
				</div>
			</div>

			<div
				class="flex items-center justify-between gap-4 rounded-xl border border-zinc-800 bg-zinc-950 p-4"
			>
				<div class="space-y-1">
					<Label for="maintenance_backfill_enabled">backfill sweep</Label>
					<p class="text-xs text-zinc-500">
						enable a scheduled sweep for old inactive threads with incomplete metadata
						or summaries.
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
							<SelectItem value="weekdays">business days</SelectItem>
							<SelectItem value="weekly">weekly</SelectItem>
							<SelectItem value="monthly">monthly</SelectItem>
							<SelectItem value="yearly">annually</SelectItem>
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
					<div class="space-y-2">
						<Label for="maintenance_backfill_custom_cron">custom cron</Label>
						<p class="text-xs text-zinc-500">five-field cron expression in UTC.</p>
						<Input
							id="maintenance_backfill_custom_cron"
							value={backfillCron}
							oninput={(event) => setBackfillCustomCron(event.currentTarget.value)}
							class="rounded-xl font-mono"
							placeholder="0 4 * * 1-5"
						/>
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
								{weekdays.find((weekday) => weekday.value === backfillWeekday)
									?.label ?? 'monday'}
							</SelectTrigger>
							<SelectContent>
								{#each weekdays as weekday (weekday.value)}
									<SelectItem value={weekday.value}>{weekday.label}</SelectItem>
								{/each}
							</SelectContent>
						</Select>
					</div>
				{:else if backfillFrequency === 'monthly' || backfillFrequency === 'yearly'}
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
				{#if backfillFrequency === 'yearly'}
					<div class="space-y-2">
						<Label for="maintenance_backfill_month">month</Label>
						<p class="text-xs text-zinc-500">month of year in UTC.</p>
						<Select value={backfillMonth} onValueChange={setBackfillMonth}>
							<SelectTrigger id="maintenance_backfill_month" class="rounded-xl">
								{months.find((month) => month.value === backfillMonth)?.label ??
									'january'}
							</SelectTrigger>
							<SelectContent>
								{#each months as month (month.value)}
									<SelectItem value={month.value}>{month.label}</SelectItem>
								{/each}
							</SelectContent>
						</Select>
					</div>
				{/if}
				<div class="space-y-2">
					<Label for="maintenance_backfill_batch">batch size</Label>
					<p class="text-xs text-zinc-500">maximum thread maintenance tasks per sweep.</p>
					<Input
						id="maintenance_backfill_batch"
						type="number"
						min="1"
						placeholder="10"
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
						placeholder="30"
						bind:value={backfillMaxLookbackDays}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="maintenance_backfill_inactivity">min inactivity hours</Label>
					<p class="text-xs text-zinc-500">
						minimum idle time before a thread is eligible.
					</p>
					<Input
						id="maintenance_backfill_inactivity"
						type="number"
						min="1"
						placeholder="8"
						bind:value={backfillMinInactivityHours}
						class="rounded-xl"
					/>
				</div>
			</div>
		</CardContent>
	</Card>
</div>
