<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type DefaultPermissions_Input = Schemas['DefaultPermissions-Input']
	type DefaultPermissions_Output = Schemas['DefaultPermissions-Output']
	type Role = Schemas['Role']
	type RoleCreate = Schemas['RoleCreate']

	import DefaultPermissionsEditor from '$lib/components/DefaultPermissionsEditor.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		onCreated?: (role: Role) => void
		onClose?: () => void
	}

	let { open = $bindable(false), onCreated, onClose }: Props = $props()

	let isCreating = $state(false)
	let error = $state<string | null>(null)

	let name = $state('')
	let description = $state('')
	let defaultPermissions = $state<DefaultPermissions_Input>({
		resource_access: {},
		action_permissions: [],
	})

	function normalizePermissions(
		input: DefaultPermissions_Input | DefaultPermissions_Output
	): DefaultPermissions_Input {
		return {
			resource_access: {
				thread: input.resource_access?.thread ?? null,
				project: input.resource_access?.project ?? null,
				file: input.resource_access?.file ?? null,
				note: input.resource_access?.note ?? null,
				group: input.resource_access?.group ?? null,
				reminder_list: input.resource_access?.reminder_list ?? null,
			},
			action_permissions: [...(input.action_permissions ?? [])].sort(),
		}
	}

	function reset() {
		name = ''
		description = ''
		defaultPermissions = { resource_access: {}, action_permissions: [] }
		error = null
	}

	function close() {
		open = false
		onClose?.()
	}

	function buildPayload(): RoleCreate {
		return {
			name: name.trim(),
			description: description.trim() ? description.trim() : null,
			priority: 0,
			default_permissions: normalizePermissions(defaultPermissions),
		}
	}

	async function submit() {
		if (!name.trim()) {
			error = 'name is required'
			return
		}

		isCreating = true
		error = null
		try {
			const created = unwrap(await api.POST('/v1/roles', { body: buildPayload() }))
			onCreated?.(created)
			reset()
			close()
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : String(e)
		} finally {
			isCreating = false
		}
	}
</script>

<Dialog.Root
	bind:open
	onOpenChange={(v) => {
		if (!v) close()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[90vh] w-[min(768px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">new role</Dialog.Title>
					<Dialog.Description class="text-sm text-zinc-400">
						create a role with default permissions
					</Dialog.Description>
				</div>
				<Button variant="ghost" size="icon" class="rounded-xl" onclick={close}>
					<X class="h-4 w-4" />
				</Button>
			</div>

			<div class="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-4">
				{#if error}
					<div
						class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				{/if}

				<div class="space-y-2">
					<Label for="role_name">name</Label>
					<Input id="role_name" bind:value={name} class="rounded-xl" />
				</div>

				<div class="space-y-2">
					<Label for="role_description">description</Label>
					<textarea
						id="role_description"
						rows="3"
						class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600"
						bind:value={description}
					></textarea>
				</div>

				<DefaultPermissionsEditor bind:value={defaultPermissions} />
			</div>

			<div class="flex shrink-0 justify-end gap-2 border-t border-zinc-800 px-6 py-4">
				<Button
					type="button"
					variant="outline"
					class="rounded-xl"
					onclick={close}
					disabled={isCreating}
				>
					cancel
				</Button>
				<Button type="button" class="rounded-xl" onclick={submit} disabled={isCreating}>
					{isCreating ? 'creating...' : 'create'}
				</Button>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
