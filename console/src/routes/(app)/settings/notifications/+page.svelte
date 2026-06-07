<script lang="ts">
	import { api } from '$lib/api'
	import SettingsNotifications from '$lib/components/settings/SettingsNotifications.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { toStringOrEmpty } from '$lib/settings/utils'
	import { asNumberOrNull, asNumberOrUndefined } from '$lib/utils/settingsNumbers'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'

	const ctx = getSettingsContext()

	let webPushEnabled = $state(false)
	let webPushTtlSeconds = $state('')
	let notificationTtlSeconds = $state('')
	let missedGraceDays = $state('')
	let lookaheadDays = $state('')
	let vapidPublicKey = $state('')
	let vapidPrivateKey = $state('')

	type Original = {
		webPushEnabled: boolean
		webPushTtlSeconds: string
		notificationTtlSeconds: string
		missedGraceDays: string
		lookaheadDays: string
		vapidPublicKey: string
		vapidPrivateKey: string
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const notif = r.data.notifications
		webPushEnabled = notif?.web_push_enabled ?? false
		webPushTtlSeconds = toStringOrEmpty(notif?.web_push_ttl_seconds)
		notificationTtlSeconds = toStringOrEmpty(notif?.notification_ttl_seconds)
		missedGraceDays = toStringOrEmpty(notif?.missed_grace_days)
		lookaheadDays = toStringOrEmpty(notif?.lookahead_days)
		vapidPublicKey = notif?.vapid_public_key ?? ''
		vapidPrivateKey = notif?.vapid_private_key ?? ''
		original = {
			webPushEnabled,
			webPushTtlSeconds,
			notificationTtlSeconds,
			missedGraceDays,
			lookaheadDays,
			vapidPublicKey,
			vapidPrivateKey,
		}
	})

	const hasChanges = $derived(
		original !== null &&
			(webPushEnabled !== original.webPushEnabled ||
				webPushTtlSeconds !== original.webPushTtlSeconds ||
				notificationTtlSeconds !== original.notificationTtlSeconds ||
				missedGraceDays !== original.missedGraceDays ||
				lookaheadDays !== original.lookaheadDays ||
				vapidPublicKey !== original.vapidPublicKey ||
				vapidPrivateKey !== original.vapidPrivateKey)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)
	let isGeneratingVapidKeys = $state(false)
	let vapidGenerationError = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		webPushEnabled = original.webPushEnabled
		webPushTtlSeconds = original.webPushTtlSeconds
		notificationTtlSeconds = original.notificationTtlSeconds
		missedGraceDays = original.missedGraceDays
		lookaheadDays = original.lookaheadDays
		vapidPublicKey = original.vapidPublicKey
		vapidPrivateKey = original.vapidPrivateKey
		saveError = null
		saveSuccess = null
	}

	async function generateVapidKeys() {
		if (vapidPublicKey.trim() || vapidPrivateKey.trim()) return
		isGeneratingVapidKeys = true
		vapidGenerationError = null
		try {
			const result = await api.POST('/v1/settings/vapid-keypair', {})
			if (result.error) {
				const detail = result.error?.detail
				vapidGenerationError =
					typeof detail === 'string' ? detail : 'failed to generate VAPID keys'
				return
			}
			if (!result.data) {
				vapidGenerationError = 'failed to generate VAPID keys'
				return
			}
			vapidPublicKey = result.data.public_key
			vapidPrivateKey = result.data.private_key
		} catch (e) {
			console.error('Failed to generate VAPID keys', e)
			vapidGenerationError = 'failed to generate VAPID keys'
		} finally {
			isGeneratingVapidKeys = false
		}
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const np: Record<string, unknown> = {}
			if (webPushEnabled !== original.webPushEnabled) np.web_push_enabled = webPushEnabled
			if (webPushTtlSeconds !== original.webPushTtlSeconds)
				np.web_push_ttl_seconds = asNumberOrUndefined(webPushTtlSeconds)
			if (notificationTtlSeconds !== original.notificationTtlSeconds)
				np.notification_ttl_seconds = asNumberOrNull(notificationTtlSeconds)
			if (missedGraceDays !== original.missedGraceDays)
				np.missed_grace_days = asNumberOrUndefined(missedGraceDays)
			if (lookaheadDays !== original.lookaheadDays)
				np.lookahead_days = asNumberOrUndefined(lookaheadDays)
			if (vapidPublicKey !== original.vapidPublicKey)
				np.vapid_public_key = vapidPublicKey || null
			if (vapidPrivateKey !== original.vapidPrivateKey)
				np.vapid_private_key = vapidPrivateKey || null

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { notifications: np },
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
			console.error('Failed to save notifications settings', e)
			saveError = 'failed to save settings'
		} finally {
			isSaving = false
		}
	}
</script>

<div class="flex flex-col gap-4">
	<div class="flex items-center justify-between gap-2">
		<div>
			{#if vapidGenerationError}
				<p class="text-sm text-red-400">{vapidGenerationError}</p>
			{:else if saveError}
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
				disabled={ctx.isFetching || isSaving || isGeneratingVapidKeys}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				reload
			</Button>
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={resetDraft}
				disabled={!hasChanges || isSaving || isGeneratingVapidKeys}
			>
				<RotateCcw class="mr-1.5 h-4 w-4" />
				reset
			</Button>
			<Button
				class="rounded-xl"
				onclick={save}
				disabled={!hasChanges || isSaving || isGeneratingVapidKeys}
			>
				<Save class="mr-1.5 h-4 w-4" />
				{isSaving ? 'saving...' : 'save'}
			</Button>
		</div>
	</div>

	<SettingsNotifications
		bind:webPushEnabled
		bind:webPushTtlSeconds
		bind:notificationTtlSeconds
		bind:missedGraceDays
		bind:lookaheadDays
		bind:vapidPublicKey
		bind:vapidPrivateKey
		{isGeneratingVapidKeys}
		{vapidGenerationError}
		onGenerateVapidKeys={generateVapidKeys}
	/>
</div>
