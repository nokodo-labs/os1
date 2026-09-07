<script lang="ts">
	import MessageRequests from '$lib/components/messages/MessageRequests.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { messages } from '$lib/stores/messages.svelte'

	interface Props {
		open: boolean
		onClose: () => void
		onOpenConversation?: (threadId: string) => void
	}

	let { open, onClose, onOpenConversation }: Props = $props()

	// the banner that opens this disappears once the last request is handled,
	// so close with it rather than stranding an empty modal.
	$effect(() => {
		if (open && messages.inviteCount === 0) onClose()
	})
</script>

<BaseModal {open} title="message requests" {onClose} widthClassName="max-w-md">
	<MessageRequests {onOpenConversation} />
</BaseModal>
