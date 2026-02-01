export type ModalId = 'settings' | 'archived-chats'

class ModalStore {
	active = $state<ModalId | null>(null)
	isOpen = (id: ModalId) => this.active === id
	open = (id: ModalId) => (this.active = id)
	close = () => (this.active = null)
}

export const modals = new ModalStore()
