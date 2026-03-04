export type ModalId =
	| 'add-friends'
	| 'archived-chats'
	| 'create-group'
	| 'memories'
	| 'share-resource'
	| 'confirm-delete'

export type ShareResourcePayload = {
	resource: 'thread'
	id: string
	title: string | null
}

export type ConfirmDeletePayload = {
	title: string
	description?: string
	onDelete: () => void | boolean | Promise<void | boolean>
}

class ModalStore {
	active = $state<ModalId | null>(null)
	shareResourcePayload = $state<ShareResourcePayload | null>(null)
	confirmDeletePayload = $state<ConfirmDeletePayload | null>(null)
	isOpen = (id: ModalId) => this.active === id
	open(id: 'add-friends'): void
	open(id: 'archived-chats'): void
	open(id: 'create-group'): void
	open(id: 'memories'): void
	open(id: 'share-resource', payload: ShareResourcePayload): void
	open(id: 'confirm-delete', payload: ConfirmDeletePayload): void
	open(id: ModalId, payload?: ShareResourcePayload | ConfirmDeletePayload): void {
		this.active = id
		if (id === 'share-resource') {
			if (!payload) throw new Error('share-resource modal requires a payload')
			this.shareResourcePayload = payload as ShareResourcePayload
			return
		}
		if (id === 'confirm-delete') {
			if (!payload) throw new Error('confirm-delete modal requires a payload')
			this.confirmDeletePayload = payload as ConfirmDeletePayload
			return
		}
		this.shareResourcePayload = null
	}
	close = () => {
		this.active = null
		this.shareResourcePayload = null
		this.confirmDeletePayload = null
	}
}

export const modals = new ModalStore()
