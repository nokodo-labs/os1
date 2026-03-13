/**
 * files store - manages uploaded/created files with API persistence.
 *
 * this is the single source of truth for all file operations:
 * - listing, caching, and managing file records
 * - blob fetching and downloading
 * - thumbnail management
 * - media type classification
 *
 * cache strategy:
 * - generous TTL (10 min) with automatic refresh on API calls
 * - stale data is still displayed while fetching fresh data
 * - thumbnail blob URLs managed centrally (loaded on demand, revoked on clear)
 */

import { browser } from '$app/environment'
import { apiClient } from '$lib/api/client'
import { getApiOrigin } from '$lib/api/origin'
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import type { AttachmentMediaCategory } from '$lib/chat/types'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'

export type ApiFile = components['schemas']['File']

export interface FileResource {
	id: string
	type: 'file'
	title: string
	href: string
	updatedAt: number
	createdAt: number
	meta: {
		file_type: string
		file_size: number
		mime_type: string
		category: AttachmentMediaCategory
		source: string
	}
}

// --- file utilities ---

/** classify a MIME type into a rendering category */
export function categorizeMediaType(mediaType: string): AttachmentMediaCategory {
	if (mediaType.startsWith('image/')) return 'image'
	if (mediaType.startsWith('audio/')) return 'audio'
	if (mediaType.startsWith('video/')) return 'video'
	return 'file'
}

/**
 * fetch a URL with authentication and return a blob object URL.
 * used for rendering media from authenticated API endpoints in <img>/<video>/<audio> tags.
 */
export async function fetchAuthenticatedBlob(url: string): Promise<string> {
	const { getAccessToken } = await import('$lib/auth/session.svelte')
	const token = getAccessToken()
	const response = await fetch(url, {
		credentials: 'include',
		headers: token ? { Authorization: `Bearer ${token}` } : {},
	})
	if (!response.ok) throw new Error(`failed to fetch media: ${response.status}`)
	const blob = await response.blob()
	return URL.createObjectURL(blob)
}

/**
 * download a file by its id from the API.
 * creates a temporary link and triggers a browser download.
 */
export async function downloadFile(fileId: string, filename?: string): Promise<void> {
	const url = `${getApiOrigin()}/v1/files/${fileId}/content?force_download=true`
	const blobUrl = await fetchAuthenticatedBlob(url)
	const a = document.createElement('a')
	a.href = blobUrl
	a.download = filename ?? 'download'
	document.body.appendChild(a)
	a.click()
	document.body.removeChild(a)
	URL.revokeObjectURL(blobUrl)
}

// --- cache state ---

const CACHE_TTL_MS = 10 * 60 * 1000 // 10 minutes
const PAGE_SIZE = 50

const filesMap = new SvelteMap<string, ApiFile>()
let fetchedAt = $state<number | null>(null)
let isLoading = $state(false)
let isLoadingMore = $state(false)
let hasMore = $state(true)
let inFlight: Promise<ApiFile[]> | null = null

/** blob URLs for file thumbnails - revoked on clear */
const thumbnailUrls = new SvelteMap<string, string>()
/** tracks in-flight thumbnail loads to avoid duplicates (non-reactive by design) */
const thumbnailLoading = new SvelteSet<string>()

function isFresh(): boolean {
	return fetchedAt !== null && Date.now() - fetchedAt < CACHE_TTL_MS
}

export function apiFileToResource(file: ApiFile): FileResource {
	const mime = file.mime_type ?? 'application/octet-stream'
	const category = categorizeMediaType(mime)
	return {
		id: file.id,
		type: 'file',
		title: file.filename || 'untitled file',
		href: '#',
		updatedAt: Date.parse(file.updated_at),
		createdAt: Date.parse(file.created_at),
		meta: {
			file_type: mime.split('/')[0] ?? 'file',
			file_size: file.size_bytes ?? 0,
			mime_type: mime,
			category,
			source: file.source,
		},
	}
}

