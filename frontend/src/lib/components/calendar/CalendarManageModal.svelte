<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import CalendarIcon from '$lib/components/icons/Calendar.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Info from '$lib/components/icons/Info.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { Switch } from '$lib/components/primitives'
	import {
		calendars,
		type Calendar,
		type CalendarCreate,
		type CalendarUpdate,
	} from '$lib/stores/calendars.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import {
		canDeleteAccessLevel,
		canEditAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { byAuthor, metadataLine } from '$lib/utils/resourceAuthors'

	interface Props {
		open: boolean
		calendar?: Calendar | null
		onClose: () => void
	}

	let { open, calendar = null, onClose }: Props = $props()

	let name = $state('')
	let description = $state('')
	let color = $state('#d45446')
	let timezone = $state('')
	let isDefault = $state(false)
	let saving = $state(false)
	let error = $state('')

	const isCreate = $derived(!calendar?.id)
	const calendarAccessLevel = $derived(
		calendar?.id ? resourceAccess.level('calendar', calendar.id, calendar.owner_id) : 'admin'
	)
	const canEditCalendar = $derived(isCreate || canEditAccessLevel(calendarAccessLevel))
	const canDeleteCalendar = $derived(!isCreate && canDeleteAccessLevel(calendarAccessLevel))
	const title = $derived(isCreate ? 'create calendar' : 'calendar properties')
	const authorLabel = $derived(session.authorLabel(calendar?.owner_id))
	const previewSubtitle = $derived(metadataLine(byAuthor(authorLabel), timezone.trim() || null))
	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const fieldClass = `${panelClass} grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 rounded-[16px] border p-3`
	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6 disabled:cursor-not-allowed disabled:opacity-55'
	const iconClass = 'h-4 w-4 text-(--accent-primary)'
	const labelClass = 'text-foreground/60 text-[0.78rem] font-semibold'
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'

	$effect(() => {
		if (!open) return
		name = calendar?.name ?? ''
		description = calendar?.description ?? ''
		color = calendar?.color ?? '#d45446'
		timezone = calendar?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone
		isDefault = calendar?.is_default ?? false
		saving = false
		error = ''
	})

	$effect(() => {
		const accessKey = open && calendar?.id ? `${calendar.id}:${resourceAccess.version}` : ''
		if (open && calendar?.owner_id && calendar.owner_id !== session.currentUserId) {
			void session.ensureUsers([calendar.owner_id])
		}
		if (open && calendar?.id && accessKey) {
			void resourceAccess.ensure('calendar', calendar.id, calendar.owner_id)
		}
	})

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault()
		void save()
	}

	async function save(): Promise<void> {
		if (!canEditCalendar) return
		const trimmedName = name.trim()
		if (!trimmedName) {
			error = 'name is required'
			return
		}

		saving = true
		error = ''
		try {
			const payload = {
				name: trimmedName,
				description: description.trim() || null,
				color,
				is_default: isDefault,
				timezone: timezone.trim() || null,
				project_ids: calendar?.project_ids ?? [],
				metadata_: calendar?.metadata_ ?? {},
			}
			const saved = calendar?.id
				? await calendars.update(calendar.id, payload satisfies CalendarUpdate)
				: await calendars.create({
						...payload,
						position: calendars.all.length,
					} satisfies CalendarCreate)
			if (!saved) return
			onClose()
		} finally {
			saving = false
		}
	}

	function shareCalendar(): void {
		if (!calendar?.id) return
		onClose()
		modals.open('resource-access', {
			resourceType: 'calendar',
			resourceId: calendar.id,
			title: calendar.name,
		})
	}

	function requestDelete(): void {
		if (!calendar?.id || calendar.is_default || !canDeleteCalendar) return
		modals.open('confirm-delete', {
			title: 'delete calendar?',
			description: calendar.name,
			onDelete: async () => {
				const deleted = await calendars.remove(calendar.id)
				if (!deleted) return false
				onClose()
				return true
			},
		})
	}
</script>

<BaseModal
	{open}
	{title}
	description={isCreate ? 'new calendar' : calendar?.name}
	onClose={() => !saving && onClose()}
	widthClassName="max-w-lg"
