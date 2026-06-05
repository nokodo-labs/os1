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
import { api } from '$lib/api/client'
import { getApiOrigin } from '$lib/api/origin'
import type { StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import type { AttachmentMediaCategory } from '$lib/chat/types'
import {
	STORE_EVENT_TYPES,
	storeEventData,
	storeEventString,
	subscribeToStoreEvents,
} from '$lib/stores/storeEvents'
import { describeFileType } from '$lib/utils/fileTypes'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'

export type ApiFile = components['schemas']['File']
export type FileCategoryFilter = components['schemas']['FileCategoryFilter']
export type FileCounts = components['schemas']['FileCounts']
export type FileSourceFilter = components['schemas']['FileSource']

export interface FileLoadOptions {
	force?: boolean
	projectId?: string | null
	source?: FileSourceFilter | null
	category?: FileCategoryFilter | null
	resolveOrigin?: boolean
}

export interface FileEnsureOptions {
	force?: boolean
	resolveOrigin?: boolean
}

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
		owner_id: string
		project_ids: string[]
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
async function fetchAuthenticatedMediaBlob(url: string, mediaType?: string): Promise<Blob> {
	const { getAccessToken } = await import('$lib/auth/session.svelte')
	const token = getAccessToken()
	const response = await fetch(url, {
		credentials: 'include',
		headers: token ? { Authorization: `Bearer ${token}` } : {},
	})
	if (!response.ok) throw new Error(`failed to fetch media: ${response.status}`)
	const responseBlob = await response.blob()
	return mediaType ? new Blob([responseBlob], { type: mediaType }) : responseBlob
}

export async function fetchAuthenticatedBlob(url: string, mediaType?: string): Promise<string> {
	const blob = await fetchAuthenticatedMediaBlob(url, mediaType)
	return URL.createObjectURL(blob)
}

/**
 * download a file by its id from the API.
 * creates a temporary link and triggers a browser download.
 */
export async function downloadFile(fileId: string, filename?: string): Promise<void> {
	const url = `${getApiOrigin()}/v1/files/${fileId}/content?download=true`
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
const EMPTY_FILE_COUNTS: Required<FileCounts> = {
	total: 0,
	owned_total: 0,
	shared_total: 0,
	by_category: {},
	by_source: {},
}
const MAX_THUMBNAIL_REQUESTS = 4

const filesMap = new SvelteMap<string, ApiFile>()
const fileCountCache = new SvelteMap<string, { data: FileCounts; fetchedAt: number }>()
let fetchedAt = $state<number | null>(null)
let fetchedKey = $state('')
let fileListHydrated = false
let fileCountsHydrated = false
let isLoading = $state(false)
let isLoadingMore = $state(false)
let isLoadingCounts = $state(false)
let hasMore = $state(true)
let inFlight: Promise<ApiFile[]> | null = null
let inFlightKey = ''
let countInFlight: Promise<FileCounts> | null = null
let countInFlightKey = ''
let lastLoadOptions: FileLoadOptions | undefined
let lastCountOptions: FileLoadOptions | undefined

/** blob URLs for file thumbnails - revoked on clear */
const thumbnailUrls = new SvelteMap<string, string>()
/** tracks in-flight thumbnail loads to avoid duplicates (non-reactive by design) */
const thumbnailLoading = new SvelteSet<string>()
let activeThumbnailRequests = 0
const thumbnailQueue: Array<() => void> = []

async function acquireThumbnailSlot(): Promise<void> {
	if (activeThumbnailRequests < MAX_THUMBNAIL_REQUESTS) {
		activeThumbnailRequests += 1
		return
	}
	await new Promise<void>((resolve) => {
		thumbnailQueue.push(() => {
			activeThumbnailRequests += 1
			resolve()
		})
	})
}

function releaseThumbnailSlot(): void {
	activeThumbnailRequests = Math.max(0, activeThumbnailRequests - 1)
	thumbnailQueue.shift()?.()
}

function isFresh(key: string): boolean {
	return fetchedAt !== null && fetchedKey === key && Date.now() - fetchedAt < CACHE_TTL_MS
}

function areCountsFresh(key: string): boolean {
	const entry = fileCountCache.get(key)
	return Boolean(entry && Date.now() - entry.fetchedAt < CACHE_TTL_MS)
}

function filterKey(options?: FileLoadOptions): string {
	return [
		options?.projectId ?? '',
		options?.source ?? '',
		options?.category ?? '',
		options?.resolveOrigin ? 'origin' : '',
	].join(':')
}

function listQuery(options: FileLoadOptions | undefined, skip: number) {
	return {
		limit: PAGE_SIZE,
		skip,
		sort_by: 'created_at' as const,
		sort_dir: 'desc' as const,
		project_id: options?.projectId ?? undefined,
		source: options?.source ?? undefined,
		category: options?.category ?? undefined,
		resolve_origin: options?.resolveOrigin || undefined,
	}
}

function countQuery(options?: FileLoadOptions) {
	return {
		project_id: options?.projectId ?? undefined,
		source: options?.source ?? undefined,
		category: options?.category ?? undefined,
	}
}

function rememberOptions(options?: FileLoadOptions): FileLoadOptions | undefined {
	if (!options) return undefined
	return {
		projectId: options.projectId,
		source: options.source,
		category: options.category,
		resolveOrigin: options.resolveOrigin,
	}
}

function optionsFromKey(key: string): FileLoadOptions | undefined {
	const [projectId = '', source = '', category = ''] = key.split(':')
	if (!projectId && !source && !category) return undefined
	return {
		projectId: projectId || null,
		source: (source || null) as FileSourceFilter | null,
		category: (category || null) as FileCategoryFilter | null,
		resolveOrigin: false,
	}
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
			file_type: describeFileType(mime, file.filename),
			file_size: file.size_bytes ?? 0,
			mime_type: mime,
			category,
			source: file.source,
			owner_id: file.owner_id,
			project_ids: file.project_ids ?? [],
		},
	}
}

