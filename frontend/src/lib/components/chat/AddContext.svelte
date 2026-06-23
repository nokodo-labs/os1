<script lang="ts">
	import { api } from '$lib/api/client'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ChatBottomPanel from '$lib/components/chat/ChatBottomPanel.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowUpTray from '$lib/components/icons/ArrowUpTray.svelte'
	import Brain from '$lib/components/icons/Brain.svelte'
	import Folder from '$lib/components/icons/Folder.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import ResourcePickerModal from '$lib/components/modals/ResourcePickerModal.svelte'
	import { RadioGroup } from '$lib/components/primitives'
	import Switch from '$lib/components/primitives/ResolverSwitch.svelte'
	import ResourceWidget from '$lib/components/widgets/ResourceWidget.svelte'
	import type { ResourceItem } from '$lib/components/widgets/types'
	import { modals } from '$lib/stores/modals.svelte'
	import { session } from '$lib/stores/session.svelte'

	// -- types --
	type QuickAction = 'none' | 'web_search' | 'think' | 'generate_image'

	interface McpServerTool {
		pluginId: string
		name: string
		description: string
		serverName: string
	}

	interface McpServerGroup {
		serverId: string
		serverName: string
		tools: McpServerTool[]
	}

	interface NativeAttachment {
		id: string
		resourceType?: ResourceItem['type']
		filename: string
		type: 'image' | 'audio' | 'video' | 'file'
		/** true for newly attached files (pending send); false for thread-level */
		isPending?: boolean
		/** local object URL for image/video preview */
		previewUrl?: string
		summary?: string
		/** display resource for widget-based rendering */
		resource: ResourceItem
	}

	// -- props --

	interface Props {
		open: boolean
		onClose: () => void
		activeAttachments?: NativeAttachment[]
		isUploading?: boolean
		webSearchEnabled?: boolean
		thinkLongerEnabled?: boolean
		generateImageEnabled?: boolean
		quickAction?: QuickAction
		onFileUpload?: (files: FileList) => void
		onAttachResource?: (resource: ResourceItem) => void
		onToggleWebSearch?: () => void
		onToggleThinkLonger?: () => void
		onToggleGenerateImage?: () => void
		onQuickActionChange?: (action: QuickAction) => void
		extraPluginIds?: string[]
		onToggleExtraPlugin?: (pluginId: string) => void
		onRemoveAttachment?: (id: string) => void
	}

	let {
		open,
		onClose,
		activeAttachments = [],
		isUploading = false,
		webSearchEnabled = false,
		thinkLongerEnabled = false,
		generateImageEnabled = false,
		quickAction = 'none',
		onFileUpload,
		onAttachResource,
		onToggleWebSearch,
		onToggleThinkLonger,
		onToggleGenerateImage,
		onQuickActionChange,
		extraPluginIds = [],
		onToggleExtraPlugin,
		onRemoveAttachment,
	}: Props = $props()

	// -- state --

	let fileInput = $state<HTMLInputElement | null>(null)
	let isResourcePickerOpen = $state(false)
	let mcpServerGroups = $state<McpServerGroup[]>([])
	let mcpToolsLoaded = $state(false)
	let mcpToolsLoading = $state(false)
	const chatAttachmentResourceTypes: ResourceItem['type'][] = [
		'thread',
		'note',
		'file',
		'project',
		'reminder',
		'reminder_list',
		'calendar_event',
		'calendar',
	]

	const mcpToolList = $derived(mcpServerGroups.flatMap((group) => group.tools))
	const selectedMcpTools = $derived(
		mcpToolList.filter((tool) => extraPluginIds.includes(tool.pluginId))
	)
	const attachedIds = $derived(new Set(activeAttachments.map((attachment) => attachment.id)))
	const hasInputContext = $derived(
		activeAttachments.length > 0 || selectedMcpTools.length > 0 || isUploading
	)
	const hasMcpTools = $derived(mcpToolList.length > 0)
	const activeQuickAction = $derived(
		quickAction !== 'none'
			? quickAction
			: webSearchEnabled
				? 'web_search'
				: thinkLongerEnabled
					? 'think'
					: generateImageEnabled
						? 'generate_image'
						: 'none'
	)
	const quickActionOptions = [
		{
			value: 'web_search',
			label: 'search the web',
			icon: GlobeAlt,
			selectedClass:
				'border-sky-400/35 bg-sky-400/14 text-sky-50 shadow-[0_12px_26px_rgba(14,165,233,0.18)]',
			selectedIconClass: 'text-sky-300',
		},
		{
			value: 'think',
			label: 'think longer',
			icon: Brain,
			selectedClass:
				'border-violet-400/35 bg-violet-400/14 text-violet-50 shadow-[0_12px_26px_rgba(139,92,246,0.18)]',
			selectedIconClass: 'text-violet-300',
		},
		{
			value: 'generate_image',
			label: 'generate image',
			icon: Sparkles,
			selectedClass:
				'border-amber-300/35 bg-amber-300/14 text-amber-50 shadow-[0_12px_26px_rgba(251,191,36,0.16)]',
			selectedIconClass: 'text-amber-200',
		},
	] as const

	$effect(() => {
		if (!open || mcpToolsLoaded || mcpToolsLoading) return
		void loadMcpTools()
	})

	// -- other handlers --

	function handleFileChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement
		if (input.files && input.files.length > 0) {
			onFileUpload?.(input.files)
		}
		input.value = ''
	}

	function handleResourcePicked(resource: ResourceItem) {
		onAttachResource?.(resource)
		isResourcePickerOpen = false
	}

	function handleAttachmentClick(attachment: NativeAttachment): void {
		if (attachment.resourceType && attachment.resourceType !== 'file') return
		modals.open('file-details', { fileId: attachment.id })
	}

	async function loadMcpTools(): Promise<void> {
		mcpToolsLoading = true
		try {
			const { data, error } = await api.GET('/v1/integrations/mcp/servers')
			if (error || !data) {
				mcpServerGroups = []
				return
			}
			// only the current user's own servers are toggleable per-request here.
			// global (admin-managed) servers are wired to agents, not per request.
			const currentUserId = session.currentUserId
			const groups: McpServerGroup[] = []
			for (const server of data) {
				if (server.scope !== 'user') continue
				if (currentUserId !== null && server.owner_user_id !== currentUserId) continue
				const tools: McpServerTool[] = []
				for (const tool of server.discovered_tools ?? []) {
					if (!tool.enabled || !tool.plugin_id) continue
					tools.push({
						pluginId: tool.plugin_id,
						name: tool.name,
						description: tool.description ?? '',
						serverName: server.name,
					})
				}
				if (tools.length > 0) {
					groups.push({ serverId: server.id, serverName: server.name, tools })
				}
			}
			mcpServerGroups = groups
		} catch {
			mcpServerGroups = []
		} finally {
			mcpToolsLoaded = true
			mcpToolsLoading = false
		}
	}

	function pluginSelected(pluginId: string): boolean {
		return extraPluginIds.includes(pluginId)
	}

	function setQuickAction(action: string): void {
		const next = action as QuickAction
		if (onQuickActionChange) {
			onQuickActionChange(next)
			return
		}
		if (next === 'web_search') onToggleWebSearch?.()
		else if (next === 'think') onToggleThinkLonger?.()
		else if (next === 'generate_image') onToggleGenerateImage?.()
	}
