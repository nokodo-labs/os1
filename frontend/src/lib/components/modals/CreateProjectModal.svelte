<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import Info from '$lib/components/icons/Info.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { projects } from '$lib/stores/projects.svelte'

	interface Props {
		open: boolean
		onClose: () => void
		onCreated?: (project: { id: string }) => void | Promise<void>
	}

	let { open, onClose, onCreated }: Props = $props()

	let name = $state('')
	let description = $state('')
	let saving = $state(false)

	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const fieldClass = `${panelClass} grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 rounded-[16px] border p-3`
	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6 disabled:cursor-not-allowed disabled:opacity-55'
	const iconClass = 'h-4 w-4 text-(--accent-primary)'
	const labelClass = 'text-foreground/60 text-[0.78rem] font-semibold'
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const previewTitle = $derived(name.trim() || 'untitled project')
	const previewDescription = $derived(description.trim() || 'project')

	$effect(() => {
		if (open) {
			name = ''
			description = ''
			saving = false
		}
	})

	async function save(): Promise<void> {
		if (saving) return
		const trimmed = name.trim()
		if (!trimmed) return
		saving = true
		try {
			const created = await projects.create({
				name: trimmed,
				description: description.trim() || undefined,
			})
			if (created) {
				onClose()
				await onCreated?.(created)
			}
		} finally {
			saving = false
		}
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
			event.preventDefault()
			void save()
		}
	}

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault()
		void save()
	}
</script>

<BaseModal
	{open}
	title="create project"
	onClose={() => !saving && onClose()}
	widthClassName="max-w-md"
>
	<form class="grid gap-3" onsubmit={handleSubmit}>
		<section class="{panelClass} flex min-w-0 items-center gap-4 rounded-[18px] border p-4">
			<div
				class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
			>
				<FinderFolder class="h-5 w-5" />
			</div>
			<div class="min-w-0 flex-1">
				<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
					new project
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
			<FinderFolder class={iconClass} />
			<label class={labelClass} for="new-project-name">name</label>
			<input
				id="new-project-name"
				type="text"
				bind:value={name}
				class="{inputClass} col-span-full text-base"
				placeholder="project name"
				disabled={saving}
				onkeydown={handleKeyDown}
			/>
		</div>
		<div class={fieldClass}>
			<Info class={iconClass} />
			<label class={labelClass} for="new-project-desc">description</label>
			<textarea
				id="new-project-desc"
				bind:value={description}
				class="{inputClass} col-span-full min-h-24 resize-y text-sm"
				placeholder="describe this project"
				disabled={saving}
				onkeydown={handleKeyDown}
			></textarea>
		</div>
		<div class="flex items-center justify-end gap-2 pt-1">
			<button
				type="submit"
				class="{actionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]"
				disabled={saving || !name.trim()}
			>
				<Check class="h-4 w-4" />
				{#if saving}<ShimmerText className="inline-block">saving</ShimmerText>{:else}<span
						>save</span
					>{/if}
			</button>
		</div>
	</form>
</BaseModal>
