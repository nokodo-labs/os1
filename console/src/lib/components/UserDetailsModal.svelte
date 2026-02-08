<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { api, unwrap, type User } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'

	type Props = {
		open: boolean
		userId: string | null
		onClose?: () => void
	}

	let { open = $bindable(false), userId, onClose }: Props = $props()

	let user = $state<User | null>(null)
	let isLoading = $state(false)
	let error = $state<string | null>(null)

	function close() {
		open = false
		onClose?.()
	}

	function openThreads(userId: string) {
		void goto(resolve('/threads'), { state: { user: userId } })
		close()
	}

	function openMemories(userId: string) {
		void goto(resolve('/memories'), { state: { user: userId } })
		close()
	}

	function openRoles(userId: string) {
		void goto(resolve('/roles'), { state: { user: userId } })
		close()
	}

	function errorMessage(error: unknown): string {
		if (error instanceof Error) return error.message
		if (typeof error === 'string') return error
		return 'failed to load user'
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!userId) return

		isLoading = true
		error = null
		user = null

		api.GET('/v1/users/{user_id}', { params: { path: { user_id: userId } } })
			.then((r) => unwrap(r))
			.then((u) => {
				user = u
			})
			.catch((e: unknown) => {
				error = errorMessage(e)
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

{#if open}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
		<Card class="w-full max-w-lg rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader class="flex flex-row items-start justify-between gap-4">
				<div>
					<CardTitle>user details</CardTitle>
					<CardDescription>{userId ?? ''}</CardDescription>
				</div>
				<Button variant="outline" class="rounded-xl" onclick={() => close()}>close</Button>
			</CardHeader>
			<CardContent class="space-y-4">
				{#if isLoading}
					<div class="flex items-center justify-center py-10">
						<NokodoLoader />
					</div>
				{:else if error}
					<div
						class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				{:else if user}
					<div class="space-y-3">
						<div class="flex flex-wrap gap-2">
							<Button class="rounded-xl" onclick={() => user && openThreads(user.id)}>
								threads
							</Button>
							<Button
								variant="outline"
								class="rounded-xl"
								onclick={() => user && openMemories(user.id)}
							>
								memories
							</Button>
							<Button
								variant="outline"
								class="rounded-xl"
								onclick={() => user && openRoles(user.id)}
							>
								roles
							</Button>
						</div>

						<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-sm">
							<div class="flex justify-between gap-3">
								<span class="text-zinc-400">email</span>
								<span class="truncate">{user.email}</span>
							</div>
							<div class="mt-2 flex justify-between gap-3">
								<span class="text-zinc-400">id</span>
								<span class="truncate">{user.id}</span>
							</div>
							<div class="mt-2 flex justify-between gap-3">
								<span class="text-zinc-400">display name</span>
								<span class="truncate">{user.display_name ?? '-'}</span>
							</div>
							<div class="mt-2 flex justify-between gap-3">
								<span class="text-zinc-400">active</span>
								<span>{user.is_active === false ? 'no' : 'yes'}</span>
							</div>
							<div class="mt-2 flex justify-between gap-3">
								<span class="text-zinc-400">superuser</span>
								<span>{user.is_superuser ? 'yes' : 'no'}</span>
							</div>
						</div>

						<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
							<div
								class="rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400"
							>
								<div class="text-zinc-500">created</div>
								<div class="mt-1 text-zinc-200">
									{new Date(user.created_at).toLocaleString()}
								</div>
							</div>
							<div
								class="rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400"
							>
								<div class="text-zinc-500">updated</div>
								<div class="mt-1 text-zinc-200">
									{new Date(user.updated_at).toLocaleString()}
								</div>
							</div>
						</div>
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
					>
						no user selected
					</div>
				{/if}
			</CardContent>
		</Card>
	</div>
{/if}
