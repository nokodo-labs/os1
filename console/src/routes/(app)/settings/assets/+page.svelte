<script lang="ts">
	import { api } from '$lib/api'
	import SettingsAssets from '$lib/components/settings/SettingsAssets.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { toRerankDefaultStrategy, toStringOrEmpty } from '$lib/settings/utils'
	import { asNumberOrUndefined } from '$lib/utils/settingsNumbers'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'

	type VectorDatabaseProvider =
		| 'qdrant'
		| 'chroma'
		| 'pinecone'
		| 'weaviate'
		| 'milvus'
		| 'pgvector'
		| 'redis'
		| 'opensearch'
	type StorageBackend = 'local' | 's3'

	const ctx = getSettingsContext()

	let defaultEmbeddingModelId = $state('')
	let vectorDatabaseProvider = $state<VectorDatabaseProvider>('qdrant')
	let vectorDatabaseUrl = $state('')
	let vectorDatabaseQdrantUseGrpc = $state(true)
	let vectorDatabaseQdrantApiKey = $state('')
	let vectorDatabaseChromaApiKey = $state('')
	let vectorDatabasePineconeApiKey = $state('')
	let vectorDatabaseWeaviateApiKey = $state('')
	let vectorDatabaseMilvusToken = $state('')
	let vectorDatabaseRedisPassword = $state('')
	let vectorDatabaseOpensearchApiKey = $state('')
	let vectorCollectionTemplate = $state('')
	let vectorSparseEnabled = $state(true)
	let vectorFusionAlgorithm = $state('rrf')
	let vectorNormalizeScores = $state(true)
	let embeddingsVectorSize = $state('')
	let embeddingsBatchSize = $state('')
	let embeddingsMaxConcurrency = $state('')
	let contentVectorizationLoader = $state('auto')
	let contentVectorizationChunkingAlgorithm = $state('auto')
	let contentVectorizationMaxBytes = $state('')
	let contentVectorizationTargetTokens = $state('')
	let contentVectorizationOverlapTokens = $state('')
	let contentVectorizationMaxChunks = $state('')
	let descriptionsMaxInputChars = $state('')
	let descriptionsMaxChars = $state('')
	let rerankDefaultStrategy = $state<'none' | 'external' | 'native'>('native')
	let rerankTopK = $state('')
	let storageBackend = $state<StorageBackend>('local')
	let storageLocalRootPath = $state('')
	let storageS3EndpointUrl = $state('')
	let storageS3Bucket = $state('')
	let storageS3Region = $state('')
	let storageS3AccessKeyId = $state('')
	let storageS3SecretAccessKey = $state('')
	let storageS3Prefix = $state('')
	let storageS3PresignedUrlTtl = $state('')
	let storageS3MultipartThreshold = $state('')
	let storageS3MultipartChunkSize = $state('')
	let storageS3MaxRetries = $state('')
	let storageS3RetryMode = $state<'legacy' | 'standard' | 'adaptive'>('adaptive')

	type Original = {
		defaultEmbeddingModelId: string
		vectorDatabaseProvider: VectorDatabaseProvider
		vectorDatabaseUrl: string
		vectorDatabaseQdrantUseGrpc: boolean
		vectorDatabaseQdrantApiKey: string
		vectorDatabaseChromaApiKey: string
		vectorDatabasePineconeApiKey: string
		vectorDatabaseWeaviateApiKey: string
		vectorDatabaseMilvusToken: string
		vectorDatabaseRedisPassword: string
		vectorDatabaseOpensearchApiKey: string
		vectorCollectionTemplate: string
		vectorSparseEnabled: boolean
		vectorFusionAlgorithm: string
		vectorNormalizeScores: boolean
		embeddingsVectorSize: string
		embeddingsBatchSize: string
		embeddingsMaxConcurrency: string
		contentVectorizationLoader: string
		contentVectorizationChunkingAlgorithm: string
		contentVectorizationMaxBytes: string
		contentVectorizationTargetTokens: string
		contentVectorizationOverlapTokens: string
		contentVectorizationMaxChunks: string
		descriptionsMaxInputChars: string
		descriptionsMaxChars: string
		rerankDefaultStrategy: 'none' | 'external' | 'native'
		rerankTopK: string
		storageBackend: StorageBackend
		storageLocalRootPath: string
		storageS3EndpointUrl: string
		storageS3Bucket: string
		storageS3Region: string
		storageS3AccessKeyId: string
		storageS3SecretAccessKey: string
		storageS3Prefix: string
		storageS3PresignedUrlTtl: string
		storageS3MultipartThreshold: string
		storageS3MultipartChunkSize: string
		storageS3MaxRetries: string
		storageS3RetryMode: 'legacy' | 'standard' | 'adaptive'
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const assets = r.data.assets
		defaultEmbeddingModelId = assets?.default_embedding_model_id ?? ''
		const vdb = assets?.vector_database
		vectorDatabaseProvider = (vdb?.provider as VectorDatabaseProvider) ?? 'qdrant'
		const activeProvider = vectorDatabaseProvider
		const qdrant = vdb?.qdrant
		const chroma = vdb?.chroma
		const pinecone = vdb?.pinecone
		const weaviate = vdb?.weaviate
		const milvus = vdb?.milvus
		const pgvector = vdb?.pgvector
		const redis = vdb?.redis
		const opensearch = vdb?.opensearch
		const activeDb =
			activeProvider === 'qdrant'
				? qdrant
				: activeProvider === 'chroma'
					? chroma
					: activeProvider === 'pinecone'
						? pinecone
						: activeProvider === 'weaviate'
							? weaviate
							: activeProvider === 'milvus'
								? milvus
								: activeProvider === 'pgvector'
									? pgvector
									: activeProvider === 'redis'
										? redis
										: opensearch
		vectorDatabaseUrl =
			activeProvider === 'qdrant' ? toStringOrEmpty(activeDb?.url) : (activeDb?.url ?? '')
		vectorDatabaseQdrantUseGrpc = qdrant?.use_grpc ?? true
		vectorDatabaseQdrantApiKey = qdrant?.api_key ?? ''
		vectorDatabaseChromaApiKey = chroma?.api_key ?? ''
		vectorDatabasePineconeApiKey = pinecone?.api_key ?? ''
		vectorDatabaseWeaviateApiKey = weaviate?.api_key ?? ''
		vectorDatabaseMilvusToken = milvus?.token ?? ''
		vectorDatabaseRedisPassword = redis?.password ?? ''
		vectorDatabaseOpensearchApiKey = opensearch?.api_key ?? ''
		const vector = assets?.vector
		vectorCollectionTemplate = toStringOrEmpty(vector?.collection_template)
		vectorSparseEnabled = vector?.sparse_vectors_enabled ?? true
		vectorFusionAlgorithm = vector?.fusion_algorithm ?? 'rrf'
		vectorNormalizeScores = vector?.normalize_scores ?? true
		const emb = assets?.embeddings
		embeddingsVectorSize = toStringOrEmpty(emb?.vector_size)
		embeddingsBatchSize = toStringOrEmpty(emb?.batch_size)
		embeddingsMaxConcurrency = toStringOrEmpty(emb?.max_concurrency)
		const cv = assets?.content_vectorization
		contentVectorizationLoader = cv?.loader ?? 'auto'
		contentVectorizationChunkingAlgorithm = cv?.chunking_algorithm ?? 'auto'
		contentVectorizationMaxBytes = toStringOrEmpty(cv?.max_bytes)
		contentVectorizationTargetTokens = toStringOrEmpty(cv?.target_tokens)
		contentVectorizationOverlapTokens = toStringOrEmpty(cv?.overlap_tokens)
		contentVectorizationMaxChunks = toStringOrEmpty(cv?.max_chunks)
		const desc = assets?.descriptions
		descriptionsMaxInputChars = toStringOrEmpty(desc?.max_input_chars)
		descriptionsMaxChars = toStringOrEmpty(desc?.max_chars)
		const rerank = assets?.rerank
		rerankDefaultStrategy = toRerankDefaultStrategy(rerank?.default_strategy)
		rerankTopK = toStringOrEmpty(rerank?.top_k)
		const storage = assets?.storage
		storageBackend = (storage?.backend ?? 'local') as StorageBackend
		storageLocalRootPath = toStringOrEmpty(storage?.local?.root_path)
		storageS3EndpointUrl = storage?.s3?.endpoint_url ?? ''
		storageS3Bucket = toStringOrEmpty(storage?.s3?.bucket)
		storageS3Region = toStringOrEmpty(storage?.s3?.region)
		storageS3AccessKeyId = storage?.s3?.access_key_id ?? ''
		storageS3SecretAccessKey = storage?.s3?.secret_access_key ?? ''
		storageS3Prefix = storage?.s3?.prefix ?? ''
		storageS3PresignedUrlTtl = toStringOrEmpty(storage?.s3?.presigned_url_ttl)
		storageS3MultipartThreshold = toStringOrEmpty(storage?.s3?.multipart_threshold)
		storageS3MultipartChunkSize = toStringOrEmpty(storage?.s3?.multipart_chunk_size)
		storageS3MaxRetries = toStringOrEmpty(storage?.s3?.max_retries)
		storageS3RetryMode = (storage?.s3?.retry_mode ?? 'adaptive') as
			| 'legacy'
			| 'standard'
			| 'adaptive'

		original = {
			defaultEmbeddingModelId,
			vectorDatabaseProvider,
			vectorDatabaseUrl,
			vectorDatabaseQdrantUseGrpc,
			vectorDatabaseQdrantApiKey,
			vectorDatabaseChromaApiKey,
			vectorDatabasePineconeApiKey,
			vectorDatabaseWeaviateApiKey,
			vectorDatabaseMilvusToken,
			vectorDatabaseRedisPassword,
			vectorDatabaseOpensearchApiKey,
			vectorCollectionTemplate,
			vectorSparseEnabled,
			vectorFusionAlgorithm,
			vectorNormalizeScores,
			embeddingsVectorSize,
			embeddingsBatchSize,
			embeddingsMaxConcurrency,
			contentVectorizationLoader,
			contentVectorizationChunkingAlgorithm,
			contentVectorizationMaxBytes,
			contentVectorizationTargetTokens,
			contentVectorizationOverlapTokens,
			contentVectorizationMaxChunks,
			descriptionsMaxInputChars,
			descriptionsMaxChars,
			rerankDefaultStrategy,
			rerankTopK,
			storageBackend,
			storageLocalRootPath,
			storageS3EndpointUrl,
			storageS3Bucket,
			storageS3Region,
			storageS3AccessKeyId,
			storageS3SecretAccessKey,
			storageS3Prefix,
			storageS3PresignedUrlTtl,
			storageS3MultipartThreshold,
			storageS3MultipartChunkSize,
			storageS3MaxRetries,
			storageS3RetryMode,
		}
	})

	const hasChanges = $derived(
		original !== null &&
			(defaultEmbeddingModelId !== original.defaultEmbeddingModelId ||
				vectorDatabaseProvider !== original.vectorDatabaseProvider ||
				vectorDatabaseUrl !== original.vectorDatabaseUrl ||
				vectorDatabaseQdrantUseGrpc !== original.vectorDatabaseQdrantUseGrpc ||
				vectorDatabaseQdrantApiKey !== original.vectorDatabaseQdrantApiKey ||
				vectorDatabaseChromaApiKey !== original.vectorDatabaseChromaApiKey ||
				vectorDatabasePineconeApiKey !== original.vectorDatabasePineconeApiKey ||
				vectorDatabaseWeaviateApiKey !== original.vectorDatabaseWeaviateApiKey ||
				vectorDatabaseMilvusToken !== original.vectorDatabaseMilvusToken ||
				vectorDatabaseRedisPassword !== original.vectorDatabaseRedisPassword ||
				vectorDatabaseOpensearchApiKey !== original.vectorDatabaseOpensearchApiKey ||
				vectorCollectionTemplate !== original.vectorCollectionTemplate ||
				vectorSparseEnabled !== original.vectorSparseEnabled ||
				vectorFusionAlgorithm !== original.vectorFusionAlgorithm ||
				vectorNormalizeScores !== original.vectorNormalizeScores ||
				embeddingsVectorSize !== original.embeddingsVectorSize ||
				embeddingsBatchSize !== original.embeddingsBatchSize ||
				embeddingsMaxConcurrency !== original.embeddingsMaxConcurrency ||
				contentVectorizationLoader !== original.contentVectorizationLoader ||
				contentVectorizationChunkingAlgorithm !==
					original.contentVectorizationChunkingAlgorithm ||
				contentVectorizationMaxBytes !== original.contentVectorizationMaxBytes ||
				contentVectorizationTargetTokens !== original.contentVectorizationTargetTokens ||
				contentVectorizationOverlapTokens !== original.contentVectorizationOverlapTokens ||
				contentVectorizationMaxChunks !== original.contentVectorizationMaxChunks ||
				descriptionsMaxInputChars !== original.descriptionsMaxInputChars ||
				descriptionsMaxChars !== original.descriptionsMaxChars ||
				rerankDefaultStrategy !== original.rerankDefaultStrategy ||
				rerankTopK !== original.rerankTopK ||
				storageBackend !== original.storageBackend ||
				storageLocalRootPath !== original.storageLocalRootPath ||
				storageS3EndpointUrl !== original.storageS3EndpointUrl ||
				storageS3Bucket !== original.storageS3Bucket ||
				storageS3Region !== original.storageS3Region ||
				storageS3AccessKeyId !== original.storageS3AccessKeyId ||
				storageS3SecretAccessKey !== original.storageS3SecretAccessKey ||
				storageS3Prefix !== original.storageS3Prefix ||
				storageS3PresignedUrlTtl !== original.storageS3PresignedUrlTtl ||
				storageS3MultipartThreshold !== original.storageS3MultipartThreshold ||
				storageS3MultipartChunkSize !== original.storageS3MultipartChunkSize ||
				storageS3MaxRetries !== original.storageS3MaxRetries ||
				storageS3RetryMode !== original.storageS3RetryMode)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		defaultEmbeddingModelId = original.defaultEmbeddingModelId
		vectorDatabaseProvider = original.vectorDatabaseProvider
		vectorDatabaseUrl = original.vectorDatabaseUrl
		vectorDatabaseQdrantUseGrpc = original.vectorDatabaseQdrantUseGrpc
		vectorDatabaseQdrantApiKey = original.vectorDatabaseQdrantApiKey
		vectorDatabaseChromaApiKey = original.vectorDatabaseChromaApiKey
		vectorDatabasePineconeApiKey = original.vectorDatabasePineconeApiKey
		vectorDatabaseWeaviateApiKey = original.vectorDatabaseWeaviateApiKey
		vectorDatabaseMilvusToken = original.vectorDatabaseMilvusToken
		vectorDatabaseRedisPassword = original.vectorDatabaseRedisPassword
		vectorDatabaseOpensearchApiKey = original.vectorDatabaseOpensearchApiKey
		vectorCollectionTemplate = original.vectorCollectionTemplate
		vectorSparseEnabled = original.vectorSparseEnabled
		vectorFusionAlgorithm = original.vectorFusionAlgorithm
		vectorNormalizeScores = original.vectorNormalizeScores
		embeddingsVectorSize = original.embeddingsVectorSize
		embeddingsBatchSize = original.embeddingsBatchSize
		embeddingsMaxConcurrency = original.embeddingsMaxConcurrency
		contentVectorizationLoader = original.contentVectorizationLoader
		contentVectorizationChunkingAlgorithm = original.contentVectorizationChunkingAlgorithm
		contentVectorizationMaxBytes = original.contentVectorizationMaxBytes
		contentVectorizationTargetTokens = original.contentVectorizationTargetTokens
		contentVectorizationOverlapTokens = original.contentVectorizationOverlapTokens
		contentVectorizationMaxChunks = original.contentVectorizationMaxChunks
		descriptionsMaxInputChars = original.descriptionsMaxInputChars
		descriptionsMaxChars = original.descriptionsMaxChars
		rerankDefaultStrategy = original.rerankDefaultStrategy
		rerankTopK = original.rerankTopK
		storageBackend = original.storageBackend
		storageLocalRootPath = original.storageLocalRootPath
		storageS3EndpointUrl = original.storageS3EndpointUrl
		storageS3Bucket = original.storageS3Bucket
		storageS3Region = original.storageS3Region
		storageS3AccessKeyId = original.storageS3AccessKeyId
		storageS3SecretAccessKey = original.storageS3SecretAccessKey
		storageS3Prefix = original.storageS3Prefix
		storageS3PresignedUrlTtl = original.storageS3PresignedUrlTtl
		storageS3MultipartThreshold = original.storageS3MultipartThreshold
		storageS3MultipartChunkSize = original.storageS3MultipartChunkSize
		storageS3MaxRetries = original.storageS3MaxRetries
		storageS3RetryMode = original.storageS3RetryMode
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const assetsPatch: Record<string, unknown> = {}

			if (defaultEmbeddingModelId !== original.defaultEmbeddingModelId)
				assetsPatch.default_embedding_model_id = defaultEmbeddingModelId || null

			if (
				vectorDatabaseProvider !== original.vectorDatabaseProvider ||
				vectorDatabaseUrl !== original.vectorDatabaseUrl ||
				vectorDatabaseQdrantUseGrpc !== original.vectorDatabaseQdrantUseGrpc ||
				vectorDatabaseQdrantApiKey !== original.vectorDatabaseQdrantApiKey ||
				vectorDatabaseChromaApiKey !== original.vectorDatabaseChromaApiKey ||
				vectorDatabasePineconeApiKey !== original.vectorDatabasePineconeApiKey ||
				vectorDatabaseWeaviateApiKey !== original.vectorDatabaseWeaviateApiKey ||
				vectorDatabaseMilvusToken !== original.vectorDatabaseMilvusToken ||
				vectorDatabaseRedisPassword !== original.vectorDatabaseRedisPassword ||
				vectorDatabaseOpensearchApiKey !== original.vectorDatabaseOpensearchApiKey
			) {
				const vdbPatch: Record<string, unknown> = {}
				if (vectorDatabaseProvider !== original.vectorDatabaseProvider)
					vdbPatch.provider = vectorDatabaseProvider
				if (
					vectorDatabaseProvider === 'qdrant' &&
					(vectorDatabaseUrl !== original.vectorDatabaseUrl ||
						vectorDatabaseQdrantUseGrpc !== original.vectorDatabaseQdrantUseGrpc ||
						vectorDatabaseQdrantApiKey !== original.vectorDatabaseQdrantApiKey)
				) {
					const q: Record<string, unknown> = {}
					if (vectorDatabaseUrl !== original.vectorDatabaseUrl)
						q.url = vectorDatabaseUrl || undefined
					if (vectorDatabaseQdrantUseGrpc !== original.vectorDatabaseQdrantUseGrpc)
						q.use_grpc = vectorDatabaseQdrantUseGrpc
					if (vectorDatabaseQdrantApiKey !== original.vectorDatabaseQdrantApiKey)
						q.api_key = vectorDatabaseQdrantApiKey || null
					vdbPatch.qdrant = q
				}
				if (
					vectorDatabaseProvider === 'chroma' &&
					(vectorDatabaseUrl !== original.vectorDatabaseUrl ||
						vectorDatabaseChromaApiKey !== original.vectorDatabaseChromaApiKey)
				) {
					vdbPatch.chroma = {
						url: vectorDatabaseUrl || null,
						api_key: vectorDatabaseChromaApiKey || null,
					}
				}
				if (
					vectorDatabaseProvider === 'pinecone' &&
					(vectorDatabaseUrl !== original.vectorDatabaseUrl ||
						vectorDatabasePineconeApiKey !== original.vectorDatabasePineconeApiKey)
				) {
					vdbPatch.pinecone = {
						url: vectorDatabaseUrl || null,
						api_key: vectorDatabasePineconeApiKey || null,
					}
				}
				if (
					vectorDatabaseProvider === 'weaviate' &&
					(vectorDatabaseUrl !== original.vectorDatabaseUrl ||
						vectorDatabaseWeaviateApiKey !== original.vectorDatabaseWeaviateApiKey)
				) {
					vdbPatch.weaviate = {
						url: vectorDatabaseUrl || null,
						api_key: vectorDatabaseWeaviateApiKey || null,
					}
				}
				if (
					vectorDatabaseProvider === 'milvus' &&
					(vectorDatabaseUrl !== original.vectorDatabaseUrl ||
						vectorDatabaseMilvusToken !== original.vectorDatabaseMilvusToken)
				) {
					vdbPatch.milvus = {
						url: vectorDatabaseUrl || null,
						token: vectorDatabaseMilvusToken || null,
					}
				}
				if (
					vectorDatabaseProvider === 'pgvector' &&
					vectorDatabaseUrl !== original.vectorDatabaseUrl
				) {
					vdbPatch.pgvector = { url: vectorDatabaseUrl || null }
				}
				if (
					vectorDatabaseProvider === 'redis' &&
					(vectorDatabaseUrl !== original.vectorDatabaseUrl ||
						vectorDatabaseRedisPassword !== original.vectorDatabaseRedisPassword)
				) {
					vdbPatch.redis = {
						url: vectorDatabaseUrl || null,
						password: vectorDatabaseRedisPassword || null,
					}
				}
				if (
					vectorDatabaseProvider === 'opensearch' &&
					(vectorDatabaseUrl !== original.vectorDatabaseUrl ||
						vectorDatabaseOpensearchApiKey !== original.vectorDatabaseOpensearchApiKey)
				) {
					vdbPatch.opensearch = {
						url: vectorDatabaseUrl || null,
						api_key: vectorDatabaseOpensearchApiKey || null,
					}
				}
				assetsPatch.vector_database = vdbPatch
			}

			if (
				vectorCollectionTemplate !== original.vectorCollectionTemplate ||
				vectorSparseEnabled !== original.vectorSparseEnabled ||
				vectorFusionAlgorithm !== original.vectorFusionAlgorithm ||
				vectorNormalizeScores !== original.vectorNormalizeScores
			) {
				const vp: Record<string, unknown> = {}
				if (vectorCollectionTemplate !== original.vectorCollectionTemplate)
					vp.collection_template = vectorCollectionTemplate || undefined
				if (vectorSparseEnabled !== original.vectorSparseEnabled)
					vp.sparse_vectors_enabled = vectorSparseEnabled
				if (vectorFusionAlgorithm !== original.vectorFusionAlgorithm)
					vp.fusion_algorithm = vectorFusionAlgorithm
				if (vectorNormalizeScores !== original.vectorNormalizeScores)
					vp.normalize_scores = vectorNormalizeScores
				assetsPatch.vector = vp
			}

			if (
				embeddingsVectorSize !== original.embeddingsVectorSize ||
				embeddingsBatchSize !== original.embeddingsBatchSize ||
				embeddingsMaxConcurrency !== original.embeddingsMaxConcurrency
			) {
				const ep: Record<string, unknown> = {}
				if (embeddingsVectorSize !== original.embeddingsVectorSize)
					ep.vector_size = asNumberOrUndefined(embeddingsVectorSize)
				if (embeddingsBatchSize !== original.embeddingsBatchSize)
					ep.batch_size = asNumberOrUndefined(embeddingsBatchSize)
				if (embeddingsMaxConcurrency !== original.embeddingsMaxConcurrency)
					ep.max_concurrency = embeddingsMaxConcurrency
						? asNumberOrUndefined(embeddingsMaxConcurrency)
						: null
				assetsPatch.embeddings = ep
			}

			if (
				contentVectorizationLoader !== original.contentVectorizationLoader ||
				contentVectorizationChunkingAlgorithm !==
					original.contentVectorizationChunkingAlgorithm ||
				contentVectorizationMaxBytes !== original.contentVectorizationMaxBytes ||
				contentVectorizationTargetTokens !== original.contentVectorizationTargetTokens ||
				contentVectorizationOverlapTokens !== original.contentVectorizationOverlapTokens ||
				contentVectorizationMaxChunks !== original.contentVectorizationMaxChunks
			) {
				const cvp: Record<string, unknown> = {}
				if (contentVectorizationLoader !== original.contentVectorizationLoader)
					cvp.loader = contentVectorizationLoader
				if (
					contentVectorizationChunkingAlgorithm !==
					original.contentVectorizationChunkingAlgorithm
				)
					cvp.chunking_algorithm = contentVectorizationChunkingAlgorithm
				if (contentVectorizationMaxBytes !== original.contentVectorizationMaxBytes)
					cvp.max_bytes = contentVectorizationMaxBytes
						? asNumberOrUndefined(contentVectorizationMaxBytes)
						: null
				if (contentVectorizationTargetTokens !== original.contentVectorizationTargetTokens)
					cvp.target_tokens = asNumberOrUndefined(contentVectorizationTargetTokens)
				if (
					contentVectorizationOverlapTokens !== original.contentVectorizationOverlapTokens
				)
					cvp.overlap_tokens = asNumberOrUndefined(contentVectorizationOverlapTokens)
				if (contentVectorizationMaxChunks !== original.contentVectorizationMaxChunks)
					cvp.max_chunks = contentVectorizationMaxChunks
						? asNumberOrUndefined(contentVectorizationMaxChunks)
						: null
				assetsPatch.content_vectorization = cvp
			}

			if (
				descriptionsMaxInputChars !== original.descriptionsMaxInputChars ||
				descriptionsMaxChars !== original.descriptionsMaxChars
			) {
				const dp: Record<string, unknown> = {}
				if (descriptionsMaxInputChars !== original.descriptionsMaxInputChars)
					dp.max_input_chars = descriptionsMaxInputChars
						? asNumberOrUndefined(descriptionsMaxInputChars)
						: null
				if (descriptionsMaxChars !== original.descriptionsMaxChars)
					dp.max_chars = descriptionsMaxChars
						? asNumberOrUndefined(descriptionsMaxChars)
						: null
				assetsPatch.descriptions = dp
			}

			if (
				rerankDefaultStrategy !== original.rerankDefaultStrategy ||
				rerankTopK !== original.rerankTopK
			) {
				const rp: Record<string, unknown> = {}
				if (rerankDefaultStrategy !== original.rerankDefaultStrategy)
					rp.default_strategy = rerankDefaultStrategy || undefined
				if (rerankTopK !== original.rerankTopK) rp.top_k = asNumberOrUndefined(rerankTopK)
				assetsPatch.rerank = rp
			}

			if (
				storageBackend !== original.storageBackend ||
				storageLocalRootPath !== original.storageLocalRootPath ||
				storageS3EndpointUrl !== original.storageS3EndpointUrl ||
				storageS3Bucket !== original.storageS3Bucket ||
				storageS3Region !== original.storageS3Region ||
				storageS3AccessKeyId !== original.storageS3AccessKeyId ||
				storageS3SecretAccessKey !== original.storageS3SecretAccessKey ||
				storageS3Prefix !== original.storageS3Prefix ||
				storageS3PresignedUrlTtl !== original.storageS3PresignedUrlTtl ||
				storageS3MultipartThreshold !== original.storageS3MultipartThreshold ||
				storageS3MultipartChunkSize !== original.storageS3MultipartChunkSize ||
				storageS3MaxRetries !== original.storageS3MaxRetries ||
				storageS3RetryMode !== original.storageS3RetryMode
			) {
				const sp: Record<string, unknown> = {}
				if (storageBackend !== original.storageBackend) sp.backend = storageBackend
				if (
					storageLocalRootPath !== original.storageLocalRootPath &&
					storageBackend === 'local'
				) {
					sp.local = { root_path: storageLocalRootPath || undefined }
				}
				if (storageBackend === 's3') {
					const s3: Record<string, unknown> = {}
					if (storageS3EndpointUrl !== original.storageS3EndpointUrl)
						s3.endpoint_url = storageS3EndpointUrl || null
					if (storageS3Bucket !== original.storageS3Bucket)
						s3.bucket = storageS3Bucket || undefined
					if (storageS3Region !== original.storageS3Region)
						s3.region = storageS3Region || undefined
					if (storageS3AccessKeyId !== original.storageS3AccessKeyId)
						s3.access_key_id = storageS3AccessKeyId || null
					if (storageS3SecretAccessKey !== original.storageS3SecretAccessKey)
						s3.secret_access_key = storageS3SecretAccessKey || null
					if (storageS3Prefix !== original.storageS3Prefix)
						s3.prefix = storageS3Prefix || undefined
					if (storageS3PresignedUrlTtl !== original.storageS3PresignedUrlTtl)
						s3.presigned_url_ttl = asNumberOrUndefined(storageS3PresignedUrlTtl)
					if (storageS3MultipartThreshold !== original.storageS3MultipartThreshold)
						s3.multipart_threshold = asNumberOrUndefined(storageS3MultipartThreshold)
					if (storageS3MultipartChunkSize !== original.storageS3MultipartChunkSize)
						s3.multipart_chunk_size = asNumberOrUndefined(storageS3MultipartChunkSize)
					if (storageS3MaxRetries !== original.storageS3MaxRetries)
						s3.max_retries = asNumberOrUndefined(storageS3MaxRetries)
					if (storageS3RetryMode !== original.storageS3RetryMode)
						s3.retry_mode = storageS3RetryMode
					sp.s3 = s3
				}
				assetsPatch.storage = sp
			}

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { assets: assetsPatch },
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
			console.error('Failed to save assets settings', e)
			saveError = 'failed to save settings'
		} finally {
			isSaving = false
		}
	}
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

	<SettingsAssets
		bind:defaultEmbeddingModelId
		bind:vectorDatabaseProvider
		bind:vectorDatabaseUrl
		bind:vectorDatabaseQdrantUseGrpc
		bind:vectorDatabaseQdrantApiKey
		bind:vectorDatabaseChromaApiKey
		bind:vectorDatabasePineconeApiKey
		bind:vectorDatabaseWeaviateApiKey
		bind:vectorDatabaseMilvusToken
		bind:vectorDatabaseRedisPassword
		bind:vectorDatabaseOpensearchApiKey
		bind:vectorCollectionTemplate
		bind:vectorSparseEnabled
		bind:vectorFusionAlgorithm
		bind:vectorNormalizeScores
		bind:embeddingsVectorSize
		bind:embeddingsBatchSize
		bind:embeddingsMaxConcurrency
		bind:contentVectorizationLoader
		bind:contentVectorizationChunkingAlgorithm
		bind:contentVectorizationMaxBytes
		bind:contentVectorizationTargetTokens
		bind:contentVectorizationOverlapTokens
		bind:contentVectorizationMaxChunks
		bind:descriptionsMaxInputChars
		bind:descriptionsMaxChars
		bind:rerankDefaultStrategy
		bind:rerankTopK
		bind:storageBackend
		bind:storageLocalRootPath
		bind:storageS3EndpointUrl
		bind:storageS3Bucket
		bind:storageS3Region
		bind:storageS3AccessKeyId
		bind:storageS3SecretAccessKey
		bind:storageS3Prefix
		bind:storageS3PresignedUrlTtl
		bind:storageS3MultipartThreshold
		bind:storageS3MultipartChunkSize
		bind:storageS3MaxRetries
		bind:storageS3RetryMode
		models={ctx.models}
		providers={ctx.providers}
		isFetchingModels={ctx.isFetchingModels}
		modelsError={ctx.modelsError}
	/>
</div>
