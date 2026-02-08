<script lang="ts">
	import {
		api,
		unwrap,
		type DefaultPermissions_Input,
		type DefaultPermissions_Output,
		type Role,
		type RoleCreate,
	} from '$lib/api'
	import DefaultPermissionsEditor from '$lib/components/DefaultPermissionsEditor.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardFooter,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') close()
	}

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

{#if open}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
		onkeydown={handleKeydown}
		onclick={(e) => {
			if (e.target === e.currentTarget) close()
		}}
	>
		<Card
			class="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100"
		>
			<CardHeader class="shrink-0">
				<CardTitle>new role</CardTitle>
				<CardDescription>create a role with default permissions</CardDescription>
			</CardHeader>
			<CardContent class="min-h-0 flex-1 space-y-6 overflow-y-auto">
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
						placeholder="optional description"
						bind:value={description}
					></textarea>
				</div>

				<DefaultPermissionsEditor bind:value={defaultPermissions} />
			</CardContent>
			<CardFooter class="flex shrink-0 justify-end gap-2">
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
			</CardFooter>
		</Card>
	</div>
{/if}