</script>

<ChatBottomPanel {open} {onClose} ariaLabel="add context panel">
	{#if hasInputContext}
		<!-- input context section -->
		<div class="max-h-[30dvh] overflow-y-auto px-4 pt-3 pb-2">
			<div class="text-foreground/45 mb-3 text-[11px] font-semibold tracking-widest">
				input context
			</div>

			<div class="space-y-1">
				{#each activeAttachments as attachment (attachment.id)}
					<div class="group/attachment flex items-center gap-1.5">
						<div class="min-w-0 flex-1">
							<ResourceWidget
								resource={attachment.resource}
								layout="pill"
								onclick={() => handleAttachmentClick(attachment)}
							/>
						</div>
						{#if attachment.isPending !== false}
							<button
								type="button"
								aria-label="remove attachment"
								class="text-muted-foreground hover:text-foreground flex size-9 shrink-0 cursor-pointer items-center justify-center border-none bg-transparent transition-all duration-150 hover:scale-[1.05] active:scale-[0.97]"
								onclick={() => onRemoveAttachment?.(attachment.id)}
							>
								<XMark class="h-5 w-5" />
							</button>
						{/if}
					</div>
				{/each}

				{#each selectedMcpTools as tool (tool.pluginId)}
					<div class="flex items-center gap-2.5 rounded-xl px-2 py-1.5">
						<span class="relative flex h-2.5 w-2.5 shrink-0">
							<span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-cyan-400"
							></span>
						</span>
						<Wrench class="text-foreground/50 h-3.5 w-3.5 shrink-0" />
						<span class="min-w-0 flex-1 text-left">
							<span class="text-foreground/80 block truncate text-xs font-medium">
								{tool.name}
							</span>
							<span class="text-foreground/45 block truncate text-[11px]">
								{tool.serverName}
							</span>
						</span>
						<Switch
							size="sm"
							checked={true}
							onchange={() => onToggleExtraPlugin?.(tool.pluginId)}
						/>
					</div>
				{/each}

				{#if isUploading}
					<div class="flex items-center gap-2.5 rounded-xl px-2 py-1.5">
						<span class="relative flex h-2.5 w-2.5 shrink-0">
							<span
								class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"
							></span>
							<span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-500"
							></span>
						</span>
						<ArrowUpTray class="text-foreground/50 h-3.5 w-3.5 shrink-0" />
						<ShimmerText className="text-foreground/60 text-xs font-medium">
							uploading
						</ShimmerText>
					</div>
				{/if}
			</div>
		</div>

		<div class="border-foreground/10 mx-4 my-1 border-t"></div>
	{/if}

	<!-- add to context -->
	<div class="px-4 pt-3 pb-2">
		<div class="text-foreground/45 mb-3 text-[11px] font-semibold tracking-widest">
			add to context
		</div>
		<div class="grid grid-cols-3 gap-2">
			<button type="button" class="context-action-btn" onclick={() => fileInput?.click()}>
				<span class="context-action-icon">
					<ArrowUpTray class="h-5 w-5" />
				</span>
				<span class="context-action-label">upload</span>
			</button>
			<button
				type="button"
				class="context-action-btn"
				onclick={() => {
					isResourcePickerOpen = true
				}}
			>
				<span class="context-action-icon">
					<Folder class="h-5 w-5" />
				</span>
				<span class="context-action-label">attach resource</span>
			</button>
		</div>
	</div>

	<div class="border-foreground/10 mx-4 border-t"></div>

	<!-- actions -->
	<div class="px-4 py-2">
		<div class="text-foreground/45 pt-1 pb-2 text-[11px] font-semibold tracking-widest">
			actions
		</div>

		<div class="space-y-0.5">
			<div class="px-1 pb-2">
				<RadioGroup
					options={quickActionOptions}
					value={activeQuickAction}
					onchange={setQuickAction}
					clearValue="none"
					class="flex-wrap"
				/>
			</div>

			{#if mcpToolsLoading || hasMcpTools}
				<div
					class="text-foreground/45 px-3 pt-3 pb-1 text-[11px] font-semibold tracking-widest"
				>
					MCP tools
				</div>
				{#if mcpToolsLoading}
					<div class="flex justify-center px-3 py-4">
						<NokodoLoader />
					</div>
				{:else}
					{#each mcpServerGroups as group (group.serverId)}
						<div
							class="text-foreground/55 flex items-center gap-1.5 px-3 pt-2 pb-1 text-[11px] font-medium"
						>
							<GlobeAlt class="h-3 w-3 shrink-0" />
							<span class="truncate">{group.serverName}</span>
						</div>
						{#each group.tools as tool (tool.pluginId)}
							<button
								type="button"
								class="rounded-pill hover:bg-foreground/8 flex w-full cursor-pointer items-center gap-3 px-3 py-2.5 transition-colors duration-150"
								onclick={() => onToggleExtraPlugin?.(tool.pluginId)}
							>
								<Wrench class="text-foreground/60 h-5 w-5 shrink-0" />
								<span class="min-w-0 flex-1 text-left">
									<span
										class="text-foreground/80 block truncate text-sm font-medium"
									>
										{tool.name}
									</span>
									{#if tool.description}
										<span
											class="text-foreground/45 mt-0.5 line-clamp-1 text-xs"
										>
											{tool.description}
										</span>
									{/if}
								</span>
								<Switch
									size="sm"
									checked={pluginSelected(tool.pluginId)}
									onchange={() => onToggleExtraPlugin?.(tool.pluginId)}
								/>
							</button>
						{/each}
					{/each}
				{/if}
			{/if}
		</div>
	</div>

	<!-- hidden file input -->
</ChatBottomPanel>

{#if open}
	<input bind:this={fileInput} type="file" class="hidden" multiple onchange={handleFileChange} />
{/if}

<ResourcePickerModal
	open={isResourcePickerOpen}
	onClose={() => (isResourcePickerOpen = false)}
	onSelect={handleResourcePicked}
	excludeIds={attachedIds}
	allowedTypes={chatAttachmentResourceTypes}
	title="attach resource"
/>

<style>
	.context-action-btn {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.875rem 0.5rem;
		border-radius: var(--radius-container);
		background: color-mix(in oklch, var(--foreground) 14%, transparent);
		border: 1px solid color-mix(in oklch, var(--foreground) 10%, transparent);
		cursor: pointer;
		transition:
			background 0.15s ease,
			transform 0.1s ease;
		-webkit-tap-highlight-color: transparent;
	}

	.context-action-btn:hover {
		background: color-mix(in oklch, var(--foreground) 20%, transparent);
	}

	.context-action-btn:active {
		transform: scale(0.96);
		background: color-mix(in oklch, var(--foreground) 17%, transparent);
	}

	.context-action-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		color: color-mix(in oklch, var(--foreground) 72%, transparent);
	}

	.context-action-label {
		font-size: 0.72rem;
		font-weight: 500;
		color: color-mix(in oklch, var(--foreground) 65%, transparent);
		text-align: center;
		line-height: 1.2;
	}
</style>
