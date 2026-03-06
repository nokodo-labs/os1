export type ModalId =
	| 'add-friends'
	| 'archived-chats'
	| 'create-group'
	| 'memories'
	| 'share-resource'
	| 'confirm-delete'
	| 'file-details'
	| 'resource-access'

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

export type FileDetailsPayload = {
	fileId: string
}

export type ResourceAccessPayload = {
	resourceType: 'thread' | 'file' | 'project' | 'group' | 'agent' | 'note' | 'reminder_list'
	resourceId: string
	title: string
}

class ModalStore {
	active = $state<ModalId | null>(null)
	shareResourcePayload = $state<ShareResourcePayload | null>(null)
	confirmDeletePayload = $state<ConfirmDeletePayload | null>(null)
	fileDetailsPayload = $state<FileDetailsPayload | null>(null)
	resourceAccessPayload = $state<ResourceAccessPayload | null>(null)
	isOpen = (id: ModalId) => this.active === id
	open(id: 'add-friends'): void
	open(id: 'archived-chats'): void
	open(id: 'create-group'): void
	open(id: 'memories'): void
	open(id: 'share-resource', payload: ShareResourcePayload): void
	open(id: 'confirm-delete', payload: ConfirmDeletePayload): void
	open(id: 'file-details', payload: FileDetailsPayload): void
	open(id: 'resource-access', payload: ResourceAccessPayload): void
	open(
		id: ModalId,
		payload?:
			| ShareResourcePayload
			| ConfirmDeletePayload
			| FileDetailsPayload
			| ResourceAccessPayload
	): void {
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
		if (id === 'file-details') {
			if (!payload) throw new Error('file-details modal requires a payload')
			this.fileDetailsPayload = payload as FileDetailsPayload
			return
		}
		if (id === 'resource-access') {
			if (!payload) throw new Error('resource-access modal requires a payload')
			this.resourceAccessPayload = payload as ResourceAccessPayload
			return
		}
		this.shareResourcePayload = null
	}
	close = () => {
		this.active = null
		this.shareResourcePayload = null
		this.confirmDeletePayload = null
		this.fileDetailsPayload = null
		this.resourceAccessPayload = null
	}
}

export const modals = new ModalStore()
