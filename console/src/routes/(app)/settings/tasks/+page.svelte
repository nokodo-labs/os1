<script lang="ts">
	import { api } from '$lib/api'
	import SettingsTasks from '$lib/components/settings/SettingsTasks.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { toStringOrEmpty } from '$lib/settings/utils'
	import { asNumberOrUndefined } from '$lib/utils/settingsNumbers'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'

	const ctx = getSettingsContext()

	let taskiqQueueName = $state('')
	let taskiqResultTtlSeconds = $state('')
	let taskiqMaxConnections = $state('')
	let taskiqAutoWorkersMax = $state('')
	let taskiqSchedulePrefix = $state('')
	let maintenanceInactivityHours = $state('')
	let maintenanceQueuedSupersedeAfterMinutes = $state('')
	let maintenanceActiveSupersedeAfterMinutes = $state('')
	let maintenanceRunnerTimeoutSeconds = $state('')
	let maintenanceStaleTaskCleanupAfterMinutes = $state('')
	let backfillEnabled = $state(false)
	let backfillCron = $state('')
	let backfillBatchSize = $state('')
	let backfillMaxLookbackDays = $state('')
	let backfillMinInactivityHours = $state('')
	let fileMaintenanceEnabled = $state(false)
	let fileMaintenanceCron = $state('')
	let fileMaintenanceBatchSize = $state('')

	type Original = {
		taskiqQueueName: string
		taskiqResultTtlSeconds: string
		taskiqMaxConnections: string
		taskiqAutoWorkersMax: string
		taskiqSchedulePrefix: string
		maintenanceInactivityHours: string
		maintenanceQueuedSupersedeAfterMinutes: string
		maintenanceActiveSupersedeAfterMinutes: string
		maintenanceRunnerTimeoutSeconds: string
		maintenanceStaleTaskCleanupAfterMinutes: string
		backfillEnabled: boolean
		backfillCron: string
		backfillBatchSize: string
		backfillMaxLookbackDays: string
		backfillMinInactivityHours: string
		fileMaintenanceEnabled: boolean
		fileMaintenanceCron: string
		fileMaintenanceBatchSize: string
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const tasks = r.data.tasks
		const taskiq = tasks?.taskiq
		taskiqQueueName = taskiq?.queue_name ?? ''
		taskiqResultTtlSeconds = toStringOrEmpty(taskiq?.result_ttl_seconds)
		taskiqMaxConnections = toStringOrEmpty(taskiq?.max_connections)
		taskiqAutoWorkersMax = toStringOrEmpty(taskiq?.auto_workers_max)
		taskiqSchedulePrefix = taskiq?.schedule_prefix ?? ''
		const maint = tasks?.thread_maintenance
		maintenanceInactivityHours = toStringOrEmpty(maint?.inactivity_hours)
		maintenanceQueuedSupersedeAfterMinutes = toStringOrEmpty(
			maint?.queued_supersede_after_minutes
		)
		maintenanceActiveSupersedeAfterMinutes = toStringOrEmpty(
			maint?.active_supersede_after_minutes
		)
		maintenanceRunnerTimeoutSeconds = toStringOrEmpty(maint?.runner_timeout_seconds)
		maintenanceStaleTaskCleanupAfterMinutes = toStringOrEmpty(
			maint?.stale_task_cleanup_after_minutes
		)
		const backfill = tasks?.maintenance_backfill
		backfillEnabled = backfill?.enabled ?? false
		backfillCron = toStringOrEmpty(backfill?.cron)
		backfillBatchSize = toStringOrEmpty(backfill?.batch_size)
		backfillMaxLookbackDays = toStringOrEmpty(backfill?.max_lookback_days)
		backfillMinInactivityHours = toStringOrEmpty(backfill?.min_inactivity_hours)
		const fileMaint = tasks?.file_maintenance
		fileMaintenanceEnabled = fileMaint?.enabled ?? false
		fileMaintenanceCron = toStringOrEmpty(fileMaint?.cron)
		fileMaintenanceBatchSize = toStringOrEmpty(fileMaint?.batch_size)

		original = {
			taskiqQueueName,
			taskiqResultTtlSeconds,
			taskiqMaxConnections,
			taskiqAutoWorkersMax,
			taskiqSchedulePrefix,
			maintenanceInactivityHours,
			maintenanceQueuedSupersedeAfterMinutes,
			maintenanceActiveSupersedeAfterMinutes,
			maintenanceRunnerTimeoutSeconds,
			maintenanceStaleTaskCleanupAfterMinutes,
			backfillEnabled,
			backfillCron,
			backfillBatchSize,
			backfillMaxLookbackDays,
			backfillMinInactivityHours,
			fileMaintenanceEnabled,
			fileMaintenanceCron,
			fileMaintenanceBatchSize,
		}
	})

	const hasChanges = $derived(
		original !== null &&
			(taskiqQueueName !== original.taskiqQueueName ||
				taskiqResultTtlSeconds !== original.taskiqResultTtlSeconds ||
				taskiqMaxConnections !== original.taskiqMaxConnections ||
				taskiqAutoWorkersMax !== original.taskiqAutoWorkersMax ||
				taskiqSchedulePrefix !== original.taskiqSchedulePrefix ||
				maintenanceInactivityHours !== original.maintenanceInactivityHours ||
				maintenanceQueuedSupersedeAfterMinutes !==
					original.maintenanceQueuedSupersedeAfterMinutes ||
				maintenanceActiveSupersedeAfterMinutes !==
					original.maintenanceActiveSupersedeAfterMinutes ||
				maintenanceRunnerTimeoutSeconds !== original.maintenanceRunnerTimeoutSeconds ||
				maintenanceStaleTaskCleanupAfterMinutes !==
					original.maintenanceStaleTaskCleanupAfterMinutes ||
				backfillEnabled !== original.backfillEnabled ||
				backfillCron !== original.backfillCron ||
				backfillBatchSize !== original.backfillBatchSize ||
				backfillMaxLookbackDays !== original.backfillMaxLookbackDays ||
				backfillMinInactivityHours !== original.backfillMinInactivityHours ||
				fileMaintenanceEnabled !== original.fileMaintenanceEnabled ||
				fileMaintenanceCron !== original.fileMaintenanceCron ||
				fileMaintenanceBatchSize !== original.fileMaintenanceBatchSize)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		taskiqQueueName = original.taskiqQueueName
		taskiqResultTtlSeconds = original.taskiqResultTtlSeconds
		taskiqMaxConnections = original.taskiqMaxConnections
		taskiqAutoWorkersMax = original.taskiqAutoWorkersMax
		taskiqSchedulePrefix = original.taskiqSchedulePrefix
		maintenanceInactivityHours = original.maintenanceInactivityHours
		maintenanceQueuedSupersedeAfterMinutes = original.maintenanceQueuedSupersedeAfterMinutes
		maintenanceActiveSupersedeAfterMinutes = original.maintenanceActiveSupersedeAfterMinutes
		maintenanceRunnerTimeoutSeconds = original.maintenanceRunnerTimeoutSeconds
		maintenanceStaleTaskCleanupAfterMinutes = original.maintenanceStaleTaskCleanupAfterMinutes
		backfillEnabled = original.backfillEnabled
		backfillCron = original.backfillCron
		backfillBatchSize = original.backfillBatchSize
		backfillMaxLookbackDays = original.backfillMaxLookbackDays
		backfillMinInactivityHours = original.backfillMinInactivityHours
		fileMaintenanceEnabled = original.fileMaintenanceEnabled
		fileMaintenanceCron = original.fileMaintenanceCron
		fileMaintenanceBatchSize = original.fileMaintenanceBatchSize
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const tasksPatch: Record<string, unknown> = {}

			if (
				maintenanceInactivityHours !== original.maintenanceInactivityHours ||
				maintenanceQueuedSupersedeAfterMinutes !==
					original.maintenanceQueuedSupersedeAfterMinutes ||
				maintenanceActiveSupersedeAfterMinutes !==
					original.maintenanceActiveSupersedeAfterMinutes ||
				maintenanceRunnerTimeoutSeconds !== original.maintenanceRunnerTimeoutSeconds ||
				maintenanceStaleTaskCleanupAfterMinutes !==
					original.maintenanceStaleTaskCleanupAfterMinutes
			) {
				const mp: Record<string, unknown> = {}
				if (maintenanceInactivityHours !== original.maintenanceInactivityHours)
					mp.inactivity_hours = asNumberOrUndefined(maintenanceInactivityHours)
				if (
					maintenanceQueuedSupersedeAfterMinutes !==
					original.maintenanceQueuedSupersedeAfterMinutes
				)
					mp.queued_supersede_after_minutes = asNumberOrUndefined(
						maintenanceQueuedSupersedeAfterMinutes
					)
				if (
					maintenanceActiveSupersedeAfterMinutes !==
					original.maintenanceActiveSupersedeAfterMinutes
				)
					mp.active_supersede_after_minutes = asNumberOrUndefined(
						maintenanceActiveSupersedeAfterMinutes
					)
				if (maintenanceRunnerTimeoutSeconds !== original.maintenanceRunnerTimeoutSeconds)
					mp.runner_timeout_seconds = asNumberOrUndefined(maintenanceRunnerTimeoutSeconds)
				if (
					maintenanceStaleTaskCleanupAfterMinutes !==
					original.maintenanceStaleTaskCleanupAfterMinutes
				)
					mp.stale_task_cleanup_after_minutes = asNumberOrUndefined(
						maintenanceStaleTaskCleanupAfterMinutes
					)
				tasksPatch.thread_maintenance = mp
			}

			if (
				backfillEnabled !== original.backfillEnabled ||
				backfillCron !== original.backfillCron ||
				backfillBatchSize !== original.backfillBatchSize ||
				backfillMaxLookbackDays !== original.backfillMaxLookbackDays ||
				backfillMinInactivityHours !== original.backfillMinInactivityHours
			) {
				const bp: Record<string, unknown> = {}
				if (backfillEnabled !== original.backfillEnabled) bp.enabled = backfillEnabled
				if (backfillCron !== original.backfillCron) bp.cron = backfillCron
				if (backfillBatchSize !== original.backfillBatchSize)
					bp.batch_size = asNumberOrUndefined(backfillBatchSize)
				if (backfillMaxLookbackDays !== original.backfillMaxLookbackDays)
					bp.max_lookback_days = asNumberOrUndefined(backfillMaxLookbackDays)
				if (backfillMinInactivityHours !== original.backfillMinInactivityHours)
					bp.min_inactivity_hours = asNumberOrUndefined(backfillMinInactivityHours)
				tasksPatch.maintenance_backfill = bp
			}

			if (
				fileMaintenanceEnabled !== original.fileMaintenanceEnabled ||
				fileMaintenanceCron !== original.fileMaintenanceCron ||
				fileMaintenanceBatchSize !== original.fileMaintenanceBatchSize
			) {
				const fp: Record<string, unknown> = {}
				if (fileMaintenanceEnabled !== original.fileMaintenanceEnabled)
					fp.enabled = fileMaintenanceEnabled
				if (fileMaintenanceCron !== original.fileMaintenanceCron)
					fp.cron = fileMaintenanceCron
				if (fileMaintenanceBatchSize !== original.fileMaintenanceBatchSize)
					fp.batch_size = asNumberOrUndefined(fileMaintenanceBatchSize)
				tasksPatch.file_maintenance = fp
			}

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { tasks: tasksPatch },
					expected_versions: ctx.response.versions ?? null,
				},
			})
			if (result.error) {
				if (result.response.status === 409) {
					saveError = 'settings were updated elsewhere. reload and try again.'
				} else {
					const detail = result.error?.detail
					saveError = typeof detail === 'string' ? detail : 'failed to save settings'
				}
				return
			}
			ctx.setFromResponse(result.data!)
			saveSuccess = 'saved'
		} catch (e) {
			console.error('Failed to save tasks settings', e)
			saveError = 'failed to save settings'
		} finally {
			isSaving = false
		}
	}
