import type { Component } from 'svelte'

export type ModalId =
	| 'add-friends'
	| 'archived-chats'
	| 'create-group'
	| 'memories'
	| 'confirm-delete'
	| 'file-details'
	| 'note-properties'
	| 'resource-access'

/** opt-in switch rendered inside the confirm dialog, above the confirm button. */
export type ConfirmDeleteToggle = {
	label: string
	description?: string
	/** starting state of the switch. off unless set. */
	default?: boolean
}

export type ConfirmDeletePayload = {
	title: string
	description?: string
	/** verb for the confirm button, when "delete" is not what happens. */
	confirmLabel?: string
	/** verb shown while the action runs. */
	pendingLabel?: string
	/** icon for the confirm button, when a trash can is not what happens. */
	confirmIcon?: Component<{ class?: string }>
	/** optional opt-in switch. its state is handed to onDelete. */
	toggle?: ConfirmDeleteToggle
	onDelete: (toggleOn: boolean) => void | boolean | Promise<void | boolean>
}

export type FileDetailsPayload = {
	fileId: string
}

export type NotePropertiesPayload = {
	noteId: string
}

export type ResourceAccessPayload = {
	resourceType:
		| 'thread'
		| 'file'
		| 'project'
		| 'group'
		| 'agent'
		| 'note'
		| 'reminder_list'
		| 'calendar'
	resourceId: string
	title: string
}

class ModalStore {
	active = $state<ModalId | null>(null)
	confirmDeletePayload = $state<ConfirmDeletePayload | null>(null)
	fileDetailsPayload = $state<FileDetailsPayload | null>(null)
	notePropertiesPayload = $state<NotePropertiesPayload | null>(null)
	resourceAccessPayload = $state<ResourceAccessPayload | null>(null)
	isOpen = (id: ModalId) => this.active === id
	open(id: 'add-friends'): void
	open(id: 'archived-chats'): void
	open(id: 'create-group'): void
	open(id: 'memories'): void
	open(id: 'confirm-delete', payload: ConfirmDeletePayload): void
	open(id: 'file-details', payload: FileDetailsPayload): void
	open(id: 'note-properties', payload: NotePropertiesPayload): void
	open(id: 'resource-access', payload: ResourceAccessPayload): void
	open(
		id: ModalId,
		payload?:
			| ConfirmDeletePayload
			| FileDetailsPayload
			| NotePropertiesPayload
			| ResourceAccessPayload
	): void {
		this.active = id
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
		if (id === 'note-properties') {
			if (!payload) throw new Error('note-properties modal requires a payload')
			this.notePropertiesPayload = payload as NotePropertiesPayload
			return
		}
		if (id === 'resource-access') {
			if (!payload) throw new Error('resource-access modal requires a payload')
			this.resourceAccessPayload = payload as ResourceAccessPayload
			return
		}
	}
	close = () => {
		this.active = null
		this.confirmDeletePayload = null
		this.fileDetailsPayload = null
		this.notePropertiesPayload = null
		this.resourceAccessPayload = null
	}
}

export const modals = new ModalStore()
