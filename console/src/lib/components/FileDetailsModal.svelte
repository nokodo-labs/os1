<script lang="ts">
	import { api, getApiBaseUrl, getAuthHeaders, unwrap, type Schemas } from '$lib/api'

	type File = Schemas['File']

	import AccessRulesButton from '$lib/components/AccessRulesButton.svelte'
	import AclModal from '$lib/components/AclModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Calendar,
		CircleCheck,
		Database,
		Download,
		FileIcon,
		FingerprintPattern,
		FolderOpen,
		HardDrive,
		Hash,
		MessageSquare,
		Package,
		Pencil,
		RotateCcw,
		Server,
		Trash2,
		User,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		file: File | null
		onUpdated?: (file: File) => void
		onDeleted?: (fileId: string) => void
	}

	let { open = $bindable(false), file, onUpdated, onDeleted }: Props = $props()

	let isDownloading = $state(false)
	let downloadError = $state<string | null>(null)
	let confirmDelete = $state(false)
	let confirmWipe = $state(false)
	let isDeleting = $state(false)
	let isRestoring = $state(false)
	let deleteError = $state<string | null>(null)
	let showAclModal = $state(false)
	let isPreviewLoading = $state(false)
	let previewUrl = $state<string | null>(null)
	let previewText = $state<string | null>(null)
	let previewError = $state<string | null>(null)
	let previewLoadToken = 0
	let currentPreviewObjectUrl: string | null = null

	function close() {
		open = false
		confirmDelete = false
		confirmWipe = false
		downloadError = null
		deleteError = null
		clearPreview()
	}

	function clearPreview() {
		if (currentPreviewObjectUrl) {
			URL.revokeObjectURL(currentPreviewObjectUrl)
			currentPreviewObjectUrl = null
		}
		previewUrl = null
		previewText = null
		previewError = null
		isPreviewLoading = false
	}

	function previewKind(target: File): 'image' | 'text' | 'pdf' | 'audio' | 'video' | null {
		const mime = (target.mime_type ?? '').toLowerCase()
		const name = (target.filename ?? '').toLowerCase()
		if (mime.startsWith('image/')) return 'image'
		if (mime.startsWith('audio/')) return 'audio'
		if (mime.startsWith('video/')) return 'video'
		if (mime === 'application/pdf' || name.endsWith('.pdf')) return 'pdf'
		if (
			mime.startsWith('text/') ||
			mime.includes('json') ||
			mime.includes('xml') ||
			name.endsWith('.md') ||
			name.endsWith('.csv') ||
			name.endsWith('.json') ||
			name.endsWith('.txt') ||
			name.endsWith('.yaml') ||
			name.endsWith('.yml')
		) {
			return 'text'
		}
		return null
	}

	async function loadPreview(target: File) {
		const kind = previewKind(target)
		clearPreview()
		if (!kind) return

		const token = ++previewLoadToken
		isPreviewLoading = true
		try {
			const urlResult = unwrap(
				await api.GET('/v1/files/{file_id}/url', {
					params: { path: { file_id: target.id } },
				})
			)

			if (token !== previewLoadToken) return

			if (urlResult.url) {
				if (kind === 'text') {
					const response = await fetch(urlResult.url)
					if (!response.ok) throw new Error(`server returned ${response.status}`)
					previewText = await response.text()
				} else {
					previewUrl = urlResult.url
				}
				return
			}

			const headers = await getAuthHeaders()
			const response = await fetch(`${getApiBaseUrl()}/v1/files/${target.id}/content`, {
				headers,
			})
			if (!response.ok) throw new Error(`server returned ${response.status}`)

			if (token !== previewLoadToken) return

			if (kind === 'text') {
				previewText = await response.text()
			} else {
				const objectUrl = URL.createObjectURL(await response.blob())
				currentPreviewObjectUrl = objectUrl
				previewUrl = objectUrl
			}
		} catch (e) {
			if (token === previewLoadToken) {
				previewError = e instanceof Error ? e.message : 'preview failed'
			}
		} finally {
			if (token === previewLoadToken) isPreviewLoading = false
		}
	}

	$effect(() => {
		const currentFile = file
		if (!open || !currentFile) {
			previewLoadToken += 1
			clearPreview()
			return
		}

		loadPreview(currentFile)
		return () => {
			previewLoadToken += 1
			clearPreview()
		}
	})

	async function download() {
		if (!file) return
		isDownloading = true
		downloadError = null
		try {
			const r = await api.GET('/v1/files/{file_id}/url', {
				params: { path: { file_id: file.id } },
			})
			const { url } = unwrap(r)
			if (url) {
				window.open(url, '_blank', 'noopener,noreferrer')
				return
			}
			const headers = await getAuthHeaders()
			const res = await fetch(
				`${getApiBaseUrl()}/v1/files/${file.id}/content?download=true`,
				{ headers }
			)
			if (!res.ok) throw new Error(`server returned ${res.status}`)
			const blob = await res.blob()
			const objectUrl = URL.createObjectURL(blob)
			const a = document.createElement('a')
			a.href = objectUrl
			a.download = file.filename ?? file.id
			document.body.appendChild(a)
			a.click()
			document.body.removeChild(a)
			URL.revokeObjectURL(objectUrl)
		} catch (e) {
			downloadError = e instanceof Error ? e.message : 'download failed'
		} finally {
			isDownloading = false
		}
	}

	async function deleteFile(permanent = false) {
		if (!file) return
		isDeleting = true
		deleteError = null
		try {
			const r = await api.DELETE('/v1/files/{file_id}', {
				params: {
					path: { file_id: file.id },
					query: permanent ? { permanent: true } : undefined,
				},
			})
			if (r.error) {
				const detail = r.error?.detail
				deleteError = typeof detail === 'string' ? detail : 'failed to delete file'
			} else {
				onDeleted?.(file.id)
				close()
			}
		} catch (e) {
			deleteError = e instanceof Error ? e.message : 'failed to delete file'
		} finally {
			isDeleting = false
		}
	}

	async function restoreFile() {
		if (!file) return
		isRestoring = true
		deleteError = null
		try {
			const updated = unwrap(
				await api.POST('/v1/files/{file_id}/restore', {
					params: { path: { file_id: file.id } },
				})
			)
			file = updated
			onUpdated?.(updated)
		} catch (e) {
			deleteError = e instanceof Error ? e.message : 'failed to restore file'
		} finally {
			isRestoring = false
		}
	}

	function formatBytes(n: number | null | undefined): string {
		if (n == null) return '—'
		if (n < 1024) return `${n} B`
		if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
		if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
		return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
	}

	// parse storage key into something human-readable
	function storageInfo(
		backend: string,
		key: string
	): { label: string; path: string; filename: string | null } {
		const isS3 = backend === 's3' || backend.includes('s3')
		if (isS3) {
			// key format may be "bucket/path/file.ext" or just the object key
			const slash = key.indexOf('/')
			if (slash !== -1) {
				return { label: 's3', path: key.substring(slash + 1), filename: null }
			}
			return { label: 's3', path: key, filename: null }
		}
		// filesystem: key is typically a relative or absolute path
		const lastSlash = Math.max(key.lastIndexOf('/'), key.lastIndexOf('\\'))
		if (lastSlash !== -1) {
			return {
				label: 'filesystem',
				path: key.substring(0, lastSlash) || '/',
				filename: key.substring(lastSlash + 1),
			}
		}
		return { label: 'filesystem', path: '/', filename: key }
	}

	function statusColor(status: string): string {
		switch (status) {
			case 'ready':
				return 'text-emerald-400'
			case 'processing':
				return 'text-yellow-400'
			case 'error':
			case 'failed':
				return 'text-red-400'
			default:
				return 'text-zinc-400'
		}
	}