</script>

<div class="flex flex-col gap-4">
	<div class="flex items-center justify-between gap-2">
		<div>
			{#if saveError}
				<p class="text-sm text-red-400">{saveError}</p>
			{:else if saveSuccess}
				<p class="text-sm text-emerald-400">{saveSuccess}</p>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={ctx.fetchSettings}
				disabled={ctx.isFetching || isSaving}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				reload
			</Button>
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={resetDraft}
				disabled={!hasChanges || isSaving}
			>
				<RotateCcw class="mr-1.5 h-4 w-4" />
				reset
			</Button>
			<Button class="rounded-xl" onclick={save} disabled={!hasChanges || isSaving}>
				<Save class="mr-1.5 h-4 w-4" />
				{isSaving ? 'saving...' : 'save'}
			</Button>
		</div>
	</div>

	<SettingsTasks
		{taskiqQueueName}
		{taskiqResultTtlSeconds}
		{taskiqMaxConnections}
		{taskiqAutoWorkersMax}
		{taskiqSchedulePrefix}
		bind:maintenanceInactivityHours
		bind:maintenanceQueuedSupersedeAfterMinutes
		bind:maintenanceActiveSupersedeAfterMinutes
		bind:maintenanceRunnerTimeoutSeconds
		bind:maintenanceStaleTaskCleanupAfterMinutes
		bind:backfillEnabled
		bind:backfillCron
		bind:backfillBatchSize
		bind:backfillMaxLookbackDays
		bind:backfillMinInactivityHours
		bind:fileMaintenanceEnabled
		bind:fileMaintenanceCron
		bind:fileMaintenanceBatchSize
	/>
</div>
