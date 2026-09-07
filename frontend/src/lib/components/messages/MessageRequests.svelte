<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import ConversationAvatar from '$lib/components/messages/ConversationAvatar.svelte'
	import { Skeleton } from '$lib/components/primitives'
	import { messages } from '$lib/stores/messages.svelte'
	import { showError } from '$lib/stores/notifications.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { conversationDisplay } from '$lib/utils/conversationDisplay'

	interface Props {
		onOpenConversation?: (threadId: string) => void
	}

	let { onOpenConversation }: Props = $props()

	let busyId = $state<string | null>(null)

	async function act(threadId: string, action: 'accept' | 'decline' | 'block'): Promise<void> {
		if (busyId) return
		busyId = threadId
		try {
			if (action === 'accept') {
				const thread = await messages.acceptInvite(threadId)
				if (thread) onOpenConversation?.(thread.id)
			} else if (action === 'decline') {
				await messages.declineInvite(threadId)
			} else {
				await messages.blockInvite(threadId)
			}
		} catch {
			showError(`could not ${action} request`)
		} finally {
			busyId = null
		}
	}

	$effect(() => {
		void messages.loadInvites()
	})
</script>

<div class="flex min-h-0 flex-1 flex-col gap-2">
	{#if messages.invites.length === 0 && !messages.hasLoadedInvites}
		<Skeleton shape="row" count={3} lines={2} trailing />
	{:else if messages.invites.length === 0}
		<EmptyState label="no message requests" compact class="flex-1">
			{#snippet icon()}<ChatBubble class="size-6" />{/snippet}
		</EmptyState>
	{:else}
		{#each messages.invites as invite (invite.id)}
			{@const display = conversationDisplay(invite, session.currentUserId)}
			<div class="bg-foreground/4 flex items-center gap-3 rounded-2xl px-3 py-2.5">
				<ConversationAvatar faces={display.faces} isGroup={display.isGroup} />
				<div class="flex min-w-0 flex-1 flex-col gap-0.5">
					<span class="text-foreground truncate text-sm font-semibold">
						{display.title}
					</span>
					<span class="text-foreground/50 truncate text-xs">wants to message you</span>
				</div>
				<div class="flex shrink-0 items-center gap-1.5">
					<button
						type="button"
						class="rounded-pill bg-(--accent-primary) cursor-pointer px-3 py-1.5 text-xs font-semibold text-white transition-all hover:brightness-[1.06] active:scale-[0.97] disabled:opacity-55"
						disabled={busyId === invite.id}
						onclick={() => act(invite.id, 'accept')}
					>
						{#if busyId === invite.id}<ShimmerText className="inline-block"
								>…</ShimmerText
							>{:else}accept{/if}
					</button>
					<button
						type="button"
						class="rounded-pill bg-foreground/8 text-foreground/70 hover:bg-foreground/12 cursor-pointer px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-55"
						disabled={busyId === invite.id}
						onclick={() => act(invite.id, 'decline')}
					>
						decline
					</button>
					<button
						type="button"
						class="rounded-pill text-red-500/70 hover:bg-red-500/10 cursor-pointer px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-55"
						disabled={busyId === invite.id}
						onclick={() => act(invite.id, 'block')}
					>
						block
					</button>
				</div>
			</div>
		{/each}
	{/if}
</div>