</script>

<Dialog.Root
	bind:open
	onOpenChange={(v) => {
		if (!v) close()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			data-dialog-content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2rem)] min-w-80 -translate-x-1/2 -translate-y-1/2 flex-col overflow-auto rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-xl"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div class="flex min-w-0 flex-1 items-center gap-3">
					<div
						class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-zinc-800"
					>
						<FileIcon class="h-4 w-4 text-zinc-400" />
					</div>
					<div class="min-w-0">
						<Dialog.Title class="truncate text-base font-semibold">
							{file?.filename ?? '(no filename)'}
						</Dialog.Title>
						<Dialog.Description class="text-xs text-zinc-500"
							>file details</Dialog.Description
						>
					</div>
				</div>
				<div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
					{#if file}
						<AccessRulesButton
							type="button"
							variant="outline"
							size="sm"
							onclick={() => (showAclModal = true)}
						/>
					{/if}
					<Button
						variant="outline"
						size="sm"
						class="gap-1.5 rounded-xl"
						onclick={download}
						disabled={isDownloading || !file}
					>
						<Download class="h-3.5 w-3.5" />
						{isDownloading ? 'getting url...' : 'download'}
					</Button>
					<Button variant="ghost" size="icon" class="shrink-0 rounded-xl" onclick={close}>
						<X class="h-4 w-4" />
					</Button>
				</div>
			</div>

			{#if file}
				{@const si = storageInfo(file.storage_backend, file.storage_key)}
				{@const currentPreviewKind = previewKind(file)}
				<div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-5">
					{#if downloadError}
						<div
							class="rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-xs text-red-300"
						>
							{downloadError}
						</div>
					{/if}

					{#if file.deleted_at}
						<div
							class="flex items-center gap-2 rounded-xl border border-red-900/30 bg-red-900/10 px-4 py-2.5 text-sm text-red-300"
						>
							<Trash2 class="h-4 w-4 shrink-0" />
							deleted {new Date(file.deleted_at).toLocaleString()}
						</div>
					{/if}

					{#if currentPreviewKind}
						<section class="rounded-2xl border border-zinc-800 bg-zinc-900/30 p-4">
							<div class="mb-3 flex items-center justify-between gap-3">
								<div>
									<h3 class="text-sm font-semibold text-zinc-200">preview</h3>
									<p class="text-xs text-zinc-500">{currentPreviewKind}</p>
								</div>
								<CircleCheck class="h-4 w-4 text-emerald-400" />
							</div>

							{#if isPreviewLoading}
								<div
									class="rounded-xl border border-zinc-800 bg-zinc-950/50 p-6 text-center text-sm text-zinc-500"
								>
									loading preview...
								</div>
							{:else if previewError}
								<div
									class="rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-xs text-red-300"
								>
									{previewError}
								</div>
							{:else if currentPreviewKind === 'text'}
								<pre
									class="max-h-96 overflow-auto rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-xs whitespace-pre-wrap text-zinc-300">{previewText ??
										''}</pre>
							{:else if previewUrl && currentPreviewKind === 'image'}
								<img
									src={previewUrl}
									alt="file preview"
									class="max-h-96 w-full rounded-xl border border-zinc-800 bg-zinc-950 object-contain"
								/>
							{:else if previewUrl && currentPreviewKind === 'pdf'}
								<iframe
									src={previewUrl}
									title="file preview"
									class="h-96 w-full rounded-xl border border-zinc-800 bg-zinc-950"
								></iframe>
							{:else if previewUrl && currentPreviewKind === 'audio'}
								<audio controls src={previewUrl} class="w-full"></audio>
							{:else if previewUrl && currentPreviewKind === 'video'}
								<video
									controls
									src={previewUrl}
									class="max-h-96 w-full rounded-xl border border-zinc-800 bg-black"
								>
									<track kind="captions" />
								</video>
							{/if}
						</section>
					{/if}

					<!-- identity -->
					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							identity
						</p>
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<Hash class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">file id</span>
								<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
									>{file.id}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<User class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">owner</span>
								<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
									>{file.owner_id}</span
								>
							</div>
							{#if file.project_ids && file.project_ids.length > 0}
								<div
									class="flex flex-col border-b border-zinc-800/60 transition-colors"
								>
									{#each file.project_ids as pid (pid)}
										<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
											<Package class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
											<span class="w-24 shrink-0 text-xs text-zinc-500"
												>project</span
											>
											<span
												class="min-w-0 truncate font-mono text-xs text-zinc-300"
												>{pid}</span
											>
										</div>
									{/each}
								</div>
							{/if}
							{#if file.message_id}
								<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
									<MessageSquare class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="w-24 shrink-0 text-xs text-zinc-500">message</span>
									<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
										>{file.message_id}</span
									>
								</div>
							{/if}
						</div>
					</div>

					<!-- file info -->
					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							file
						</p>
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<FileIcon class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">filename</span>
								<span class="min-w-0 truncate text-xs text-zinc-300"
									>{file.filename ?? '—'}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<Database class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">mime type</span>
								<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
									>{file.mime_type ?? '—'}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<HardDrive class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">size</span>
								<span class="text-xs text-zinc-300"
									>{formatBytes(file.size_bytes)}</span
								>
								{#if file.size_bytes != null}
									<span class="text-xs text-zinc-600"
										>({file.size_bytes.toLocaleString()} bytes)</span
									>
								{/if}
							</div>
							{#if file.checksum_sha256}
								<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
									<FingerprintPattern
										class="h-3.5 w-3.5 shrink-0 text-zinc-500"
									/>
									<span class="w-24 shrink-0 text-xs text-zinc-500">sha256</span>
									<span class="min-w-0 truncate font-mono text-xs text-zinc-400"
										>{file.checksum_sha256}</span
									>
								</div>
							{/if}
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<CircleCheck class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">status</span>
								<span
									class="text-xs font-medium capitalize {statusColor(
										file.status
									)}">{file.status}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<Server class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">source</span>
								<span class="text-xs text-zinc-300 capitalize">{file.source}</span>
							</div>
						</div>
					</div>

					<!-- description -->
					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							description
						</p>
						<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
							{#if file.description?.trim()}
								<p class="text-xs whitespace-pre-wrap text-zinc-300">
									{file.description.trim()}
								</p>
							{:else}
								<p class="text-xs text-zinc-600">no description yet</p>
							{/if}
						</div>
					</div>

					<!-- storage -->
					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							storage
							<span
								class="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-normal text-zinc-400 normal-case"
							>
								{si.label === 's3' ? 'Amazon S3' : 'filesystem'}
							</span>
						</p>
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<Database class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">backend</span>
								<span class="font-mono text-xs text-zinc-300"
									>{file.storage_backend}</span
								>
							</div>
							{#if si.label === 's3'}
								<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
									<Hash class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="w-24 shrink-0 text-xs text-zinc-500"
										>object key</span
									>
									<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
										>{file.storage_key}</span
									>
								</div>
								{#if si.path !== file.storage_key}
									<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
										<FolderOpen class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
										<span class="w-24 shrink-0 text-xs text-zinc-500">path</span
										>
										<span
											class="min-w-0 truncate font-mono text-xs text-zinc-400"
											>{si.path}</span
										>
									</div>
								{/if}
							{:else}
								<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
									<FolderOpen class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="w-24 shrink-0 text-xs text-zinc-500">path</span>
									<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
										>{si.path}</span
									>
								</div>
								{#if si.filename}
									<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
										<FileIcon class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
										<span class="w-24 shrink-0 text-xs text-zinc-500"
											>on-disk name</span
										>
										<span
											class="min-w-0 truncate font-mono text-xs text-zinc-300"
											>{si.filename}</span
										>
									</div>
								{/if}
							{/if}
						</div>
					</div>

					<!-- timestamps -->
					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							timestamps
						</p>
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<Calendar class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">created</span>
								<span class="text-xs text-zinc-300"
									>{new Date(file.created_at).toLocaleString()}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<Pencil class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">updated</span>
								<span class="text-xs text-zinc-300"
									>{new Date(file.updated_at).toLocaleString()}</span
								>
							</div>
						</div>
					</div>

					<!-- metadata -->
					{#if file.metadata_ && Object.keys(file.metadata_).length > 0}
						<div class="space-y-1.5">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								metadata
							</p>
							<pre
								class="max-h-48 overflow-auto rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-xs text-zinc-300">{JSON.stringify(
									file.metadata_,
									null,
									2
								)}</pre>
						</div>
					{/if}

					<!-- delete -->
					<div class="space-y-2 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
						<p class="text-xs font-medium text-zinc-400">danger zone</p>
						{#if deleteError}
							<div
								class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
							>
								{deleteError}
							</div>
						{/if}
						{#if file.deleted_at}
							<div class="flex flex-wrap items-center gap-2">
								<Button
									variant="outline"
									size="sm"
									class="rounded-xl border-emerald-900/40 text-emerald-400 hover:bg-emerald-900/20 hover:text-emerald-300"
									disabled={isRestoring || isDeleting}
									onclick={restoreFile}
								>
									<RotateCcw class="mr-1.5 h-3.5 w-3.5" />
									{isRestoring ? 'restoring...' : 'restore file'}
								</Button>
								{#if confirmWipe}
									<span class="text-sm text-zinc-300"
										>permanently delete this file?</span
									>
									<Button
										variant="destructive"
										size="sm"
										class="rounded-lg"
										disabled={isDeleting}
										onclick={() => deleteFile(true)}
									>
										{isDeleting ? 'deleting...' : 'yes, delete'}
									</Button>
									<Button
										variant="outline"
										size="sm"
										class="rounded-lg"
										onclick={() => (confirmWipe = false)}
									>
										<X class="mr-1.5 h-4 w-4" />
										cancel
									</Button>
								{:else}
									<Button
										variant="outline"
										size="sm"
										class="rounded-xl border-red-900/40 text-red-400 hover:bg-red-900/20 hover:text-red-300"
										onclick={() => (confirmWipe = true)}
									>
										<Trash2 class="mr-1.5 h-3.5 w-3.5" />
										perma delete
									</Button>
								{/if}
							</div>
						{:else if confirmDelete}
							<div class="flex items-center gap-3">
								<span class="text-sm text-zinc-300">delete this file?</span>
								<Button
									variant="destructive"
									size="sm"
									class="rounded-lg"
									disabled={isDeleting}
									onclick={() => deleteFile(false)}
								>
									{isDeleting ? 'deleting...' : 'yes, delete'}
								</Button>
								<Button
									variant="outline"
									size="sm"
									class="rounded-lg"
									onclick={() => (confirmDelete = false)}
								>
									<X class="mr-1.5 h-4 w-4" />
									cancel
								</Button>
							</div>
						{:else if confirmWipe}
							<div class="flex items-center gap-3">
								<span class="text-sm text-zinc-300"
									>permanently delete this file?</span
								>
								<Button
									variant="destructive"
									size="sm"
									class="rounded-lg"
									disabled={isDeleting}
									onclick={() => deleteFile(true)}
								>
									{isDeleting ? 'wiping...' : 'yes, wipe'}
								</Button>
								<Button
									variant="outline"
									size="sm"
									class="rounded-lg"
									onclick={() => (confirmWipe = false)}
								>
									<X class="mr-1.5 h-4 w-4" />
									cancel
								</Button>
							</div>
						{:else}
							<div class="flex flex-wrap gap-2">
								<Button
									variant="outline"
									size="sm"
									class="rounded-xl border-red-900/40 text-red-400 hover:bg-red-900/20 hover:text-red-300"
									onclick={() => {
										confirmDelete = true
										confirmWipe = false
									}}
								>
									<Trash2 class="mr-1.5 h-3.5 w-3.5" />
									delete file
								</Button>
								<Button
									variant="outline"
									size="sm"
									class="rounded-xl border-red-900/40 text-red-400 hover:bg-red-900/20 hover:text-red-300"
									onclick={() => {
										confirmWipe = true
										confirmDelete = false
									}}
								>
									<Trash2 class="mr-1.5 h-3.5 w-3.5" />
									full wipe
								</Button>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

{#if file}
	<AclModal
		bind:open={showAclModal}
		resourceType="file"
		resourceId={file.id}
		title="file access rules"
	/>
{/if}
