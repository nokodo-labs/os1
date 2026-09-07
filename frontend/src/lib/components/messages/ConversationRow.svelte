<script module lang="ts">
	import { contentPartsToText, type ApiMessage } from '$lib/chat/helpers'
	import { threadKind } from '$lib/stores/chat.svelte'
	import { userDisplayName } from '$lib/utils/resourceAuthors'

	/** short stand-in for a message whose content is not text. */
	function attachmentLabel(message: ApiMessage): string | null {
		const parts = message.content ?? []
		if (parts.some((part) => part.type === 'image')) return 'photo'
		if (parts.some((part) => part.type === 'file')) return 'attachment'
		return message.attachments?.length ? 'attachment' : null
	}

	/** name the sender the way the conversation names its people. */
	function senderLabel(
		thread: Thread,
		message: ApiMessage,
		currentUserId: string | null
	): string | null {
		if (message.sender_user_id && message.sender_user_id === currentUserId) return 'you'
		for (const participant of thread.participants ?? []) {
			if (participant.kind === 'user' && participant.user.id === message.sender_user_id) {
				return userDisplayName(participant.user)
			}
			if (participant.kind === 'agent' && participant.agent.id === message.sender_agent_id) {
				return participant.agent.name
			}
		}
		return null
	}

	/**
	 * the preview line while somebody is composing, iMessage-style: a group names
	 * who, a DM stays anonymous because there is only one person it can be. null
	 * when nobody in the thread is composing.
	 */
	export function typingPreview(
		thread: Thread,
		composingUserIds: readonly string[],
		currentUserId: string | null
	): string | null {
		const names: string[] = []
		for (const userId of composingUserIds) {
			if (userId === currentUserId) continue
			for (const participant of thread.participants ?? []) {
				if (participant.kind !== 'user' || participant.user.id !== userId) continue
				names.push(userDisplayName(participant.user) ?? 'someone')
			}
		}
		if (names.length === 0) return null
		if (threadKind(thread) !== 'group') return 'typing...'
		if (names.length === 1) return `${names[0]} is typing...`
		return `${names.length} people are typing...`
	}

	/**
	 * the inbox preview line: what was said last, prefixed by who said it in
	 * group threads only. null when the thread carries no last message, so the
	 * row keeps its participants line.
	 */
	export function conversationPreview(
		thread: Thread,
		currentUserId: string | null
	): string | null {
		const message = thread.last_message
		if (!message) return null
		const text = contentPartsToText(message.content).replace(/\s+/g, ' ').trim()
		const body = text || attachmentLabel(message)
		if (!body) return null
		const sender =
			threadKind(thread) === 'group' ? senderLabel(thread, message, currentUserId) : null
		return sender ? `${sender}: ${body}` : body
	}
</script>

