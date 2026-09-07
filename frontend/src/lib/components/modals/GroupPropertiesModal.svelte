<script lang="ts">
	import Info from '$lib/components/icons/Info.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { ModalFormDirty } from '$lib/components/modals/formDirty.svelte'
	import ModalActions, { modalQuietButtonClass } from '$lib/components/modals/ModalActions.svelte'
	import ModalSaveButton from '$lib/components/modals/ModalSaveButton.svelte'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { groups, type Group } from '$lib/stores/groups.svelte'
	import { modals } from '$lib/stores/modals.svelte'

	interface Props {
		open: boolean
		group: Group
		canManage: boolean
		onClose: () => void
		onSaved?: () => void | Promise<void>
	}

	let { open, group, canManage, onClose, onSaved }: Props = $props()

	let name = $state('')
	let description = $state('')
	let saving = $state(false)

	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const fieldClass = `${panelClass} grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 rounded-[16px] border p-3`
	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6 disabled:cursor-not-allowed disabled:opacity-55'
	const groupVisual = resourceVisual('group')
	const GroupIcon = groupVisual.icon
	const groupAccentStyle = resourceAccentStyle('group')
	const previewTitle = $derived(name.trim() || group.name || 'untitled group')
	const previewDescription = $derived(description.trim() || `${group.memberships.length} members`)
	const form = new ModalFormDirty(() => ({ name, description }))

	$effect(() => {
		if (open) {
			name = group.name
			description = group.description ?? ''
			saving = false
			form.reset()
		}
	})

	async function save(): Promise<void> {
		if (saving || !canManage || !name.trim() || !form.dirty) return
		saving = true
		try {
			const saved = await groups.update(group.id, {
				name: name.trim(),
				description: description.trim() || undefined,
			})
			if (!saved) return
			await onSaved?.()
			onClose()
		} finally {
			saving = false
		}
	}

	function shareGroup(): void {
		onClose()
		modals.open('resource-access', {
			resourceType: 'group',
			resourceId: group.id,
			title: group.name,
		})
	}

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault()
		void save()
	}
</script>

<BaseModal
	{open}
	title="group properties"
	onClose={() => !saving && onClose()}
	widthClassName="max-w-md"
>
	<form class="grid gap-3" style={groupAccentStyle} onsubmit={handleSubmit}>
		<section class="{panelClass} flex min-w-0 items-center gap-4 rounded-[18px] border p-4">
			<div
				class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
			>
				<GroupIcon variant="solid" class="h-5 w-5" />
			</div>
			<div class="min-w-0 flex-1">
				<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
					group
				</p>
				<h3 class="text-foreground min-w-0 truncate text-lg font-semibold">
					{previewTitle}
				</h3>
				<p class="text-foreground/55 mt-0.5 min-w-0 truncate text-xs">
					{previewDescription}
				</p>
			</div>
		</section>

		<div class={fieldClass}>
			<GroupIcon variant="solid" class="h-4 w-4 text-(--accent-primary)" />
			<label class="text-foreground/60 text-[0.78rem] font-semibold" for="group-name"
				>name</label
			>
			<input
				id="group-name"
				type="text"
				bind:value={name}
				class="{inputClass} col-span-full text-base"
				placeholder="group name"
				disabled={saving || !canManage}
			/>
		</div>
		<div class={fieldClass}>
			<Info class="h-4 w-4 text-(--accent-primary)" />
			<label class="text-foreground/60 text-[0.78rem] font-semibold" for="group-desc"
				>description</label
			>
			<textarea
				id="group-desc"
				bind:value={description}
				class="{inputClass} col-span-full min-h-24 resize-y text-sm"
				placeholder="describe this group"
				disabled={saving || !canManage}
			></textarea>
		</div>

		<ModalActions class="pt-1">
			{#snippet leading()}
				<button
					type="button"
					class={modalQuietButtonClass}
					disabled={saving}
					onclick={shareGroup}
				>
					<Share class="h-4 w-4" />
					<span>share</span>
				</button>
			{/snippet}
			{#if canManage}
				<ModalSaveButton
					dirty={form.dirty}
					{saving}
					blockedReason={name.trim() ? null : 'name is required'}
				/>
			{/if}
		</ModalActions>
	</form>
</BaseModal>