export const files = {
	get hydrated() {
		return fetchedAt !== null
	},
	get hasLoaded() {
		return fileListHydrated || fileCountsHydrated
	},
	get loading() {
		return isLoading
	},
	get loadingMore() {
		return isLoadingMore
	},
	get loadingCounts() {
		return isLoadingCounts
	},
	get hasMore() {
		return hasMore
	},
	get counts(): FileCounts {
		return this.getCounts()
	},

	getCounts(options?: FileLoadOptions): FileCounts {
		return fileCountCache.get(filterKey(options))?.data ?? EMPTY_FILE_COUNTS
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
	async ensure(fileId: string, options?: FileEnsureOptions): Promise<ApiFile | null> {
		const cached = filesMap.get(fileId)
		const force = options?.force ?? false
		const resolveOrigin = options?.resolveOrigin ?? false
		if (cached && !force && (!resolveOrigin || cached.origin_thread_id || !cached.message_id)) {
			return cached
		}
		const file = await fetchSingleFile(fileId, resolveOrigin)
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
		await acquireThumbnailSlot()
		try {
			const url = `${getApiOrigin()}/v1/files/${fileId}/preview`
			const blobUrl = await fetchAuthenticatedBlob(url)
			thumbnailUrls.set(fileId, blobUrl)
		} catch {
			// thumbnail load failed, skip
		} finally {
			releaseThumbnailSlot()
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

	async load(options?: FileLoadOptions): Promise<ApiFile[]> {
		const force = options?.force ?? false
		const key = filterKey(options)
		lastLoadOptions = rememberOptions(options)
		if (!force && isFresh(key)) {
			isLoading = false
			return this.all
		}

		if (inFlight && inFlightKey === key) return inFlight

		isLoading = true
		inFlightKey = key
		inFlight = (async () => {
			const { data, error } = await api.GET('/v1/files', {
				params: { query: listQuery(options, 0) },
			})
			if (error || !data) return this.all

			filesMap.clear()
			const items = data as ApiFile[]
			for (const file of items) {
				filesMap.set(file.id, file)
			}
			hasMore = items.length >= PAGE_SIZE
			fetchedAt = Date.now()
			fetchedKey = key
			fileListHydrated = true
			return this.all
		})()

		try {
			return await inFlight
		} finally {
			inFlight = null
			inFlightKey = ''
			isLoading = false
		}
	},

	async loadCounts(options?: FileLoadOptions): Promise<FileCounts> {
		const key = filterKey(options)
		lastCountOptions = rememberOptions(options)
		if (areCountsFresh(key)) return fileCountCache.get(key)?.data ?? EMPTY_FILE_COUNTS
		if (countInFlight && countInFlightKey === key) return countInFlight

		isLoadingCounts = true
		countInFlightKey = key
		countInFlight = (async () => {
			const { data, error } = await api.GET('/v1/files/count', {
				params: { query: countQuery(options) },
			})
			if (error || !data) return fileCountCache.get(key)?.data ?? EMPTY_FILE_COUNTS
			fileCountCache.set(key, { data, fetchedAt: Date.now() })
			fileCountsHydrated = true
			return data
		})()

		try {
			return await countInFlight
		} finally {
			countInFlight = null
			countInFlightKey = ''
			isLoadingCounts = false
		}
	},

	/** load the next page of files (for infinite scroll) */
	async loadMore(options?: FileLoadOptions): Promise<void> {
		if (isLoadingMore || !hasMore) return
		const key = filterKey(options)
		if (fetchedKey !== key) {
			await this.load(options)
			return
		}

		isLoadingMore = true
		try {
			const skip = filesMap.size
			const { data, error } = await api.GET('/v1/files', {
				params: { query: listQuery(options, skip) },
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

		const { error } = await api.DELETE('/v1/files/{file_id}', {
			params: { path: { file_id: fileId } },
		})

		if (error) {
			// rollback on failure
			filesMap.set(fileId, existing)
			return false
		}
		fileCountCache.clear()
		return true
	},

	/** upload a file via multipart form data. returns the new ApiFile on success. */
	async upload(file: File): Promise<ApiFile> {
		const form = new FormData()
		form.append('file', file)
		const { getAccessToken } = await import('$lib/auth/session.svelte')
		const token = getAccessToken()
		const response = await fetch(`${getApiOrigin()}/v1/files/upload`, {
			method: 'POST',
			credentials: 'include',
			headers: token ? { Authorization: `Bearer ${token}` } : {},
			body: form,
		})
		if (!response.ok) throw new Error(`upload failed: ${response.status}`)
		const created = (await response.json()) as ApiFile
		filesMap.set(created.id, created)
		fileCountCache.clear()
		return created
	},

	/** clear all cached data */
	clear(): void {
		this.revokeThumbnails()
		filesMap.clear()
		fetchedAt = null
		fetchedKey = ''
		fileCountCache.clear()
		fileListHydrated = false
		fileCountsHydrated = false
	},

	/** mark cache stale so next access triggers a refetch (keeps thumbnails). */
	invalidate(): void {
		fetchedAt = null
		fileCountCache.clear()
	},

	async refreshCached(): Promise<void> {
		const tasks: Promise<unknown>[] = []
		if (fileListHydrated) {
			tasks.push(this.load({ ...lastLoadOptions, force: true }))
		}
		if (fileCountsHydrated) {
			for (const key of fileCountCache.keys()) {
				tasks.push(this.loadCounts(optionsFromKey(key)))
			}
			if (fileCountCache.size === 0) tasks.push(this.loadCounts(lastCountOptions))
		}
		await Promise.allSettled(tasks)
	},

	async refresh(): Promise<void> {
		await this.refreshCached()
	},
}

// --- event stream integration ---

let filesUnsub: (() => void) | null = null
const FILE_STREAM_EVENTS = [
	...STORE_EVENT_TYPES.files,
	...STORE_EVENT_TYPES.resourceAccessResource,
] as const

async function fetchSingleFile(fileId: string, resolveOrigin = false): Promise<ApiFile | null> {
	const { data, error } = await api.GET('/v1/files/{file_id}', {
		params: {
			path: { file_id: fileId },
			query: { resolve_origin: resolveOrigin || undefined },
		},
	})
	if (error || !data) return null
	return data as ApiFile
}

function revokeThumbnail(fileId: string): void {
	const thumbUrl = thumbnailUrls.get(fileId)
	if (!thumbUrl) return
	URL.revokeObjectURL(thumbUrl)
	thumbnailUrls.delete(fileId)
}

function refetchSingleFile(fileId: string): void {
	fetchSingleFile(fileId).then((file) => {
		if (file) {
			filesMap.set(file.id, file)
			fileCountCache.clear()
			revokeThumbnail(file.id)
		} else {
			filesMap.delete(fileId)
			fileCountCache.clear()
			revokeThumbnail(fileId)
		}
	})
}

function handleFileEvent(message: StreamMessage): void {
	const data = storeEventData(message)
	if (message.type === 'access.updated' || message.type === 'resource.access.updated') {
		if (data?.resource_type !== 'file' || typeof data.resource_id !== 'string') return
		refetchSingleFile(data.resource_id)
		return
	}

	const fileId = storeEventString(message, ['file_id', 'id'])
	if (!fileId) return

	if (message.type === 'file.created') {
		// fetch full file record from API and add to cache
		fetchSingleFile(fileId).then((file) => {
			if (file) filesMap.set(file.id, file)
			if (fetchedAt === null) fetchedAt = Date.now()
			fileCountCache.clear()
		})
	} else if (
		message.type === 'file.updated' ||
		message.type === 'file.processing' ||
		message.type === 'file.ready'
	) {
		// refetch the full file record to get the latest state
		refetchSingleFile(fileId)
	} else if (message.type === 'file.deleted') {
		filesMap.delete(fileId)
		fileCountCache.clear()
		// revoke thumbnail if exists
		revokeThumbnail(fileId)
	}
}

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			if (!filesUnsub) {
				filesUnsub = subscribeToStoreEvents(FILE_STREAM_EVENTS, handleFileEvent)
			}
		} else {
			filesUnsub?.()
			filesUnsub = null
			files.clear()
		}
	})

	// subscribe immediately if already authenticated
	if (getAccessToken() && !filesUnsub) {
		filesUnsub = subscribeToStoreEvents(FILE_STREAM_EVENTS, handleFileEvent)
	}
}
