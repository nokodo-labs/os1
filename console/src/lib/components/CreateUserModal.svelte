<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type User = Schemas['User']

	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Switch } from '$lib/components/ui/switch'
	import { X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		onCreated?: (user: User) => void
		onClose?: () => void
	}

	let { open = $bindable(false), onCreated, onClose }: Props = $props()

	let isCreating = $state(false)
	let error = $state<string | null>(null)

	let email = $state('')
	let password = $state('')
	let displayName = $state('')
	let isActive = $state(true)
	let isSuperuser = $state(false)

	function reset() {
		email = ''
		password = ''
		displayName = ''
		isActive = true
		isSuperuser = false
		error = null
	}

	function close() {
		open = false
		onClose?.()
	}

	async function submit() {
		const trimmedEmail = email.trim()
		if (!trimmedEmail) {
			error = 'email is required'
			return
		}
		if (!password) {
			error = 'password is required'
			return
		}

		isCreating = true
		error = null
		try {
			const created = unwrap(
				await api.POST('/v1/users', {
					body: {
						email: trimmedEmail,
						password,
						display_name: displayName.trim() ? displayName.trim() : null,
						is_active: isActive,
						is_superuser: isSuperuser,
					},
				})
			)
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

<Dialog.Root bind:open>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[85vh] w-[min(520px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">add user</Dialog.Title>
					<Dialog.Description class="mt-0.5 text-sm text-zinc-400">
						create a new user account
					</Dialog.Description>
				</div>
				<button
					class="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
					onclick={close}
					disabled={isCreating}
				>
					<X class="h-4 w-4" />
				</button>
			</div>

			<div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-6">
				{#if error}
					<div
						class="rounded-xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				{/if}

				<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
					<div class="space-y-2">
						<Label for="create_email">email</Label>
						<Input id="create_email" bind:value={email} class="rounded-xl" />
					</div>
					<div class="space-y-2">
						<Label for="create_display_name">display name</Label>
						<Input
							id="create_display_name"
							bind:value={displayName}
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="create_password">password</Label>
						<Input
							id="create_password"
							type="password"
							bind:value={password}
							class="rounded-xl"
						/>
					</div>
					<div
						class="flex flex-col gap-3 rounded-xl border border-zinc-800 bg-zinc-900 p-3"
					>
						<label class="flex items-center justify-between gap-3">
							<span class="text-sm text-zinc-200">active</span>
							<Switch bind:checked={isActive} />
						</label>
						<label class="flex items-center justify-between gap-3">
							<span class="text-sm text-zinc-200">superuser</span>
							<Switch bind:checked={isSuperuser} />
						</label>
					</div>
				</div>
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
