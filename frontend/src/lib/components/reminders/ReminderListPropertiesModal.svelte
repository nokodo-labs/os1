<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Info from '$lib/components/icons/Info.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { Switch } from '$lib/components/primitives'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { modals } from '$lib/stores/modals.svelte'
	import {
		reminders,
		type ReminderListUpdate,
		type ReminderListWithCounts,
	} from '$lib/stores/reminders.svelte'
	import {
		canEditAccessLevel,
		canShareAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { byAuthor, metadataLine } from '$lib/utils/resourceAuthors'

	interface Props {
		open: boolean
		list: ReminderListWithCounts | null
		onClose: () => void
	}

	let { open, list, onClose }: Props = $props()

	let name = $state('')
	let description = $state('')
	let icon = $state('')
	let color = $state('#d45446')
	let isDefault = $state(false)
	let isSaving = $state(false)
	let error = $state<string | null>(null)

	const iconOptions = ['📌', '✅', '💼', '🏠', '🛒', '💊', '✈️', '🎁', '📚', '⚡', '🔥', '🧠']
	const listAccessLevel = $derived(
		list ? resourceAccess.level('reminder_list', list.id, list.owner_id) : null
	)
	const canEditList = $derived(canEditAccessLevel(listAccessLevel))
	const canShareList = $derived(canShareAccessLevel(listAccessLevel))
	const iconChoices = $derived(
		icon.trim() && !iconOptions.includes(icon.trim())
			? [icon.trim(), ...iconOptions]
			: iconOptions
	)
	const authorLabel = $derived(session.authorLabel(list?.owner_id))
	const reminderVisual = resourceVisual('reminder_list')
	const ReminderIcon = reminderVisual.icon
	const reminderAccentStyle = resourceAccentStyle('reminder_list')
	const previewSubtitle = $derived(
		metadataLine(
			byAuthor(authorLabel),
			`${list?.pending_count ?? 0} pending of ${list?.total_count ?? 0}`
		)
	)

	$effect(() => {
		if (!open || !list) return
		name = list.name
		description = list.description ?? ''
		icon = list.icon ?? ''
		color = list.color ?? '#d45446'
		isDefault = list.is_default
		isSaving = false
		error = null
	})

	$effect(() => {
		if (open && list?.owner_id && list.owner_id !== session.currentUserId) {
			void session.ensureUsers([list.owner_id])
		}
		if (open && list) void resourceAccess.ensure('reminder_list', list.id, list.owner_id)
	})

	function displayName(value: string): string {
		const trimmed = value.trim()
		return trimmed || 'untitled list'
	}

	function shareList(): void {
		if (!list || !canShareList) return
		onClose()
		modals.open('resource-access', {
			resourceType: 'reminder_list',
			resourceId: list.id,
			title: displayName(name),
		})
	}

	function selectIcon(value: string): void {
		if (isSaving || !canEditList) return
		icon = value
	}

	async function save(): Promise<void> {
		if (!list || !canEditList || isSaving) return
		const trimmedName = name.trim()
		if (!trimmedName) {
			error = 'name is required'
			return
		}

		isSaving = true
		error = null
		try {
			const updates: ReminderListUpdate = {
				name: trimmedName,
				description: description.trim() || null,
				icon: icon.trim() || null,
				color: color.trim() || null,
				is_default: list.is_default ? true : isDefault,
				project_ids: list.project_ids ?? [],
				metadata_: list.metadata_ ?? {},
			}
			const saved = await reminders.updateList(list, updates)
			if (!saved) {
				error = 'could not save list'
				return
			}
			onClose()
		} finally {
			isSaving = false
		}
	}

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault()
		void save()
	}

	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const fieldClass = `${panelClass} grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 rounded-[16px] border p-3`
	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6 disabled:cursor-not-allowed disabled:opacity-55'
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
</script>

<BaseModal
	{open}
	title="list properties"
	description="name, appearance, and access"
	onClose={() => !isSaving && onClose()}
	widthClassName="max-w-lg"