export const files = {
	get hydrated() {
		return fetchedAt !== null
	},
	get loading() {
		return isLoading
	},
	get loadingMore() {
		return isLoadingMore
	},
	get hasMore() {
		return hasMore
	},

	/** all cached files */
	get all(): ApiFile[] {
		return [...filesMap.values()]
	},

	/** all files as resource items */
	get resources(): FileResource[] {
		return this.all.map(apiFileToResource)
	},

	/** thumbnail blob URL for a given file id (if loaded) */
	getThumbnailUrl(fileId: string): string | undefined {
		return thumbnailUrls.get(fileId)
	},

	/** check if a thumbnail is available */
	hasThumbnail(fileId: string): boolean {
		return thumbnailUrls.has(fileId)
	},

	/**
	 * ensure a single file is in the cache. fetches from API if missing.
	 * returns the cached record, or null if the file doesn't exist.
	 */
	async ensure(fileId: string): Promise<ApiFile | null> {
		const cached = filesMap.get(fileId)
		if (cached) return cached
		const file = await fetchSingleFile(fileId)
		if (file) {
			filesMap.set(file.id, file)
			if (fetchedAt === null) fetchedAt = Date.now()
		}
		return file
	},

	/**
	 * load thumbnail for a file (if it's an image).
	 * no-op if already loaded or loading.
	 */
	async loadThumbnail(fileId: string): Promise<void> {
		if (thumbnailUrls.has(fileId) || thumbnailLoading.has(fileId)) return
		const file = filesMap.get(fileId)
		if (!file) return
		const mime = file.mime_type ?? ''
		if (categorizeMediaType(mime) !== 'image') return

		thumbnailLoading.add(fileId)
		try {
			const url = `${getApiOrigin()}/v1/files/${fileId}/content`
			const blobUrl = await fetchAuthenticatedBlob(url)
			thumbnailUrls.set(fileId, blobUrl)
		} catch {
			// thumbnail load failed, skip
		} finally {
			thumbnailLoading.delete(fileId)
		}
	},

	/** load thumbnails for multiple files (images only) */
	async loadThumbnails(fileIds: string[]): Promise<void> {
		await Promise.allSettled(fileIds.map((id) => this.loadThumbnail(id)))
	},

	/** revoke all thumbnail blob URLs */
	revokeThumbnails(): void {
		for (const url of thumbnailUrls.values()) {
			URL.revokeObjectURL(url)
		}
		thumbnailUrls.clear()
	},

	async load(options?: { force?: boolean }): Promise<ApiFile[]> {
		const force = options?.force ?? false
		if (!force && isFresh()) {
			isLoading = false
			return this.all
		}

		if (inFlight) return inFlight

		isLoading = true
		inFlight = (async () => {
			const { data, error } = await apiClient().GET('/v1/files', {
				params: {
					query: { limit: PAGE_SIZE, skip: 0, sort_by: 'created_at', sort_dir: 'desc' },
				},
			})
			if (error || !data) return this.all

			filesMap.clear()
			const items = data as ApiFile[]
			for (const file of items) {
				filesMap.set(file.id, file)
			}
			hasMore = items.length >= PAGE_SIZE
			fetchedAt = Date.now()
			return this.all
		})()

		try {
			return await inFlight
		} finally {
			inFlight = null
			isLoading = false
		}
	},

	/** load the next page of files (for infinite scroll) */
	async loadMore(): Promise<void> {
		if (isLoadingMore || !hasMore) return

		isLoadingMore = true
		try {
			const skip = filesMap.size
			const { data, error } = await apiClient().GET('/v1/files', {
				params: {
					query: {
						limit: PAGE_SIZE,
						skip,
						sort_by: 'created_at',
						sort_dir: 'desc',
					},
				},
			})
			if (error || !data) return

			const items = data as ApiFile[]
			for (const file of items) {
				filesMap.set(file.id, file)
			}
			hasMore = items.length >= PAGE_SIZE
		} finally {
			isLoadingMore = false
		}
	},

	get(fileId: string): ApiFile | null {
		return filesMap.get(fileId) ?? null
	},

	async remove(fileId: string): Promise<boolean> {
		const existing = filesMap.get(fileId)
		if (!existing) return false

		// optimistic delete
		filesMap.delete(fileId)

		// revoke thumbnail if exists
		const thumbUrl = thumbnailUrls.get(fileId)
		if (thumbUrl) {
			URL.revokeObjectURL(thumbUrl)
			thumbnailUrls.delete(fileId)
		}

		const { error } = await apiClient().DELETE('/v1/files/{file_id}', {
			params: { path: { file_id: fileId } },
		})

		if (error) {
			// rollback on failure
			filesMap.set(fileId, existing)
			return false
		}
		return true
	},

	/** upload a file via multipart form data. returns the new ApiFile on success. */
	async upload(file: File): Promise<ApiFile> {
		const form = new FormData()
		form.append('file', file)
		const { getAccessToken } = await import('$lib/auth/session.svelte')
		const token = getAccessToken()
		const response = await fetch(`${getApiOrigin()}/v1/files`, {
			method: 'POST',
			credentials: 'include',
			headers: token ? { Authorization: `Bearer ${token}` } : {},
			body: form,
		})
		if (!response.ok) throw new Error(`upload failed: ${response.status}`)
		const created = (await response.json()) as ApiFile
		filesMap.set(created.id, created)
		return created
	},

	/** clear all cached data */
	clear(): void {
		this.revokeThumbnails()
		filesMap.clear()
		fetchedAt = null
	},

	/** mark cache stale so next access triggers a refetch (keeps thumbnails). */
	invalidate(): void {
		fetchedAt = null
	},
}

