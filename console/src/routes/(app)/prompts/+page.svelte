<script lang="ts">
	import { PromptsService, type Prompt } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Pencil, Plus, Trash2 } from '@lucide/svelte'
	import { onMount } from 'svelte'

	let prompts = $state<Prompt[]>([])
	let isLoading = $state(false)
	let isSaving = $state(false)
	let isDeleting = $state(false)
	let error = $state<string | null>(null)

	let showModal = $state(false)
	let modalMode = $state<'create' | 'edit'>('create')
	let editingId = $state<string | null>(null)
	let formCommand = $state('')
	let formContent = $state('')

	onMount(() => {
		refresh()
	})

	async function refresh() {
		isLoading = true
		error = null
		try {
			prompts = await PromptsService.listPromptsPromptsGet()
		} catch (e: any) {
			error = e?.message ?? 'failed to load prompts'
		} finally {
			isLoading = false
		}
	}

	function openCreateModal() {
		modalMode = 'create'
		editingId = null
		formCommand = ''
		formContent = ''
		showModal = true
	}

	function openEditModal(prompt: Prompt) {
		modalMode = 'edit'
		editingId = prompt.id
		formCommand = prompt.command
		formContent = prompt.content
		showModal = true
	}

	function closeModal() {
		showModal = false
	}

	async function handleSave() {
		const trimmedCommand = formCommand.trim()
		if (!trimmedCommand) {
			error = 'command is required'
			return
		}
		if (!formContent.trim()) {
			error = 'content is required'
			return
		}

		isSaving = true
		error = null
		try {
			if (modalMode === 'edit' && editingId) {
				await PromptsService.updatePromptPromptsPromptIdPatch(editingId, {
					command: trimmedCommand,
					content: formContent,
				})
			} else {
				await PromptsService.createPromptPromptsPost({
					command: trimmedCommand,
					content: formContent,
				})
			}
			await refresh()
			closeModal()
		} catch (e: any) {
			error = e?.message ?? 'failed to save prompt'
		} finally {
			isSaving = false
		}
	}

	async function handleDelete(promptId: string) {
		const ok = confirm('delete this prompt? this cannot be undone.')
		if (!ok) return

		isDeleting = true
		error = null
		try {
			await PromptsService.deletePromptPromptsPromptIdDelete(promptId)
			await refresh()
		} catch (e: any) {
			error = e?.message ?? 'failed to delete prompt'
		} finally {
			isDeleting = false
		}
	}

	function preview(text: string, maxLen = 180) {
		const normalized = text.replace(/\s+/g, ' ').trim()
		if (normalized.length <= maxLen) return normalized
		return normalized.slice(0, maxLen) + '…'
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">prompts</h2>
			<p class="text-zinc-400">write and iterate on prompts.</p>
		</div>
		<div class="flex items-center gap-2">
			<Button class="gap-2 rounded-xl" onclick={openCreateModal}>
				<Plus class="h-4 w-4" />
				create prompt
			</Button>
			<Button
				variant="outline"
				class="rounded-xl"
				onclick={() => refresh()}
				disabled={isLoading}
			>
				{isLoading ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	{#if error}
		<div class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200">
			{error}
		</div>
	{/if}

	{#if isLoading && prompts.length === 0}
		<div
			class="flex items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-950 p-10"
		>
			<NokodoLoader />
		</div>
	{:else if prompts.length === 0}
		<div
			class="rounded-2xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
		>
			no prompts yet
		</div>
	{:else}
		<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
			{#each prompts as p (p.id)}
				<Card class="overflow-hidden rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
					<CardHeader class="flex flex-row items-start justify-between space-y-0 pb-2">
						<div class="min-w-0">
							<CardTitle class="truncate text-base font-medium">{p.command}</CardTitle
							>
							<CardDescription class="truncate">
								updated {new Date(p.updated_at).toLocaleString()}
							</CardDescription>
						</div>
						<div class="flex gap-2">
							<Button
								variant="ghost"
								size="icon"
								class="h-8 w-8 text-zinc-400 hover:text-zinc-100"
								onclick={() => openEditModal(p)}
							>
								<Pencil class="h-4 w-4" />
							</Button>
							<Button
								variant="ghost"
								size="icon"
								class="h-8 w-8 text-zinc-400 hover:text-red-500"
								onclick={() => handleDelete(p.id)}
								disabled={isDeleting}
							>
								<Trash2 class="h-4 w-4" />
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						<div class="font-mono text-xs whitespace-pre-wrap text-zinc-400">
							{preview(p.content)}
						</div>
					</CardContent>
				</Card>
			{/each}
		</div>
	{/if}
</div>

{#if showModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
	>
		<Card class="w-full max-w-3xl rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader>
				<CardTitle>{modalMode === 'create' ? 'create prompt' : 'edit prompt'}</CardTitle>
				<CardDescription>command + content</CardDescription>
			</CardHeader>
			<form
				onsubmit={(e) => {
					e.preventDefault()
					handleSave()
				}}
			>
				<CardContent class="max-h-[70vh] space-y-4 overflow-y-auto pr-2">
					<div class="space-y-2">
						<Label for="command">command</Label>
						<Input
							id="command"
							bind:value={formCommand}
							placeholder="e.g. /summarize"
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="content">content</Label>
						<textarea
							id="content"
							bind:value={formContent}
							rows={16}
							placeholder="write your prompt..."
							class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm"
						></textarea>
					</div>
				</CardContent>
				<div class="flex justify-end gap-2 border-t border-zinc-800 p-4">
					<Button
						type="button"
						variant="outline"
						class="rounded-xl"
						onclick={closeModal}
						disabled={isSaving}
					>
						cancel
					</Button>
					<Button type="submit" class="rounded-xl" disabled={isSaving}>
						{isSaving ? 'saving...' : 'save'}
					</Button>
				</div>
			</form>
		</Card>
	</div>
{/if}
