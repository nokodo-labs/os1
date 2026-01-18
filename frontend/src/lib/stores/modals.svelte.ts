export type ModalId = 'settings' | 'archived-chats'

export let activeModal = $state<ModalId | null>(null)

export function openModal(modal: ModalId) {
	activeModal = modal
}

export function closeModal() {
	activeModal = null
}
