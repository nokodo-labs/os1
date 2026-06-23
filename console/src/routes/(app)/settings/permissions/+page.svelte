<script lang="ts">
	import { api, type Schemas } from '$lib/api'
	import SettingsDefaultPermissions from '$lib/components/settings/SettingsDefaultPermissions.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { normalizeDefaultPermissions } from '$lib/settings/utils'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'
	import { untrack } from 'svelte'

	type DefaultPermissionsSettings = Schemas['DefaultPermissionsSettings']

	function defaultPermissionsKey(v: DefaultPermissionsSettings): string {
		return JSON.stringify(v)
	}

	const ctx = getSettingsContext()

	let permissions = $state<DefaultPermissionsSettings>({
		resource_access: {
			thread: null,
			project: null,
			file: null,
			calendar: null,
			note: null,
			group: null,
			reminder_list: null,
		},
		action_permissions: [],
	})
	let originalKey = $state<string | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		permissions = normalizeDefaultPermissions(
			r.data.default_permissions ?? {
				resource_access: {},
				action_permissions: [],
			}
		)
		untrack(() => {
			originalKey = defaultPermissionsKey(permissions)
		})
	})

	const hasChanges = $derived(
		originalKey !== null && defaultPermissionsKey(permissions) !== originalKey
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!ctx.response) return
		permissions = normalizeDefaultPermissions(
			ctx.response.data.default_permissions ?? {
				resource_access: {},
				action_permissions: [],
			}
		)
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const patch = {
				resource_access: {
					thread: permissions.resource_access?.thread ?? null,
					project: permissions.resource_access?.project ?? null,
					file: permissions.resource_access?.file ?? null,
					calendar: permissions.resource_access?.calendar ?? null,
					note: permissions.resource_access?.note ?? null,
					group: permissions.resource_access?.group ?? null,
					reminder_list: permissions.resource_access?.reminder_list ?? null,
				},
				action_permissions: permissions.action_permissions ?? [],
			}

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { default_permissions: patch },
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
			console.error('Failed to save permissions settings', e)
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

	<SettingsDefaultPermissions bind:value={permissions} />
</div>
