<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Info from '$lib/components/icons/Info.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
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
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const groupVisual = resourceVisual('group')
	const GroupIcon = groupVisual.icon
	const groupAccentStyle = resourceAccentStyle('group')
	const previewTitle = $derived(name.trim() || group.name || 'untitled group')
	const previewDescription = $derived(description.trim() || `${group.memberships.length} members`)

	$effect(() => {
		if (open) {
			name = group.name
			description = group.description ?? ''
			saving = false
		}
	})

	async function save(): Promise<void> {
		if (saving || !canManage || !name.trim()) return
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

		<div class="flex items-center gap-2 pt-1 max-[520px]:flex-wrap">
			<button
				type="button"
				class="{actionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent"
				disabled={saving}
				onclick={shareGroup}
			>
				<Share class="h-4 w-4" />
				<span>share</span>
			</button>
			<div class="flex-1"></div>
			{#if canManage}
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
