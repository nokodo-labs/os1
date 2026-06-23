/**
 * resolve sharing + author metadata for a resource straight from the
 * always-available session store, keyed by owner id.
 *
 * widgets render from snapshot ResourceItem objects that only carry raw
 * fields like owner_id. deriving shared/author here means every widget shows
 * the author consistently - picker, attachment tray, citations - and stays
 * reactive when the owner record loads later. the owner is fetched and cached
 * on demand through session.ensureUsers.
 */
import type { ResourceItem } from '$lib/components/widgets/types'
import { session } from '$lib/stores/session.svelte'

export interface ResourceSharing {
	readonly isShared: boolean
	readonly authorMeta: string | null
}

export function resourceSharing(getResource: () => ResourceItem): ResourceSharing {
	const ownerId = $derived(resolveOwnerId(getResource()))
	const isShared = $derived(
		Boolean(session.currentUserId && ownerId && ownerId !== session.currentUserId)
	)
	const authorMeta = $derived(isShared ? session.authorLabel(ownerId) : null)

	$effect(() => {
		if (!isShared || !ownerId) return
		void session.ensureUsers([ownerId])
	})

	return {
		get isShared() {
			return isShared
		},
		get authorMeta() {
			return authorMeta
		},
	}
}

function resolveOwnerId(resource: ResourceItem): string | null {
	const ownerId = resource.meta?.owner_id
	return typeof ownerId === 'string' && ownerId.length > 0 ? ownerId : null
}