>
	<form class="grid gap-3" onsubmit={handleSubmit}>
		<div
			class="{panelClass} flex min-w-0 items-center gap-4 rounded-[18px] border p-4 max-[680px]:flex-wrap"
		>
			<div
				class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] text-white"
				style={`background-color: ${color}`}
			>
				<CalendarIcon class="h-5 w-5" />
			</div>
			<div class="min-w-0 flex-1">
				<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
					{isDefault ? 'default' : 'calendar'}
				</p>
				<h3 class="text-foreground min-w-0 truncate text-lg font-semibold">
					{name.trim() || 'untitled calendar'}
				</h3>
				{#if previewSubtitle}
					<p class="text-foreground/55 mt-0.5 min-w-0 truncate text-xs">
						{previewSubtitle}
					</p>
				{/if}
			</div>
			<div
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/75 ml-auto inline-flex items-center gap-2 border px-3 py-2 text-[0.8rem] font-semibold whitespace-nowrap"
			>
				<span>default</span>
				<Switch
					size="sm"
					bind:checked={isDefault}
					disabled={saving || !canEditCalendar}
					ariaLabel="default calendar"
				/>
			</div>
		</div>

		<div class={fieldClass}>
			<Info class={iconClass} />
			<label class={labelClass} for="calendar-name">name</label>
			<input
				id="calendar-name"
				type="text"
				class="{inputClass} col-span-full"
				bind:value={name}
				placeholder="calendar name"
				disabled={saving || !canEditCalendar}
			/>
		</div>

		<div class="grid grid-cols-2 gap-3 max-[680px]:grid-cols-1">
			<div class={fieldClass}>
				<CalendarIcon class={iconClass} />
				<label class={labelClass} for="calendar-color">color</label>
				<div class="col-span-full grid min-w-0 grid-cols-[3rem_minmax(0,1fr)] gap-2">
					<input
						id="calendar-color"
						type="color"
						bind:value={color}
						class="border-foreground/12 h-10 w-12 cursor-pointer rounded-xl border bg-transparent disabled:cursor-not-allowed disabled:opacity-55"
						disabled={saving || !canEditCalendar}
					/>
					<input
						type="text"
						bind:value={color}
						class={inputClass}
						disabled={saving || !canEditCalendar}
						aria-label="color value"
					/>
				</div>
			</div>
			<div class={fieldClass}>
				<GlobeAlt class={iconClass} />
				<label class={labelClass} for="calendar-timezone">timezone</label>
				<input
					id="calendar-timezone"
					type="text"
					class="{inputClass} col-span-full"
					bind:value={timezone}
					placeholder="local timezone"
					disabled={saving || !canEditCalendar}
				/>
			</div>
		</div>

		<div class={fieldClass}>
			<Info class={iconClass} />
			<label class={labelClass} for="calendar-description">description</label>
			<textarea
				id="calendar-description"
				class="{inputClass} col-span-full min-h-24 resize-y text-sm"
				bind:value={description}
				placeholder="notes"
				disabled={saving || !canEditCalendar}
			></textarea>
		</div>

		{#if error}
			<p class="text-destructive text-sm">{error}</p>
		{/if}

		<div class="flex items-center gap-2 pt-1 max-[680px]:flex-wrap">
			{#if calendar?.id}
				<button
					type="button"
					class="{actionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent"
					disabled={saving}
					onclick={shareCalendar}
				>
					<Share class="h-4 w-4" />
					<span>share</span>
				</button>
			{/if}
			{#if calendar?.id && !calendar.is_default && canDeleteCalendar}
				<button
					type="button"
					class="{actionButtonClass} border border-red-500/30 bg-red-500/13 text-red-300"
					disabled={saving}
					onclick={requestDelete}
				>
					<Trash class="h-4 w-4" />
					<span>delete</span>
				</button>
			{/if}
			<div class="flex-1"></div>
			{#if canEditCalendar}
				<button
					type="submit"
					class="{actionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]"
					disabled={saving || !name.trim()}
				>
					<Check class="h-4 w-4" />
					{#if saving}<ShimmerText className="inline-block">saving</ShimmerText
						>{:else}<span>save</span>{/if}
				</button>
			{/if}
		</div>
	</form>
</BaseModal>