<script lang="ts">
	import { api } from '$lib/api/client'
	import {
		archiveThread,
		deleteThread,
		setThreadMuted,
		THREAD_ORIGINATED_TOGGLE,
	} from '$lib/chat/threadActions'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import Bell from '$lib/components/icons/Bell.svelte'
	import BellSlash from '$lib/components/icons/BellSlash.svelte'
	import ChatCheck from '$lib/components/icons/ChatCheck.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import SignOut from '$lib/components/icons/SignOut.svelte'
	import ConversationAvatar from '$lib/components/messages/ConversationAvatar.svelte'
	import ChatPropertiesModal from '$lib/components/modals/ChatPropertiesModal.svelte'
	import { MenuItem, MenuSeparator } from '$lib/components/primitives'
	import PersonRowMenu from '$lib/components/social/PersonRowMenu.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { chat, type Thread } from '$lib/stores/chat.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { messages } from '$lib/stores/messages.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { showError } from '$lib/stores/notifications.svelte'
	import {
		canDeleteAccessLevel,
		canEditAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { conversationDisplay } from '$lib/utils/conversationDisplay'

	interface Props {
		thread: Thread
		selected?: boolean
		unreadCount: number
		/** every row but the first in its card draws the hairline above itself. */
		dividerAbove?: boolean
		onOpen: (threadId: string) => void
		onRemoved: (threadId: string) => void
	}

	let {
		thread,
		selected = false,
		unreadCount,
		dividerAbove = false,
		onOpen,
		onRemoved,
	}: Props = $props()

	const display = $derived(conversationDisplay(thread, session.currentUserId))
	// composing wins the line: it is the newer thing to know, and it goes away
	// on its own the moment the message lands or the signal expires.
	const typingLine = $derived(
		typingPreview(thread, chat.composingUserIds(thread.id), session.currentUserId)
	)
	const previewLine = $derived(
		typingLine ?? conversationPreview(thread, session.currentUserId) ?? display.subtitle ?? ''
	)
	const hasUnread = $derived(unreadCount > 0)
	const isMuted = $derived(messages.isMuted(thread.id))
	const accessLevel = $derived(resourceAccess.level('thread', thread.id, thread.owner_id))
	const canEdit = $derived(canEditAccessLevel(accessLevel))
	const canDelete = $derived(canDeleteAccessLevel(accessLevel))

	let propertiesOpen = $state(false)

	$effect(() => {
		const accessKey = `${thread.id}:${resourceAccess.version}`
		if (accessKey) void resourceAccess.ensure('thread', thread.id, thread.owner_id)
	})

	async function markRead(): Promise<void> {
		await chat.markThreadRead(thread.id)
		await chat.fetchUnreadCounts()
	}

	async function toggleMute(): Promise<void> {
		const next = await setThreadMuted(thread.id, !isMuted)
		if (next === null) return
		messages.applyMuted(thread.id, next)
	}

	async function archive(): Promise<void> {
		if (await archiveThread(thread.id)) onRemoved(thread.id)
	}

	function share(): void {
		modals.open('resource-access', {
			resourceType: 'thread',
			resourceId: thread.id,
			title: display.title,
		})
	}

	function leave(): void {
		const userId = session.currentUserId
		if (!userId) return
		modals.open('confirm-delete', {
			title: 'leave conversation?',
			description: display.title,
			confirmLabel: 'leave',
			pendingLabel: 'leaving',
			confirmIcon: SignOut,
			onDelete: async () => {
				const { error } = await api.DELETE(
					'/v1/threads/{thread_id}/participants/users/{user_id}',
					{ params: { path: { thread_id: thread.id, user_id: userId } } }
				)
				if (error) {
					showError('could not leave conversation')
					return false
				}
				onRemoved(thread.id)
				return true
			},
		})
	}

	async function remove(deleteOriginatedResources: boolean): Promise<boolean> {
		const status = await deleteThread(thread.id, { deleteOriginatedResources })
		if (status !== 204) return false
		onRemoved(thread.id)
		return true
	}

	function handleKeyDown(event: KeyboardEvent): void {
		if (event.key !== 'Enter' && event.key !== ' ') return
		event.preventDefault()
		onOpen(thread.id)
	}
</script>

<div class="group/row relative min-w-0" role="listitem" data-row>
	{#if dividerAbove}
		<span
			class="bg-foreground/10 pointer-events-none absolute top-0 right-0 left-17 h-px"
			aria-hidden="true"
		></span>
	{/if}

	<div
		role="button"
		tabindex="0"
		class="hover:bg-interactive-hover flex w-full min-w-0 cursor-pointer items-center gap-3 py-2.5 pl-3 text-left transition-colors duration-200 {device.isMobile
			? 'pr-14'
			: 'pr-3'} {isMuted ? 'opacity-65' : ''}"
		style={selected ? 'background-color: rgb(var(--accent-rgb) / 0.3);' : ''}
		onclick={() => onOpen(thread.id)}
		onkeydown={handleKeyDown}
	>
		<ConversationAvatar faces={display.faces} isGroup={display.isGroup} />

		<div class="flex min-w-0 flex-1 flex-col gap-0.5">
			<div class="flex min-w-0 items-baseline gap-2">
				<span
					class="text-foreground min-w-0 flex-1 truncate text-sm {hasUnread
						? 'font-semibold'
						: 'font-medium'}"
				>
					{display.title}
				</span>
				{#if isMuted}
					<BellSlash
						variant="solid"
						class="text-foreground/40 size-3.5 shrink-0 self-center"
					/>
				{/if}
				<Timestamp
					timestamp={new Date(thread.last_activity_at)}
					mode="relative"
					minUnit="hour"
					className="text-foreground/40 shrink-0 text-[0.7rem]"
				/>
			</div>
			<div class="flex min-w-0 items-center gap-2">
				<span
					class="min-w-0 flex-1 truncate text-xs {hasUnread
						? 'text-foreground/70 font-medium'
						: 'text-foreground/50'}"
					data-preview
				>
					{#if typingLine}
						<ShimmerText className="text-xs">{typingLine}</ShimmerText>
					{:else}
						{previewLine}
					{/if}
				</span>
				{#if hasUnread}
					<span
						class="bg-(--accent-primary) flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1.5 text-[0.7rem] font-semibold text-white"
					>
						{unreadCount > 99 ? '99+' : unreadCount}
					</span>
				{/if}
			</div>
		</div>
	</div>

	<!-- pointer mode reserves no space for the menu: it overlays the row's right
	     edge on hover or focus, the way the chat sidebar's rows do. touch keeps
	     the button in view, with the row padded to leave it room. -->
	<div
		data-row-actions
		class={device.isMobile
			? 'absolute inset-y-0 right-0 flex items-center pr-1.5'
			: 'from-background/95 pointer-events-none absolute inset-y-0 right-0 flex items-center bg-linear-to-l to-transparent pr-1.5 pl-6 opacity-0 transition-opacity duration-150 group-focus-within/row:pointer-events-auto group-focus-within/row:opacity-100 group-hover/row:pointer-events-auto group-hover/row:opacity-100'}
	>
		<PersonRowMenu label="conversation actions">
			{#snippet children(close)}
				{#if hasUnread}
					<MenuItem
						icon={ChatCheck}
						onclick={(event) => {
							event.stopPropagation()
							close()
							void markRead()
						}}
					>
						mark as read
					</MenuItem>
				{/if}
				<MenuItem
					icon={isMuted ? Bell : BellSlash}
					onclick={(event) => {
						event.stopPropagation()
						close()
						void toggleMute()
					}}
				>
					{isMuted ? 'unmute' : 'mute'}
				</MenuItem>
				<MenuItem
					icon={ArchiveBox}
					onclick={(event) => {
						event.stopPropagation()
						close()
						void archive()
					}}
				>
					archive
				</MenuItem>
				{#if canEdit}
					<MenuItem
						icon={InfoCircle}
						onclick={(event) => {
							event.stopPropagation()
							close()
							propertiesOpen = true
						}}
					>
						properties
					</MenuItem>
				{/if}
				<MenuItem
					icon={Share}
					onclick={(event) => {
						event.stopPropagation()
						close()
						share()
					}}
				>
					share
				</MenuItem>
				{#if display.isGroup}
					<MenuSeparator />
					<MenuItem
						destructive
						icon={SignOut}
						onclick={(event) => {
							event.stopPropagation()
							close()
							leave()
						}}
					>
						leave
					</MenuItem>
				{/if}
				{#if canDelete}
					{#if !display.isGroup}
						<MenuSeparator />
					{/if}
					<DeleteButton
						confirm={true}
						stopPropagation={true}
						onTrigger={close}
						modalText={{
							title: 'delete conversation?',
							description: display.title,
						}}
						modalToggle={THREAD_ORIGINATED_TOGGLE}
						onDelete={remove}
					/>
				{/if}
			{/snippet}
		</PersonRowMenu>
	</div>
</div>

<ChatPropertiesModal open={propertiesOpen} {thread} onClose={() => (propertiesOpen = false)} />
