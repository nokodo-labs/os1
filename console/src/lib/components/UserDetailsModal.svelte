<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { api, unwrap, type Schemas } from '$lib/api'

	type User = Schemas['User']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Brain,
		CheckCircle,
		Circle,
		Clock,
		Hash,
		Mail,
		MessageSquare,
		Shield,
		Sliders,
		User as UserIcon,
		Wifi,
		X,
		XCircle,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		userId: string | null
		onClose?: () => void
	}

	let { open = $bindable(false), userId, onClose }: Props = $props()

	let user = $state<User | null>(null)
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let showPreferences = $state(false)

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
		showPreferences = false

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

<Dialog.Root bind:open>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[85vh] w-[min(540px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">user details</Dialog.Title>
					<Dialog.Description class="mt-0.5 text-sm text-zinc-400">
						{userId ?? ''}
					</Dialog.Description>
				</div>
				<button
					class="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
					onclick={close}
				>
					<X class="h-4 w-4" />
				</button>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto p-6">
				{#if isLoading}
					<div class="flex items-center justify-center py-12">
						<NokodoLoader />
					</div>
				{:else if error}
					<div
						class="rounded-xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				{:else if user}
					<div class="space-y-5">
						<!-- Quick actions -->
						<div class="flex flex-wrap gap-2">
							<Button
								variant="outline"
								class="rounded-xl"
								onclick={() => user && openThreads(user.id)}
							>
								<MessageSquare class="mr-1.5 h-3.5 w-3.5" />
								threads
							</Button>
							<Button
								variant="outline"
								class="rounded-xl"
								onclick={() => user && openMemories(user.id)}
							>
								<Brain class="mr-1.5 h-3.5 w-3.5" />
								memories
							</Button>
							<Button
								variant="outline"
								class="rounded-xl"
								onclick={() => user && openRoles(user.id)}
							>
								<Shield class="mr-1.5 h-3.5 w-3.5" />
								roles
							</Button>
							<Button
								variant={showPreferences ? 'secondary' : 'outline'}
								class="rounded-xl"
								onclick={() => (showPreferences = !showPreferences)}
							>
								<Sliders class="mr-1.5 h-3.5 w-3.5" />
								preferences
							</Button>
						</div>

						{#if showPreferences}
							<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
								<div class="mb-2 text-xs font-medium text-zinc-400">
									raw preferences
								</div>
								<pre
									class="max-h-64 overflow-auto text-xs break-all whitespace-pre-wrap text-zinc-300">{user.preferences
										? JSON.stringify(user.preferences, null, 2)
										: 'no preferences set'}</pre>
							</div>
						{/if}

						<!-- User info grid -->
						<div class="space-y-3">
							<div class="flex items-center gap-3 text-sm">
								<UserIcon class="h-4 w-4 shrink-0 text-zinc-500" />
								<span class="text-zinc-400">display name</span>
								<span class="ml-auto truncate font-medium">
									{user.display_name ?? '-'}
								</span>
							</div>
							<div class="flex items-center gap-3 text-sm">
								<Mail class="h-4 w-4 shrink-0 text-zinc-500" />
								<span class="text-zinc-400">email</span>
								<span class="ml-auto truncate font-medium">{user.email}</span>
							</div>
							<div class="flex items-center gap-3 text-sm">
								<Hash class="h-4 w-4 shrink-0 text-zinc-500" />
								<span class="text-zinc-400">id</span>
								<span class="ml-auto truncate font-mono text-xs text-zinc-300">
									{user.id}
								</span>
							</div>

							<div class="h-px bg-zinc-800"></div>

							<div class="flex items-center gap-3 text-sm">
								{#if user.is_active !== false}
									<CheckCircle class="h-4 w-4 shrink-0 text-emerald-400" />
									<span class="text-zinc-400">active</span>
									<span class="ml-auto text-emerald-400">yes</span>
								{:else}
									<XCircle class="h-4 w-4 shrink-0 text-red-400" />
									<span class="text-zinc-400">active</span>
									<span class="ml-auto text-red-400">no</span>
								{/if}
							</div>
							<div class="flex items-center gap-3 text-sm">
								<Shield class="h-4 w-4 shrink-0 text-zinc-500" />
								<span class="text-zinc-400">superuser</span>
								<span
									class="ml-auto {user.is_superuser
										? 'text-amber-400'
										: 'text-zinc-300'}"
								>
									{user.is_superuser ? 'yes' : 'no'}
								</span>
							</div>
							{#if (user as Record<string, unknown>).is_online}
								<div class="flex items-center gap-3 text-sm">
									<Circle
										class="h-4 w-4 shrink-0 fill-emerald-400 text-emerald-400"
									/>
									<span class="text-zinc-400">status</span>
									<span class="ml-auto text-emerald-400">online</span>
								</div>
							{:else}
								<div class="flex items-center gap-3 text-sm">
									<Wifi class="h-4 w-4 shrink-0 text-zinc-500" />
									<span class="text-zinc-400">last active</span>
									<span class="ml-auto text-xs text-zinc-300">
										{(user as Record<string, unknown>).last_active_at
											? new Date(
													(user as Record<string, unknown>)
														.last_active_at as string
												).toLocaleString()
											: 'never'}
									</span>
								</div>
							{/if}

							<div class="h-px bg-zinc-800"></div>

							<div class="flex items-center gap-3 text-sm">
								<Clock class="h-4 w-4 shrink-0 text-zinc-500" />
								<span class="text-zinc-400">created</span>
								<span class="ml-auto text-xs text-zinc-300">
									{new Date(user.created_at).toLocaleString()}
								</span>
							</div>
							<div class="flex items-center gap-3 text-sm">
								<Clock class="h-4 w-4 shrink-0 text-zinc-500" />
								<span class="text-zinc-400">updated</span>
								<span class="ml-auto text-xs text-zinc-300">
									{new Date(user.updated_at).toLocaleString()}
								</span>
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
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
