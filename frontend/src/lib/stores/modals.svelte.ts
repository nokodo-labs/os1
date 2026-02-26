export type ModalId =
	| 'add-friends'
	| 'archived-chats'
	| 'create-group'
	| 'memories'
	| 'share-resource'

export type ShareResourcePayload = {
	resource: 'thread'
	id: string
	title: string | null
}

class ModalStore {
	active = $state<ModalId | null>(null)
	shareResourcePayload = $state<ShareResourcePayload | null>(null)
	isOpen = (id: ModalId) => this.active === id
	open(id: 'add-friends'): void
	open(id: 'archived-chats'): void
	open(id: 'create-group'): void
	open(id: 'memories'): void
	open(id: 'share-resource', payload: ShareResourcePayload): void
	open(id: ModalId, payload?: ShareResourcePayload): void {
		this.active = id
		if (id === 'share-resource') {
			if (!payload) throw new Error('share-resource modal requires a payload')
			this.shareResourcePayload = payload
			return
		}
		this.shareResourcePayload = null
	}
	close = () => {
		this.active = null
		this.shareResourcePayload = null
	}
}

export const modals = new ModalStore()
