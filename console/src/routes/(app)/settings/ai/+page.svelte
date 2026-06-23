<script lang="ts">
	import { api } from '$lib/api'
	import SettingsAI from '$lib/components/settings/SettingsAI.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { formatJsonObject, toStringOrEmpty } from '$lib/settings/utils'
	import { asNumberOrNull, asNumberOrUndefined } from '$lib/utils/settingsNumbers'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'
	import { untrack } from 'svelte'

	type ChatContextMode = 'recent' | 'relevant' | 'pinned'

	const ctx = getSettingsContext()

	// default agents
	let defaultAgentIds = $state<string[]>([])
	// memory
	let memoryEnable = $state(false)
	let memorySimilarityThreshold = $state('')
	let memoryTopK = $state('')
	let memoryPostProcessingTurns = $state('')
	// chat context
	let chatContextEnabled = $state(true)
	let chatContextMode = $state<ChatContextMode>('recent')
	let chatContextTopK = $state('')
	let chatContextSimilarityThreshold = $state('')
	// retrieval
	let retrievalTurns = $state('')
	let retrievalPreBuild = $state(true)
	// task models
	let taskDefaultModelId = $state('')
	let taskThreadMetadataModelId = $state('')
	let taskThreadMaintenanceModelId = $state('')
	let taskInputAutocompleteModelId = $state('')
	let taskSummarizationModelId = $state('')
	let taskMemoryPostProcessingModelId = $state('')
	let taskWebSearchModelId = $state('')
	let taskAssetDescriptionModelId = $state('')
	let taskAssetTextExtractionModelId = $state('')
	let taskMaintenanceMaxCharsPerMessage = $state('')
	// attachments
	let attachmentImageDecayIterations = $state('')
	let attachmentAudioDecayIterations = $state('')
	let attachmentVideoDecayIterations = $state('')
	// context compaction
	let contextCompactionEnabled = $state(true)
	let contextCompactionTriggerRatio = $state('')
	let contextCompactionRecoveryTargetRatio = $state('')
	let contextCompactionTargetUsageCapTokens = $state('')
	let contextCompactionSummaryBatchMinTokens = $state('')
	let contextCompactionSummaryBatchMaxTokens = $state('')
	let contextCompactionPromptOverheadTokens = $state('')
	let contextCompactionBlockingSummarizationEnabled = $state(true)
	let contextCompactionBlockingSummarizationTimeoutSeconds = $state('')
	let contextCompactionToolResultMaxShare = $state('')
	let contextCompactionToolResultHardCap = $state('')
	let contextCompactionToolResultsCombinedMaxShare = $state('')
	let contextCompactionResponseHeadroom = $state('')
	let contextCompactionSummarizationMaxCharsPerMessage = $state('')
	// media
	let mediaImagesEnabled = $state(true)
	let mediaImagesModel = $state('')
	let mediaImagesDefaultSize = $state('')
	let mediaImagesDefaultSteps = $state('')
	let mediaImagesDefaultN = $state('')
	let mediaImagesMaxN = $state('')
	let mediaVideosEnabled = $state(false)
	let mediaAudioEnabled = $state(false)

	type Original = {
		defaultAgentIds: string[]
		memoryEnable: boolean
		memorySimilarityThreshold: string
		memoryTopK: string
		memoryPostProcessingTurns: string
		chatContextEnabled: boolean
		chatContextMode: ChatContextMode
		chatContextTopK: string
		chatContextSimilarityThreshold: string
		retrievalTurns: string
		retrievalPreBuild: boolean
		taskDefaultModelId: string
		taskThreadMetadataModelId: string
		taskThreadMaintenanceModelId: string
		taskInputAutocompleteModelId: string
		taskSummarizationModelId: string
		taskMemoryPostProcessingModelId: string
		taskWebSearchModelId: string
		taskAssetDescriptionModelId: string
		taskAssetTextExtractionModelId: string
		taskMaintenanceMaxCharsPerMessage: string
		attachmentImageDecayIterations: string
		attachmentAudioDecayIterations: string
		attachmentVideoDecayIterations: string
		contextCompactionEnabled: boolean
		contextCompactionTriggerRatio: string
		contextCompactionRecoveryTargetRatio: string
		contextCompactionTargetUsageCapTokens: string
		contextCompactionSummaryBatchMinTokens: string
		contextCompactionSummaryBatchMaxTokens: string
		contextCompactionPromptOverheadTokens: string
		contextCompactionBlockingSummarizationEnabled: boolean
		contextCompactionBlockingSummarizationTimeoutSeconds: string
		contextCompactionToolResultMaxShare: string
		contextCompactionToolResultHardCap: string
		contextCompactionToolResultsCombinedMaxShare: string
		contextCompactionResponseHeadroom: string
		contextCompactionSummarizationMaxCharsPerMessage: string
		mediaImagesEnabled: boolean
		mediaImagesModel: string
		mediaImagesDefaultSize: string
		mediaImagesDefaultSteps: string
		mediaImagesDefaultN: string
		mediaImagesMaxN: string
		mediaVideosEnabled: boolean
		mediaAudioEnabled: boolean
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const ai = r.data.ai
		defaultAgentIds = ai?.default_agent_ids ?? []
		const memory = ai?.memory
		memoryEnable = memory?.enable_memory ?? false
		memorySimilarityThreshold = toStringOrEmpty(memory?.similarity_threshold)
		memoryTopK = toStringOrEmpty(memory?.top_k)
		memoryPostProcessingTurns = toStringOrEmpty(memory?.post_processing_turns)
		const chatCtx = ai?.chat_context
		chatContextEnabled = chatCtx?.enabled ?? true
		chatContextMode = (chatCtx?.mode ?? 'recent') as ChatContextMode
		chatContextTopK = toStringOrEmpty(chatCtx?.top_k)
		chatContextSimilarityThreshold = toStringOrEmpty(chatCtx?.similarity_threshold)
		retrievalTurns = toStringOrEmpty(ai?.retrieval_turns)
		retrievalPreBuild = ai?.retrieval_pre_build ?? true
		const tasks = ai?.tasks
		taskDefaultModelId = tasks?.default_model_id ?? ''
		taskThreadMetadataModelId = tasks?.thread_metadata_model_id ?? ''
		taskThreadMaintenanceModelId = tasks?.thread_maintenance_model_id ?? ''
		taskInputAutocompleteModelId = tasks?.input_autocomplete_model_id ?? ''
		taskSummarizationModelId = tasks?.summarization_model_id ?? ''
		taskMemoryPostProcessingModelId = tasks?.memory_post_processing_model_id ?? ''
		taskWebSearchModelId = tasks?.web_search_model_id ?? ''
		taskAssetDescriptionModelId = tasks?.asset_description_model_id ?? ''
		taskAssetTextExtractionModelId = tasks?.asset_text_extraction_model_id ?? ''
		taskMaintenanceMaxCharsPerMessage = toStringOrEmpty(
			tasks?.maintenance_max_chars_per_message
		)
		const attachments = ai?.attachments
		attachmentImageDecayIterations = toStringOrEmpty(attachments?.image_decay_iterations)
		attachmentAudioDecayIterations = toStringOrEmpty(attachments?.audio_decay_iterations)
		attachmentVideoDecayIterations = toStringOrEmpty(attachments?.video_decay_iterations)
		const cc = ai?.context_compaction
		contextCompactionEnabled = cc?.enabled ?? true
		contextCompactionTriggerRatio = toStringOrEmpty(cc?.trigger_ratio)
		contextCompactionRecoveryTargetRatio = toStringOrEmpty(cc?.recovery_target_ratio)
		contextCompactionTargetUsageCapTokens = toStringOrEmpty(cc?.target_usage_cap_tokens)
		contextCompactionSummaryBatchMinTokens = toStringOrEmpty(cc?.summary_batch_min_tokens)
		contextCompactionSummaryBatchMaxTokens = toStringOrEmpty(cc?.summary_batch_max_tokens)
		contextCompactionPromptOverheadTokens = toStringOrEmpty(cc?.prompt_overhead_tokens)
		contextCompactionBlockingSummarizationEnabled = cc?.blocking_summarization_enabled ?? true
		contextCompactionBlockingSummarizationTimeoutSeconds = toStringOrEmpty(
			cc?.blocking_summarization_timeout_seconds
		)
		contextCompactionToolResultMaxShare = toStringOrEmpty(cc?.tool_result_max_share)
		contextCompactionToolResultHardCap = toStringOrEmpty(cc?.tool_result_hard_cap)
		contextCompactionToolResultsCombinedMaxShare = toStringOrEmpty(
			cc?.tool_results_combined_max_share
		)
		contextCompactionResponseHeadroom = toStringOrEmpty(cc?.response_headroom)
		contextCompactionSummarizationMaxCharsPerMessage = toStringOrEmpty(
			cc?.summarization_max_chars_per_message
		)
		const media = ai?.media
		mediaImagesEnabled = media?.images?.enabled ?? true
		mediaImagesModel = media?.images?.model ?? ''
		mediaImagesDefaultSize = toStringOrEmpty(media?.images?.default_size)
		mediaImagesDefaultSteps = toStringOrEmpty(media?.images?.default_steps)
		mediaImagesDefaultN = toStringOrEmpty(media?.images?.default_n)
		mediaImagesMaxN = toStringOrEmpty(media?.images?.max_n)
		mediaVideosEnabled = media?.videos?.enabled ?? false
		mediaAudioEnabled = media?.audio?.enabled ?? false

		untrack(() => {
			original = {
				defaultAgentIds: [...defaultAgentIds],
				memoryEnable,
				memorySimilarityThreshold,
				memoryTopK,
				memoryPostProcessingTurns,
				chatContextEnabled,
				chatContextMode,
				chatContextTopK,
				chatContextSimilarityThreshold,
				retrievalTurns,
				retrievalPreBuild,
				taskDefaultModelId,
				taskThreadMetadataModelId,
				taskThreadMaintenanceModelId,
				taskInputAutocompleteModelId,
				taskSummarizationModelId,
				taskMemoryPostProcessingModelId,
				taskWebSearchModelId,
				taskAssetDescriptionModelId,
				taskAssetTextExtractionModelId,
				taskMaintenanceMaxCharsPerMessage,
				attachmentImageDecayIterations,
				attachmentAudioDecayIterations,
				attachmentVideoDecayIterations,
				contextCompactionEnabled,
				contextCompactionTriggerRatio,
				contextCompactionRecoveryTargetRatio,
				contextCompactionTargetUsageCapTokens,
				contextCompactionSummaryBatchMinTokens,
				contextCompactionSummaryBatchMaxTokens,
				contextCompactionPromptOverheadTokens,
				contextCompactionBlockingSummarizationEnabled,
				contextCompactionBlockingSummarizationTimeoutSeconds,
				contextCompactionToolResultMaxShare,
				contextCompactionToolResultHardCap,
				contextCompactionToolResultsCombinedMaxShare,
				contextCompactionResponseHeadroom,
				contextCompactionSummarizationMaxCharsPerMessage,
				mediaImagesEnabled,
				mediaImagesModel,
				mediaImagesDefaultSize,
				mediaImagesDefaultSteps,
				mediaImagesDefaultN,
				mediaImagesMaxN,
				mediaVideosEnabled,
				mediaAudioEnabled,
			}
		})
	})

	const hasChanges = $derived(
		original !== null &&
			(JSON.stringify(defaultAgentIds) !== JSON.stringify(original.defaultAgentIds) ||
				memoryEnable !== original.memoryEnable ||
				memorySimilarityThreshold !== original.memorySimilarityThreshold ||
				memoryTopK !== original.memoryTopK ||
				memoryPostProcessingTurns !== original.memoryPostProcessingTurns ||
				chatContextEnabled !== original.chatContextEnabled ||
				chatContextMode !== original.chatContextMode ||
				chatContextTopK !== original.chatContextTopK ||
				chatContextSimilarityThreshold !== original.chatContextSimilarityThreshold ||
				retrievalTurns !== original.retrievalTurns ||
				retrievalPreBuild !== original.retrievalPreBuild ||
				taskDefaultModelId !== original.taskDefaultModelId ||
				taskThreadMetadataModelId !== original.taskThreadMetadataModelId ||
				taskThreadMaintenanceModelId !== original.taskThreadMaintenanceModelId ||
				taskInputAutocompleteModelId !== original.taskInputAutocompleteModelId ||
				taskSummarizationModelId !== original.taskSummarizationModelId ||
				taskMemoryPostProcessingModelId !== original.taskMemoryPostProcessingModelId ||
				taskWebSearchModelId !== original.taskWebSearchModelId ||
				taskAssetDescriptionModelId !== original.taskAssetDescriptionModelId ||
				taskAssetTextExtractionModelId !== original.taskAssetTextExtractionModelId ||
				taskMaintenanceMaxCharsPerMessage !== original.taskMaintenanceMaxCharsPerMessage ||
				attachmentImageDecayIterations !== original.attachmentImageDecayIterations ||
				attachmentAudioDecayIterations !== original.attachmentAudioDecayIterations ||
				attachmentVideoDecayIterations !== original.attachmentVideoDecayIterations ||
				contextCompactionEnabled !== original.contextCompactionEnabled ||
				contextCompactionTriggerRatio !== original.contextCompactionTriggerRatio ||
				contextCompactionRecoveryTargetRatio !==
					original.contextCompactionRecoveryTargetRatio ||
				contextCompactionTargetUsageCapTokens !==
					original.contextCompactionTargetUsageCapTokens ||
				contextCompactionSummaryBatchMinTokens !==
					original.contextCompactionSummaryBatchMinTokens ||
				contextCompactionSummaryBatchMaxTokens !==
					original.contextCompactionSummaryBatchMaxTokens ||
				contextCompactionPromptOverheadTokens !==
					original.contextCompactionPromptOverheadTokens ||
				contextCompactionBlockingSummarizationEnabled !==
					original.contextCompactionBlockingSummarizationEnabled ||
				contextCompactionBlockingSummarizationTimeoutSeconds !==
					original.contextCompactionBlockingSummarizationTimeoutSeconds ||
				contextCompactionToolResultMaxShare !==
					original.contextCompactionToolResultMaxShare ||
				contextCompactionToolResultHardCap !==
					original.contextCompactionToolResultHardCap ||
				contextCompactionToolResultsCombinedMaxShare !==
					original.contextCompactionToolResultsCombinedMaxShare ||
				contextCompactionResponseHeadroom !== original.contextCompactionResponseHeadroom ||
				contextCompactionSummarizationMaxCharsPerMessage !==
					original.contextCompactionSummarizationMaxCharsPerMessage ||
				mediaImagesEnabled !== original.mediaImagesEnabled ||
				mediaImagesModel !== original.mediaImagesModel ||
				mediaImagesDefaultSize !== original.mediaImagesDefaultSize ||
				mediaImagesDefaultSteps !== original.mediaImagesDefaultSteps ||
				mediaImagesDefaultN !== original.mediaImagesDefaultN ||
				mediaImagesMaxN !== original.mediaImagesMaxN ||
				mediaVideosEnabled !== original.mediaVideosEnabled ||
				mediaAudioEnabled !== original.mediaAudioEnabled)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		defaultAgentIds = [...original.defaultAgentIds]
		memoryEnable = original.memoryEnable
		memorySimilarityThreshold = original.memorySimilarityThreshold
		memoryTopK = original.memoryTopK
		memoryPostProcessingTurns = original.memoryPostProcessingTurns
		chatContextEnabled = original.chatContextEnabled
		chatContextMode = original.chatContextMode
		chatContextTopK = original.chatContextTopK
		chatContextSimilarityThreshold = original.chatContextSimilarityThreshold
		retrievalTurns = original.retrievalTurns
		retrievalPreBuild = original.retrievalPreBuild
		taskDefaultModelId = original.taskDefaultModelId
		taskThreadMetadataModelId = original.taskThreadMetadataModelId
		taskThreadMaintenanceModelId = original.taskThreadMaintenanceModelId
		taskInputAutocompleteModelId = original.taskInputAutocompleteModelId
		taskSummarizationModelId = original.taskSummarizationModelId
		taskMemoryPostProcessingModelId = original.taskMemoryPostProcessingModelId
		taskWebSearchModelId = original.taskWebSearchModelId
		taskAssetDescriptionModelId = original.taskAssetDescriptionModelId
		taskAssetTextExtractionModelId = original.taskAssetTextExtractionModelId
		taskMaintenanceMaxCharsPerMessage = original.taskMaintenanceMaxCharsPerMessage
		attachmentImageDecayIterations = original.attachmentImageDecayIterations
		attachmentAudioDecayIterations = original.attachmentAudioDecayIterations
		attachmentVideoDecayIterations = original.attachmentVideoDecayIterations
		contextCompactionEnabled = original.contextCompactionEnabled
		contextCompactionTriggerRatio = original.contextCompactionTriggerRatio
		contextCompactionRecoveryTargetRatio = original.contextCompactionRecoveryTargetRatio
		contextCompactionTargetUsageCapTokens = original.contextCompactionTargetUsageCapTokens
		contextCompactionSummaryBatchMinTokens = original.contextCompactionSummaryBatchMinTokens
		contextCompactionSummaryBatchMaxTokens = original.contextCompactionSummaryBatchMaxTokens
		contextCompactionPromptOverheadTokens = original.contextCompactionPromptOverheadTokens
		contextCompactionBlockingSummarizationEnabled =
			original.contextCompactionBlockingSummarizationEnabled
		contextCompactionBlockingSummarizationTimeoutSeconds =
			original.contextCompactionBlockingSummarizationTimeoutSeconds
		contextCompactionToolResultMaxShare = original.contextCompactionToolResultMaxShare
		contextCompactionToolResultHardCap = original.contextCompactionToolResultHardCap
		contextCompactionToolResultsCombinedMaxShare =
			original.contextCompactionToolResultsCombinedMaxShare
		contextCompactionResponseHeadroom = original.contextCompactionResponseHeadroom
		contextCompactionSummarizationMaxCharsPerMessage =
			original.contextCompactionSummarizationMaxCharsPerMessage
		mediaImagesEnabled = original.mediaImagesEnabled
		mediaImagesModel = original.mediaImagesModel
		mediaImagesDefaultSize = original.mediaImagesDefaultSize
		mediaImagesDefaultSteps = original.mediaImagesDefaultSteps
		mediaImagesDefaultN = original.mediaImagesDefaultN
		mediaImagesMaxN = original.mediaImagesMaxN
		mediaVideosEnabled = original.mediaVideosEnabled
		mediaAudioEnabled = original.mediaAudioEnabled
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const aiPatch: Record<string, unknown> = {}

			if (JSON.stringify(defaultAgentIds) !== JSON.stringify(original.defaultAgentIds))
				aiPatch.default_agent_ids = defaultAgentIds

			if (
				memoryEnable !== original.memoryEnable ||
				memorySimilarityThreshold !== original.memorySimilarityThreshold ||
				memoryTopK !== original.memoryTopK ||
				memoryPostProcessingTurns !== original.memoryPostProcessingTurns
			) {
				const m: Record<string, unknown> = {}
				if (memoryEnable !== original.memoryEnable) m.enable_memory = memoryEnable
				if (memorySimilarityThreshold !== original.memorySimilarityThreshold)
					m.similarity_threshold = asNumberOrUndefined(memorySimilarityThreshold)
				if (memoryTopK !== original.memoryTopK) m.top_k = asNumberOrUndefined(memoryTopK)
				if (memoryPostProcessingTurns !== original.memoryPostProcessingTurns)
					m.post_processing_turns = asNumberOrUndefined(memoryPostProcessingTurns)
				aiPatch.memory = m
			}

			if (
				chatContextEnabled !== original.chatContextEnabled ||
				chatContextMode !== original.chatContextMode ||
				chatContextTopK !== original.chatContextTopK ||
				chatContextSimilarityThreshold !== original.chatContextSimilarityThreshold
			) {
				const cc: Record<string, unknown> = {}
				if (chatContextEnabled !== original.chatContextEnabled)
					cc.enabled = chatContextEnabled
				if (chatContextMode !== original.chatContextMode) cc.mode = chatContextMode
				if (chatContextTopK !== original.chatContextTopK)
					cc.top_k = asNumberOrUndefined(chatContextTopK)
				if (chatContextSimilarityThreshold !== original.chatContextSimilarityThreshold)
					cc.similarity_threshold = asNumberOrUndefined(chatContextSimilarityThreshold)
				aiPatch.chat_context = cc
			}

			if (retrievalTurns !== original.retrievalTurns)
				aiPatch.retrieval_turns = asNumberOrUndefined(retrievalTurns)
			if (retrievalPreBuild !== original.retrievalPreBuild)
				aiPatch.retrieval_pre_build = retrievalPreBuild

			if (
				taskDefaultModelId !== original.taskDefaultModelId ||
				taskThreadMetadataModelId !== original.taskThreadMetadataModelId ||
				taskThreadMaintenanceModelId !== original.taskThreadMaintenanceModelId ||
				taskInputAutocompleteModelId !== original.taskInputAutocompleteModelId ||
				taskSummarizationModelId !== original.taskSummarizationModelId ||
				taskMemoryPostProcessingModelId !== original.taskMemoryPostProcessingModelId ||
				taskWebSearchModelId !== original.taskWebSearchModelId ||
				taskAssetDescriptionModelId !== original.taskAssetDescriptionModelId ||
				taskAssetTextExtractionModelId !== original.taskAssetTextExtractionModelId ||
				taskMaintenanceMaxCharsPerMessage !== original.taskMaintenanceMaxCharsPerMessage
			) {
				const t: Record<string, unknown> = {}
				if (taskDefaultModelId !== original.taskDefaultModelId)
					t.default_model_id = taskDefaultModelId || null
				if (taskThreadMetadataModelId !== original.taskThreadMetadataModelId)
					t.thread_metadata_model_id = taskThreadMetadataModelId || null
				if (taskThreadMaintenanceModelId !== original.taskThreadMaintenanceModelId)
					t.thread_maintenance_model_id = taskThreadMaintenanceModelId || null
				if (taskInputAutocompleteModelId !== original.taskInputAutocompleteModelId)
					t.input_autocomplete_model_id = taskInputAutocompleteModelId || null
				if (taskSummarizationModelId !== original.taskSummarizationModelId)
					t.summarization_model_id = taskSummarizationModelId || null
				if (taskMemoryPostProcessingModelId !== original.taskMemoryPostProcessingModelId)
					t.memory_post_processing_model_id = taskMemoryPostProcessingModelId || null
				if (taskWebSearchModelId !== original.taskWebSearchModelId)
					t.web_search_model_id = taskWebSearchModelId || null
				if (taskAssetDescriptionModelId !== original.taskAssetDescriptionModelId)
					t.asset_description_model_id = taskAssetDescriptionModelId || null
				if (taskAssetTextExtractionModelId !== original.taskAssetTextExtractionModelId)
					t.asset_text_extraction_model_id = taskAssetTextExtractionModelId || null
				if (
					taskMaintenanceMaxCharsPerMessage !== original.taskMaintenanceMaxCharsPerMessage
				)
					t.maintenance_max_chars_per_message = asNumberOrNull(
						taskMaintenanceMaxCharsPerMessage
					)
				aiPatch.tasks = t
			}

			if (
				attachmentImageDecayIterations !== original.attachmentImageDecayIterations ||
				attachmentAudioDecayIterations !== original.attachmentAudioDecayIterations ||
				attachmentVideoDecayIterations !== original.attachmentVideoDecayIterations
			) {
				const a: Record<string, unknown> = {}
				if (attachmentImageDecayIterations !== original.attachmentImageDecayIterations)
					a.image_decay_iterations = asNumberOrUndefined(attachmentImageDecayIterations)
				if (attachmentAudioDecayIterations !== original.attachmentAudioDecayIterations)
					a.audio_decay_iterations = asNumberOrUndefined(attachmentAudioDecayIterations)
				if (attachmentVideoDecayIterations !== original.attachmentVideoDecayIterations)
					a.video_decay_iterations = asNumberOrUndefined(attachmentVideoDecayIterations)
				aiPatch.attachments = a
			}

			if (
				contextCompactionEnabled !== original.contextCompactionEnabled ||
				contextCompactionTriggerRatio !== original.contextCompactionTriggerRatio ||
				contextCompactionRecoveryTargetRatio !==
					original.contextCompactionRecoveryTargetRatio ||
				contextCompactionTargetUsageCapTokens !==
					original.contextCompactionTargetUsageCapTokens ||
				contextCompactionSummaryBatchMinTokens !==
					original.contextCompactionSummaryBatchMinTokens ||
				contextCompactionSummaryBatchMaxTokens !==
					original.contextCompactionSummaryBatchMaxTokens ||
				contextCompactionPromptOverheadTokens !==
					original.contextCompactionPromptOverheadTokens ||
				contextCompactionBlockingSummarizationEnabled !==
					original.contextCompactionBlockingSummarizationEnabled ||
				contextCompactionBlockingSummarizationTimeoutSeconds !==
					original.contextCompactionBlockingSummarizationTimeoutSeconds ||
				contextCompactionToolResultMaxShare !==
					original.contextCompactionToolResultMaxShare ||
				contextCompactionToolResultHardCap !==
					original.contextCompactionToolResultHardCap ||
				contextCompactionToolResultsCombinedMaxShare !==
					original.contextCompactionToolResultsCombinedMaxShare ||
				contextCompactionResponseHeadroom !== original.contextCompactionResponseHeadroom ||
				contextCompactionSummarizationMaxCharsPerMessage !==
					original.contextCompactionSummarizationMaxCharsPerMessage
			) {
				const ccPatch: Record<string, unknown> = {}
				if (contextCompactionEnabled !== original.contextCompactionEnabled)
					ccPatch.enabled = contextCompactionEnabled
				if (contextCompactionTriggerRatio !== original.contextCompactionTriggerRatio)
					ccPatch.trigger_ratio = asNumberOrUndefined(contextCompactionTriggerRatio)
				if (
					contextCompactionRecoveryTargetRatio !==
					original.contextCompactionRecoveryTargetRatio
				)
					ccPatch.recovery_target_ratio = asNumberOrUndefined(
						contextCompactionRecoveryTargetRatio
					)
				if (
					contextCompactionTargetUsageCapTokens !==
					original.contextCompactionTargetUsageCapTokens
				)
					ccPatch.target_usage_cap_tokens = asNumberOrNull(
						contextCompactionTargetUsageCapTokens
					)
				if (
					contextCompactionSummaryBatchMinTokens !==
					original.contextCompactionSummaryBatchMinTokens
				)
					ccPatch.summary_batch_min_tokens = asNumberOrUndefined(
						contextCompactionSummaryBatchMinTokens
					)
				if (
					contextCompactionSummaryBatchMaxTokens !==
					original.contextCompactionSummaryBatchMaxTokens
				)
					ccPatch.summary_batch_max_tokens = asNumberOrUndefined(
						contextCompactionSummaryBatchMaxTokens
					)
				if (
					contextCompactionPromptOverheadTokens !==
					original.contextCompactionPromptOverheadTokens
				)
					ccPatch.prompt_overhead_tokens = asNumberOrUndefined(
						contextCompactionPromptOverheadTokens
					)
				if (
					contextCompactionBlockingSummarizationEnabled !==
					original.contextCompactionBlockingSummarizationEnabled
				)
					ccPatch.blocking_summarization_enabled =
						contextCompactionBlockingSummarizationEnabled
				if (
					contextCompactionBlockingSummarizationTimeoutSeconds !==
					original.contextCompactionBlockingSummarizationTimeoutSeconds
				)
					ccPatch.blocking_summarization_timeout_seconds = asNumberOrUndefined(
						contextCompactionBlockingSummarizationTimeoutSeconds
					)
				if (
					contextCompactionToolResultMaxShare !==
					original.contextCompactionToolResultMaxShare
				)
					ccPatch.tool_result_max_share = asNumberOrUndefined(
						contextCompactionToolResultMaxShare
					)
				if (
					contextCompactionToolResultHardCap !==
					original.contextCompactionToolResultHardCap
				)
					ccPatch.tool_result_hard_cap = asNumberOrUndefined(
						contextCompactionToolResultHardCap
					)
				if (
					contextCompactionToolResultsCombinedMaxShare !==
					original.contextCompactionToolResultsCombinedMaxShare
				)
					ccPatch.tool_results_combined_max_share = asNumberOrUndefined(
						contextCompactionToolResultsCombinedMaxShare
					)
				if (
					contextCompactionResponseHeadroom !== original.contextCompactionResponseHeadroom
				)
					ccPatch.response_headroom = asNumberOrUndefined(
						contextCompactionResponseHeadroom
					)
				if (
					contextCompactionSummarizationMaxCharsPerMessage !==
					original.contextCompactionSummarizationMaxCharsPerMessage
				)
					ccPatch.summarization_max_chars_per_message = asNumberOrNull(
						contextCompactionSummarizationMaxCharsPerMessage
					)
				aiPatch.context_compaction = ccPatch
			}

			if (
				mediaImagesEnabled !== original.mediaImagesEnabled ||
				mediaImagesModel !== original.mediaImagesModel ||
				mediaImagesDefaultSize !== original.mediaImagesDefaultSize ||
				mediaImagesDefaultSteps !== original.mediaImagesDefaultSteps ||
				mediaImagesDefaultN !== original.mediaImagesDefaultN ||
				mediaImagesMaxN !== original.mediaImagesMaxN ||
				mediaVideosEnabled !== original.mediaVideosEnabled ||
				mediaAudioEnabled !== original.mediaAudioEnabled
			) {
				const mediaPatch: Record<string, unknown> = {}
				if (
					mediaImagesEnabled !== original.mediaImagesEnabled ||
					mediaImagesModel !== original.mediaImagesModel ||
					mediaImagesDefaultSize !== original.mediaImagesDefaultSize ||
					mediaImagesDefaultSteps !== original.mediaImagesDefaultSteps ||
					mediaImagesDefaultN !== original.mediaImagesDefaultN ||
					mediaImagesMaxN !== original.mediaImagesMaxN
				) {
					const imgPatch: Record<string, unknown> = {}
					if (mediaImagesEnabled !== original.mediaImagesEnabled)
						imgPatch.enabled = mediaImagesEnabled
					if (mediaImagesModel !== original.mediaImagesModel)
						imgPatch.model = mediaImagesModel || null
					if (mediaImagesDefaultSize !== original.mediaImagesDefaultSize)
						imgPatch.default_size = mediaImagesDefaultSize || undefined
					if (mediaImagesDefaultSteps !== original.mediaImagesDefaultSteps)
						imgPatch.default_steps = asNumberOrNull(mediaImagesDefaultSteps)
					if (mediaImagesDefaultN !== original.mediaImagesDefaultN)
						imgPatch.default_n = asNumberOrUndefined(mediaImagesDefaultN)
					if (mediaImagesMaxN !== original.mediaImagesMaxN)
						imgPatch.max_n = asNumberOrUndefined(mediaImagesMaxN)
					mediaPatch.images = imgPatch
				}
				if (mediaVideosEnabled !== original.mediaVideosEnabled)
					mediaPatch.videos = { enabled: mediaVideosEnabled }
				if (mediaAudioEnabled !== original.mediaAudioEnabled)
					mediaPatch.audio = { enabled: mediaAudioEnabled }
				aiPatch.media = mediaPatch
			}

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { ai: aiPatch },
					expected_versions: ctx.response.versions ?? null,
				},
			})
			if (result.error) {
				if (result.response.status === 409) {
					saveError = 'settings were updated elsewhere. reload and try again.'
				} else {
					const detail = result.error?.detail
					saveError = typeof detail === 'string' ? detail : 'failed to save settings'
				}
				return
			}
			ctx.setFromResponse(result.data!)
			saveSuccess = 'saved'
		} catch (e) {
			console.error('Failed to save AI settings', e)
			saveError = 'failed to save settings'
		} finally {
			isSaving = false
		}
	}

	// suppress unused import warning - formatJsonObject used in SettingsAI component context
	void formatJsonObject
