<script lang="ts">
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { projects } from '$lib/stores/projects.svelte'

	interface Props {
		open: boolean
		onClose: () => void
		onCreated?: (project: { id: string }) => void
	}

	let { open, onClose, onCreated }: Props = $props()

	let name = $state('')
	let description = $state('')
	let saving = $state(false)

	$effect(() => {
		if (open) {
			name = ''
			description = ''
		}
	})

	async function create() {
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
				onCreated?.(created)
			}
		} finally {
			saving = false
		}
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
			event.preventDefault()
			void create()
		}
	}
</script>

<BaseModal
	{open}
	title="create project"
	onClose={() => !saving && onClose()}
	widthClassName="max-w-md"
>
	<form
		class="space-y-4"
		onsubmit={(e) => {
			e.preventDefault()
			void create()
		}}
	>
		<div>
			<label for="new-project-name" class="mb-1.5 block text-sm text-foreground/60">name</label>
			<input
				id="new-project-name"
				type="text"
				bind:value={name}
				class="w-full rounded-xl border border-foreground/15 bg-foreground/5 px-4 py-2.5 text-base text-foreground/90 transition-colors outline-none placeholder:text-foreground/30 focus:border-foreground/25"
				placeholder="project name"
				disabled={saving}
				onkeydown={handleKeyDown}
			/>
		</div>
		<div>
			<label for="new-project-desc" class="mb-1.5 block text-sm text-foreground/60"
				>description</label
			>
			<textarea
				id="new-project-desc"
				bind:value={description}
				class="w-full resize-none rounded-xl border border-foreground/15 bg-foreground/5 px-4 py-2.5 text-sm text-foreground/70 transition-colors outline-none placeholder:text-foreground/30 focus:border-foreground/25"
				placeholder="describe this project (optional)"
				rows="3"
				disabled={saving}
				onkeydown={handleKeyDown}
			></textarea>
		</div>
		<div class="flex items-center justify-end gap-2 pt-1">
			<button
				type="button"
				class="rounded-pill border border-foreground/10 bg-transparent px-4 py-2 text-sm text-foreground/80 transition-colors duration-150 hover:bg-foreground/5"
				disabled={saving}
				onclick={onClose}
			>
				cancel
			</button>
			<button
				type="submit"
				class="rounded-pill border border-foreground/15 bg-foreground/10 px-4 py-2 text-sm text-foreground/90 transition-colors duration-150 hover:bg-foreground/15 disabled:opacity-50"
				disabled={saving || !name.trim()}
			>
				{saving ? 'creating' : 'create'}
			</button>
		</div>
	</form>
</BaseModal>