>
	{#if list}
		<form class="grid gap-3" style={reminderAccentStyle} onsubmit={handleSubmit}>
			<section class="{panelClass} flex min-w-0 items-center gap-4 rounded-[18px] border p-4">
				<div
					class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] text-white"
					style={`background-color: ${color}`}
				>
					{#if icon.trim()}
						<span class="text-lg leading-none">{icon.trim()}</span>
					{:else}
						<ReminderIcon variant="solid" class="h-5 w-5" />
					{/if}
				</div>
				<div class="min-w-0 flex-1">
					<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
						{list.is_default ? 'default reminders' : 'reminder list'}
					</p>
					<h3 class="text-foreground min-w-0 truncate text-lg font-semibold">
						{displayName(name)}
					</h3>
					<p class="text-foreground/55 mt-0.5 min-w-0 truncate text-xs">
						{previewSubtitle}
					</p>
				</div>
				<div
					class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/75 ml-auto inline-flex items-center gap-2 border px-3 py-2 text-[0.8rem] font-semibold whitespace-nowrap max-[520px]:ml-0"
				>
					<span>default</span>
					<Switch
						size="sm"
						bind:checked={isDefault}
						disabled={isSaving || list.is_default || !canEditList}
						ariaLabel="default list"
					/>
				</div>
			</section>

			<div class={fieldClass}>
				<ReminderIcon variant="solid" class="h-4 w-4 text-(--accent-primary)" />
				<label class="text-foreground/60 text-[0.78rem] font-semibold" for="list-name">
					name
				</label>
				<input
					id="list-name"
					type="text"
					class="{inputClass} col-span-full"
					bind:value={name}
					placeholder="list name"
					disabled={isSaving || !canEditList}
				/>
			</div>

			<div class="grid grid-cols-2 gap-3 max-[520px]:grid-cols-1">
				<div class={fieldClass}>
					<ReminderIcon variant="solid" class="h-4 w-4 text-(--accent-primary)" />
					<span class="text-foreground/60 text-[0.78rem] font-semibold">icon</span>
					<div class="col-span-full grid grid-cols-6 gap-1.5">
						<button
							type="button"
							class="border-foreground/10 bg-foreground/5 text-foreground/60 hover:bg-foreground/8 rounded-xl border px-2 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-55 {icon.trim() ===
							''
								? 'text-foreground border-[color-mix(in_oklch,var(--accent-primary)_44%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_16%,transparent)]'
								: ''}"
							disabled={isSaving || !canEditList}
							onclick={() => selectIcon('')}
						>
							-
						</button>
						{#each iconChoices as option (option)}
							<button
								type="button"
								class="border-foreground/10 bg-foreground/5 hover:bg-foreground/8 rounded-xl border px-2 py-2 text-lg leading-none transition-colors disabled:cursor-not-allowed disabled:opacity-55 {icon.trim() ===
								option
									? 'border-[color-mix(in_oklch,var(--accent-primary)_44%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_16%,transparent)]'
									: ''}"
								disabled={isSaving || !canEditList}
								onclick={() => selectIcon(option)}
								aria-label={`use ${option} icon`}
							>
								{option}
							</button>
						{/each}
					</div>
				</div>
				<div class={fieldClass}>
					<ReminderIcon variant="solid" class="h-4 w-4 text-(--accent-primary)" />
					<label class="text-foreground/60 text-[0.78rem] font-semibold" for="list-color">
						color
					</label>
					<div class="col-span-full grid min-w-0 grid-cols-[3rem_minmax(0,1fr)] gap-2">
						<input
							id="list-color"
							type="color"
							bind:value={color}
							class="border-foreground/12 h-10 w-12 cursor-pointer rounded-xl border bg-transparent disabled:cursor-not-allowed disabled:opacity-55"
							disabled={isSaving || !canEditList}
						/>
						<input
							type="text"
							bind:value={color}
							class={inputClass}
							disabled={isSaving || !canEditList}
							aria-label="color value"
						/>
					</div>
				</div>
			</div>

			<div class={fieldClass}>
				<Info class="h-4 w-4 text-(--accent-primary)" />
				<label
					class="text-foreground/60 text-[0.78rem] font-semibold"
					for="list-description"
				>
					description
				</label>
				<textarea
					id="list-description"
					class="{inputClass} col-span-full min-h-24 resize-y text-sm"
					bind:value={description}
					placeholder="what belongs here"
					disabled={isSaving || !canEditList}
				></textarea>
			</div>

			{#if error}
				<p class="text-destructive text-sm">{error}</p>
			{/if}

			<div class="flex items-center gap-2 pt-1 max-[520px]:flex-wrap">
				{#if canShareList}
					<button
						type="button"
						class="{actionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent"
						disabled={isSaving}
						onclick={shareList}
					>
						<Share class="h-4 w-4" />
						<span>share</span>
					</button>
				{/if}
				<div class="flex-1"></div>
				{#if canEditList}
					<button
						type="submit"
						class="{actionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]"
						disabled={isSaving || !name.trim()}
					>
						<Check class="h-4 w-4" />
						{#if isSaving}<ShimmerText className="inline-block">saving</ShimmerText
							>{:else}<span>save</span>{/if}
					</button>
				{/if}
			</div>
		</form>
	{:else}
		<div class="text-foreground/65 text-sm">list not found</div>
	{/if}
</BaseModal>