</script>

<div class="flex flex-col gap-4">
	<div class="flex items-center justify-between gap-2">
		<div>
			{#if saveError}
				<p class="text-sm text-red-400">{saveError}</p>
			{:else if saveSuccess}
				<p class="text-sm text-emerald-400">{saveSuccess}</p>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={ctx.fetchSettings}
				disabled={ctx.isFetching || isSaving}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				reload
			</Button>
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={resetDraft}
				disabled={!hasChanges || isSaving}
			>
				<RotateCcw class="mr-1.5 h-4 w-4" />
				reset
			</Button>
			<Button class="rounded-xl" onclick={save} disabled={!hasChanges || isSaving}>
				<Save class="mr-1.5 h-4 w-4" />
				{isSaving ? 'saving...' : 'save'}
			</Button>
		</div>
	</div>

	<SettingsAI
		bind:defaultAgentIds
		bind:memoryEnable
		bind:memorySimilarityThreshold
		bind:memoryTopK
		bind:memoryPostProcessingTurns
		bind:chatContextEnabled
		bind:chatContextMode
		bind:chatContextTopK
		bind:chatContextSimilarityThreshold
		bind:retrievalTurns
		bind:retrievalPreBuild
		bind:taskDefaultModelId
		bind:taskThreadMetadataModelId
		bind:taskThreadMaintenanceModelId
		bind:taskInputAutocompleteModelId
		bind:taskSummarizationModelId
		bind:taskMemoryPostProcessingModelId
		bind:taskWebSearchModelId
		bind:taskAssetDescriptionModelId
		bind:taskAssetTextExtractionModelId
		bind:taskMaintenanceMaxCharsPerMessage
		bind:attachmentImageDecayIterations
		bind:attachmentAudioDecayIterations
		bind:attachmentVideoDecayIterations
		bind:contextCompactionEnabled
		bind:contextCompactionTriggerRatio
		bind:contextCompactionRecoveryTargetRatio
		bind:contextCompactionTargetUsageCapTokens
		bind:contextCompactionSummaryBatchMinTokens
		bind:contextCompactionSummaryBatchMaxTokens
		bind:contextCompactionPromptOverheadTokens
		bind:contextCompactionBlockingSummarizationEnabled
		bind:contextCompactionBlockingSummarizationTimeoutSeconds
		bind:contextCompactionToolResultMaxShare
		bind:contextCompactionToolResultHardCap
		bind:contextCompactionToolResultsCombinedMaxShare
		bind:contextCompactionResponseHeadroom
		bind:contextCompactionSummarizationMaxCharsPerMessage
		bind:mediaImagesEnabled
		bind:mediaImagesModel
		bind:mediaImagesDefaultSize
		bind:mediaImagesDefaultSteps
		bind:mediaImagesDefaultN
		bind:mediaImagesMaxN
		bind:mediaVideosEnabled
		bind:mediaAudioEnabled
		agents={ctx.agents}
		models={ctx.models}
		providers={ctx.providers}
		isFetchingAgents={ctx.isFetchingAgents}
		isFetchingModels={ctx.isFetchingModels}
		agentsError={ctx.agentsError}
		modelsError={ctx.modelsError}
	/>
</div>
