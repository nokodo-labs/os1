<script lang="ts">
	import { UsersService, type User } from '$lib/api'
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
	import { Switch } from '$lib/components/ui/switch'

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
			const created = await UsersService.createUserUsersPost({
				email: trimmedEmail,
				password,
				display_name: displayName.trim() ? displayName.trim() : null,
				is_active: isActive,
				is_superuser: isSuperuser,
			})
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
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
		<Card class="w-full max-w-lg rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader>
				<CardTitle>add user</CardTitle>
				<CardDescription>create a new user account</CardDescription>
			</CardHeader>
			<CardContent class="space-y-4">
				{#if error}
					<div
						class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
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
						class="flex flex-col gap-3 rounded-xl border border-zinc-800 bg-zinc-950 p-3"
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
			</CardContent>
			<CardFooter class="flex justify-end gap-2">
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