// --- event stream integration ---

let filesUnsub: (() => void) | null = null

async function fetchSingleFile(fileId: string): Promise<ApiFile | null> {
	const { data, error } = await apiClient().GET('/v1/files/{file_id}', {
		params: { path: { file_id: fileId } },
	})
	if (error || !data) return null
	return data as ApiFile
}

function handleFileEvent(message: StreamMessage): void {
	const data = message.data as Record<string, unknown> | undefined
	if (!data) return

	if (message.type === 'file.created') {
		const fileId = data.file_id as string
		if (!fileId) return
		// fetch full file record from API and add to cache
		fetchSingleFile(fileId).then((file) => {
			if (file) filesMap.set(file.id, file)
			if (fetchedAt === null) fetchedAt = Date.now()
		})
	} else if (message.type === 'file.updated') {
		const fileId = data.file_id as string
		if (!fileId) return
		// refetch the full file record to get the latest state
		fetchSingleFile(fileId).then((file) => {
			if (file) {
				filesMap.set(file.id, file)
				// invalidate cached thumbnail so it can be reloaded
				const thumbUrl = thumbnailUrls.get(file.id)
				if (thumbUrl) {
					URL.revokeObjectURL(thumbUrl)
					thumbnailUrls.delete(file.id)
				}
			}
		})
	} else if (message.type === 'file.deleted') {
		const fileId = data.file_id as string
		if (!fileId) return
		filesMap.delete(fileId)
		// revoke thumbnail if exists
		const thumbUrl = thumbnailUrls.get(fileId)
		if (thumbUrl) {
			URL.revokeObjectURL(thumbUrl)
			thumbnailUrls.delete(fileId)
		}
	}
}

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			if (!filesUnsub) {
				filesUnsub = eventStreamClient.subscribe(handleFileEvent)
			}
		} else {
			filesUnsub?.()
			filesUnsub = null
			files.clear()
		}
	})

	// subscribe immediately if already authenticated
	if (getAccessToken() && !filesUnsub) {
		filesUnsub = eventStreamClient.subscribe(handleFileEvent)
	}
}
