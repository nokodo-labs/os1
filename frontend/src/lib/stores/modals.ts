import { writable } from 'svelte/store'

export type ModalId = 'settings' | 'archived-chats'

export const activeModal = writable<ModalId | null>(null)

export function openModal(modal: ModalId) {
	activeModal.set(modal)
}

export function closeModal() {
	activeModal.set(null)
}
