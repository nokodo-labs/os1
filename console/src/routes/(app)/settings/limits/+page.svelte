<script lang="ts">
	import { api } from '$lib/api'
	import SettingsLimits from '$lib/components/settings/SettingsLimits.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { toStringOrEmpty } from '$lib/settings/utils'
	import { asNumberOrNull, asNumberOrUndefined } from '$lib/utils/settingsNumbers'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'

	const ctx = getSettingsContext()

	let maxThreadsPerUser = $state('')
	let maxMessagesPerThread = $state('')
	let maxChatInputChars = $state('')
	let maxFileSizeMb = $state('')
	let maxReminderHierarchyDepth = $state('')
	let maxScheduledItemsWindowDays = $state('')
	let rateLimitRequestsPerMinute = $state('')
	let accessibleUsersTtlSeconds = $state('')
	let scheduledItemsTtlSeconds = $state('')
	let resourcePayloadTtlSeconds = $state('')
	let promptTemplateTtlSeconds = $state('')
	let mcpSnapshotTtlSeconds = $state('')

	type Original = {
		maxThreadsPerUser: string
		maxMessagesPerThread: string
		maxChatInputChars: string
		maxFileSizeMb: string
		maxReminderHierarchyDepth: string
		maxScheduledItemsWindowDays: string
		rateLimitRequestsPerMinute: string
		accessibleUsersTtlSeconds: string
		scheduledItemsTtlSeconds: string
		resourcePayloadTtlSeconds: string
		promptTemplateTtlSeconds: string
		mcpSnapshotTtlSeconds: string
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const limits = r.data.limits
		maxThreadsPerUser = toStringOrEmpty(limits?.max_threads_per_user)
		maxMessagesPerThread = toStringOrEmpty(limits?.max_messages_per_thread)
		maxChatInputChars = toStringOrEmpty(limits?.max_chat_input_chars)
		maxFileSizeMb = toStringOrEmpty(limits?.max_file_size_mb)
		maxReminderHierarchyDepth = toStringOrEmpty(limits?.max_reminder_hierarchy_depth)
		maxScheduledItemsWindowDays = toStringOrEmpty(limits?.max_scheduled_items_window_days)
		rateLimitRequestsPerMinute = toStringOrEmpty(limits?.rate_limit_requests_per_minute)
		accessibleUsersTtlSeconds = toStringOrEmpty(r.data.cache?.accessible_users_ttl_seconds)
		scheduledItemsTtlSeconds = toStringOrEmpty(r.data.cache?.scheduled_items_ttl_seconds)
		resourcePayloadTtlSeconds = toStringOrEmpty(r.data.cache?.resource_payload_ttl_seconds)
		promptTemplateTtlSeconds = toStringOrEmpty(r.data.cache?.prompt_template_ttl_seconds)
		mcpSnapshotTtlSeconds = toStringOrEmpty(r.data.cache?.mcp_snapshot_ttl_seconds)
		original = {
			maxThreadsPerUser,
			maxMessagesPerThread,
			maxChatInputChars,
			maxFileSizeMb,
			maxReminderHierarchyDepth,
			maxScheduledItemsWindowDays,
			rateLimitRequestsPerMinute,
			accessibleUsersTtlSeconds,
			scheduledItemsTtlSeconds,
			resourcePayloadTtlSeconds,
		}
	})

	const hasChanges = $derived(
		original !== null &&
			(maxThreadsPerUser !== original.maxThreadsPerUser ||
				maxMessagesPerThread !== original.maxMessagesPerThread ||
				maxChatInputChars !== original.maxChatInputChars ||
				maxFileSizeMb !== original.maxFileSizeMb ||
				maxReminderHierarchyDepth !== original.maxReminderHierarchyDepth ||
				maxScheduledItemsWindowDays !== original.maxScheduledItemsWindowDays ||
				rateLimitRequestsPerMinute !== original.rateLimitRequestsPerMinute ||
				accessibleUsersTtlSeconds !== original.accessibleUsersTtlSeconds ||
				scheduledItemsTtlSeconds !== original.scheduledItemsTtlSeconds ||
				resourcePayloadTtlSeconds !== original.resourcePayloadTtlSeconds ||
				promptTemplateTtlSeconds !== original.promptTemplateTtlSeconds ||
				mcpSnapshotTtlSeconds !== original.mcpSnapshotTtlSeconds)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		maxThreadsPerUser = original.maxThreadsPerUser
		maxMessagesPerThread = original.maxMessagesPerThread
		maxChatInputChars = original.maxChatInputChars
		maxFileSizeMb = original.maxFileSizeMb
		maxReminderHierarchyDepth = original.maxReminderHierarchyDepth
		maxScheduledItemsWindowDays = original.maxScheduledItemsWindowDays
		rateLimitRequestsPerMinute = original.rateLimitRequestsPerMinute
		accessibleUsersTtlSeconds = original.accessibleUsersTtlSeconds
		scheduledItemsTtlSeconds = original.scheduledItemsTtlSeconds
		resourcePayloadTtlSeconds = original.resourcePayloadTtlSeconds
		promptTemplateTtlSeconds = original.promptTemplateTtlSeconds
		mcpSnapshotTtlSeconds = original.mcpSnapshotTtlSeconds
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const data: Record<string, unknown> = {}
			if (
				maxThreadsPerUser !== original.maxThreadsPerUser ||
				maxMessagesPerThread !== original.maxMessagesPerThread ||
				maxChatInputChars !== original.maxChatInputChars ||
				maxFileSizeMb !== original.maxFileSizeMb ||
				maxReminderHierarchyDepth !== original.maxReminderHierarchyDepth ||
				maxScheduledItemsWindowDays !== original.maxScheduledItemsWindowDays ||
				rateLimitRequestsPerMinute !== original.rateLimitRequestsPerMinute
			) {
				const lp: Record<string, unknown> = {}
				if (maxThreadsPerUser !== original.maxThreadsPerUser)
					lp.max_threads_per_user = asNumberOrUndefined(maxThreadsPerUser)
				if (maxMessagesPerThread !== original.maxMessagesPerThread)
					lp.max_messages_per_thread = asNumberOrUndefined(maxMessagesPerThread)
				if (maxChatInputChars !== original.maxChatInputChars)
					lp.max_chat_input_chars = asNumberOrNull(maxChatInputChars)
				if (maxFileSizeMb !== original.maxFileSizeMb)
					lp.max_file_size_mb = asNumberOrUndefined(maxFileSizeMb)
				if (maxReminderHierarchyDepth !== original.maxReminderHierarchyDepth)
					lp.max_reminder_hierarchy_depth = asNumberOrUndefined(maxReminderHierarchyDepth)
				if (maxScheduledItemsWindowDays !== original.maxScheduledItemsWindowDays)
					lp.max_scheduled_items_window_days = asNumberOrUndefined(
						maxScheduledItemsWindowDays
					)
				if (rateLimitRequestsPerMinute !== original.rateLimitRequestsPerMinute)
					lp.rate_limit_requests_per_minute = asNumberOrUndefined(
						rateLimitRequestsPerMinute
					)
				data.limits = lp
			}
			if (
				accessibleUsersTtlSeconds !== original.accessibleUsersTtlSeconds ||
				scheduledItemsTtlSeconds !== original.scheduledItemsTtlSeconds ||
				resourcePayloadTtlSeconds !== original.resourcePayloadTtlSeconds ||
				promptTemplateTtlSeconds !== original.promptTemplateTtlSeconds ||
				mcpSnapshotTtlSeconds !== original.mcpSnapshotTtlSeconds
			) {
				const cp: Record<string, unknown> = {}
				if (accessibleUsersTtlSeconds !== original.accessibleUsersTtlSeconds)
					cp.accessible_users_ttl_seconds = asNumberOrUndefined(accessibleUsersTtlSeconds)
				if (scheduledItemsTtlSeconds !== original.scheduledItemsTtlSeconds)
					cp.scheduled_items_ttl_seconds = asNumberOrUndefined(scheduledItemsTtlSeconds)
				if (resourcePayloadTtlSeconds !== original.resourcePayloadTtlSeconds)
					cp.resource_payload_ttl_seconds = asNumberOrUndefined(resourcePayloadTtlSeconds)
				if (promptTemplateTtlSeconds !== original.promptTemplateTtlSeconds)
					cp.prompt_template_ttl_seconds = asNumberOrUndefined(promptTemplateTtlSeconds)
				if (mcpSnapshotTtlSeconds !== original.mcpSnapshotTtlSeconds)
					cp.mcp_snapshot_ttl_seconds = asNumberOrUndefined(mcpSnapshotTtlSeconds)
				data.cache = cp
			}

			const result = await api.PATCH('/v1/settings', {
				body: { data, expected_versions: ctx.response.versions ?? null },
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
			console.error('Failed to save limits settings', e)
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

	<SettingsLimits
		bind:maxThreadsPerUser
		bind:maxMessagesPerThread
		bind:maxChatInputChars
		bind:maxFileSizeMb
		bind:maxReminderHierarchyDepth
		bind:maxScheduledItemsWindowDays
		bind:rateLimitRequestsPerMinute
		bind:accessibleUsersTtlSeconds
		bind:scheduledItemsTtlSeconds
		bind:resourcePayloadTtlSeconds
		bind:promptTemplateTtlSeconds
		bind:mcpSnapshotTtlSeconds
	/>
</div>
