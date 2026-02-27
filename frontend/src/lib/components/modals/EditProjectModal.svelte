<script lang="ts">
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { projects, type Project } from '$lib/stores/projects.svelte'

	interface Props {
		open: boolean
		project: Project
		onClose: () => void
	}

	let { open, project, onClose }: Props = $props()

	let name = $state('')
	let description = $state('')
	let saving = $state(false)

	$effect(() => {
		if (open) {
			name = project.name
			description = project.description ?? ''
		}
	})

	async function save() {
		if (!name.trim()) return
		saving = true
		try {
			await projects.update(project.id, {
				name: name.trim(),
				description: description.trim() || undefined,
			})
			onClose()
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
</script>

<BaseModal
	{open}
	title="edit project"
	onClose={() => !saving && onClose()}
	widthClassName="max-w-md"
>
	<form
		class="space-y-4"
		onsubmit={(e) => {
			e.preventDefault()
			void save()
		}}
	>
		<div>
			<label for="project-name" class="mb-1.5 block text-sm text-white/60">name</label>
			<input
				id="project-name"
				type="text"
				bind:value={name}
				class="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-2.5 text-base text-white/90 transition-colors outline-none placeholder:text-white/30 focus:border-white/25"
				placeholder="project name"
				disabled={saving}
				onkeydown={handleKeyDown}
			/>
		</div>
		<div>
			<label for="project-desc" class="mb-1.5 block text-sm text-white/60">description</label>
			<textarea
				id="project-desc"
				bind:value={description}
				class="w-full resize-none rounded-xl border border-white/15 bg-white/5 px-4 py-2.5 text-sm text-white/70 transition-colors outline-none placeholder:text-white/30 focus:border-white/25"
				placeholder="describe this project (optional)"
				rows="3"
				disabled={saving}
				onkeydown={handleKeyDown}
			></textarea>
		</div>
		<div class="flex items-center justify-end gap-2 pt-1">
			<button
				type="button"
				class="rounded-pill border border-white/10 bg-transparent px-4 py-2 text-sm text-white/80 transition-colors duration-150 hover:bg-white/5"
				disabled={saving}
				onclick={onClose}
			>
				cancel
			</button>
			<button
				type="button"
				class="rounded-pill border border-white/15 bg-white/10 px-4 py-2 text-sm text-white/90 transition-colors duration-150 hover:bg-white/15 disabled:opacity-50"
				disabled={saving || !name.trim()}
				onclick={() => void save()}
			>
				{saving ? 'saving...' : 'save'}
			</button>
		</div>
	</form>
</BaseModal>
