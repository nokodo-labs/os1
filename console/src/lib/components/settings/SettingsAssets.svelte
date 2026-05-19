<script lang="ts">
	import type { Schemas } from '$lib/api'

	type Model = Schemas['Model']
	type Provider = Schemas['Provider']

	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'

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

	function modelLabel(m: Model): string {
		const name = m.display_name || m.name || m.id
		const provider = providers.find((p) => p.id === m.provider_id)
		const providerName = provider?.name || m.provider_id
		const adapterType = provider?.adapter_type
		const modelAdapter = m.adapter
		const adapterPart = adapterType
			? modelAdapter && modelAdapter !== adapterType
				? `${adapterType}/${modelAdapter}`
				: adapterType
			: (modelAdapter ?? null)
		return [name, providerName, adapterPart].filter(Boolean).join(' · ')
	}

	type Props = {
		defaultEmbeddingModelId?: string
		// vector db
		vectorDatabaseProvider?: VectorDatabaseProvider
		vectorDatabaseUrl?: string
		vectorDatabaseQdrantUseGrpc?: boolean
		vectorDatabaseQdrantApiKey?: string
		vectorDatabaseChromaApiKey?: string
		vectorDatabasePineconeApiKey?: string
		vectorDatabaseWeaviateApiKey?: string
		vectorDatabaseMilvusToken?: string
		vectorDatabaseRedisPassword?: string
		vectorDatabaseOpensearchApiKey?: string
		// vector settings
		vectorCollectionTemplate?: string
		vectorSparseEnabled?: boolean
		vectorFusionAlgorithm?: string
		vectorNormalizeScores?: boolean
		// embeddings
		embeddingsVectorSize?: string
		embeddingsBatchSize?: string
		// rerank
		rerankDefaultStrategy?: string
		rerankTopK?: string
		// storage
		storageBackend?: StorageBackend
		storageLocalRootPath?: string
		storageS3EndpointUrl?: string
		storageS3Bucket?: string
		storageS3Region?: string
		storageS3AccessKeyId?: string
		storageS3SecretAccessKey?: string
		storageS3Prefix?: string
		storageS3PresignedUrlTtl?: string
		storageS3MultipartThreshold?: string
		storageS3MultipartChunkSize?: string
		storageS3MaxRetries?: string
		storageS3RetryMode?: 'legacy' | 'standard' | 'adaptive'
		// auxiliary
		models?: Model[]
		providers?: Provider[]
		isFetchingModels?: boolean
		modelsError?: string | null
	}

	let {
		defaultEmbeddingModelId = $bindable(''),
		vectorDatabaseProvider = $bindable('qdrant'),
		vectorDatabaseUrl = $bindable(''),
		vectorDatabaseQdrantUseGrpc = $bindable(true),
		vectorDatabaseQdrantApiKey = $bindable(''),
		vectorDatabaseChromaApiKey = $bindable(''),
		vectorDatabasePineconeApiKey = $bindable(''),
		vectorDatabaseWeaviateApiKey = $bindable(''),
		vectorDatabaseMilvusToken = $bindable(''),
		vectorDatabaseRedisPassword = $bindable(''),
		vectorDatabaseOpensearchApiKey = $bindable(''),
		vectorCollectionTemplate = $bindable(''),
		vectorSparseEnabled = $bindable(true),
		vectorFusionAlgorithm = $bindable('rrf'),
		vectorNormalizeScores = $bindable(true),
		embeddingsVectorSize = $bindable(''),
		embeddingsBatchSize = $bindable(''),
		rerankDefaultStrategy = $bindable('native'),
		rerankTopK = $bindable(''),
		storageBackend = $bindable('local'),
		storageLocalRootPath = $bindable(''),
		storageS3EndpointUrl = $bindable(''),
		storageS3Bucket = $bindable(''),
		storageS3Region = $bindable(''),
		storageS3AccessKeyId = $bindable(''),
		storageS3SecretAccessKey = $bindable(''),
		storageS3Prefix = $bindable(''),
		storageS3PresignedUrlTtl = $bindable(''),
		storageS3MultipartThreshold = $bindable(''),
		storageS3MultipartChunkSize = $bindable(''),
		storageS3MaxRetries = $bindable(''),
		storageS3RetryMode = $bindable<'legacy' | 'standard' | 'adaptive'>('adaptive'),
		models = [],
		providers = [],
		isFetchingModels = false,
		modelsError = null,
	}: Props = $props()

	function getModelLabel(modelId: string): string {
		if (!modelId) return 'none'
		const m = models.find((x) => x.id === modelId)
		return m ? modelLabel(m) : modelId
	}

	const embeddingModels = $derived(models.filter((m) => m.model_type === 'embedding'))
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>assets</CardTitle>
		<CardDescription>
			vector database, embeddings, reranking, and file storage configuration.
		</CardDescription>
	</CardHeader>
	<CardContent class="space-y-6">
		<!-- embedding model + vector db provider -->
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="assets_embedding_model">default embedding model</Label>
				<p class="text-xs text-zinc-500">
					model used to embed text when no per-request override is set.
				</p>
				{#if isFetchingModels}
					<p class="text-xs text-zinc-500">loading…</p>
				{/if}
				<Select
					type="single"
					value={defaultEmbeddingModelId}
					onValueChange={(v: string) => {
						defaultEmbeddingModelId = v ?? ''
					}}
				>
					<SelectTrigger class="rounded-xl">
						{getModelLabel(defaultEmbeddingModelId)}
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="">none</SelectItem>
						{#each embeddingModels as m (m.id)}
							<SelectItem value={m.id}>{modelLabel(m)}</SelectItem>
						{/each}
					</SelectContent>
				</Select>
			</div>
			<div class="space-y-2">
				<Label for="assets_vector_db_provider">vector database provider</Label>
				<p class="text-xs text-zinc-500">
					backend used for storing and querying vector embeddings.
				</p>
				<Select
					type="single"
					value={vectorDatabaseProvider}
					onValueChange={(v: string) => {
						vectorDatabaseProvider = (v ?? 'qdrant') as VectorDatabaseProvider
					}}
				>
					<SelectTrigger class="rounded-xl">
						{vectorDatabaseProvider}
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="qdrant">qdrant</SelectItem>
						<SelectItem value="chroma">chroma</SelectItem>
						<SelectItem value="pinecone">pinecone</SelectItem>
						<SelectItem value="weaviate">weaviate</SelectItem>
						<SelectItem value="milvus">milvus</SelectItem>
						<SelectItem value="pgvector">pgvector</SelectItem>
						<SelectItem value="redis">redis</SelectItem>
						<SelectItem value="opensearch">opensearch</SelectItem>
					</SelectContent>
				</Select>
			</div>
		</div>

		<div class="space-y-2">
			<Label for="assets_vector_db_url">vector database endpoint</Label>
			<p class="text-xs text-zinc-500">
				connection URL or host for the selected vector database.
			</p>
			<Input
				id="assets_vector_db_url"
				bind:value={vectorDatabaseUrl}
				placeholder={vectorDatabaseProvider === 'qdrant' ? 'qdrant:6334' : ''}
				class="rounded-xl"
			/>
		</div>

		{#if vectorDatabaseProvider === 'qdrant'}
			<div
				class="flex items-center justify-between rounded-xl border border-zinc-800 px-4 py-3"
			>
				<div class="space-y-1">
					<Label for="assets_qdrant_use_grpc">use qdrant gRPC</Label>
					<p class="text-xs text-zinc-500">
						when enabled, a scheme-less host:port like qdrant:6334 is treated as the
						gRPC endpoint.
					</p>
				</div>
				<Switch id="assets_qdrant_use_grpc" bind:checked={vectorDatabaseQdrantUseGrpc} />
			</div>
		{/if}

		{#if vectorDatabaseProvider !== 'pgvector'}
			<h4 class="pt-2 text-sm font-medium text-zinc-400">vector database API key</h4>
			<div class="max-w-sm">
				{#if vectorDatabaseProvider === 'qdrant'}
					<div class="space-y-2">
						<Label for="assets_qdrant_api_key">qdrant api key</Label>
						<Input
							id="assets_qdrant_api_key"
							bind:value={vectorDatabaseQdrantApiKey}
							type="password"
							class="rounded-xl"
						/>
					</div>
				{:else if vectorDatabaseProvider === 'chroma'}
					<div class="space-y-2">
						<Label for="assets_chroma_api_key">chroma api key</Label>
						<Input
							id="assets_chroma_api_key"
							bind:value={vectorDatabaseChromaApiKey}
							type="password"
							class="rounded-xl"
						/>
					</div>
				{:else if vectorDatabaseProvider === 'pinecone'}
					<div class="space-y-2">
						<Label for="assets_pinecone_api_key">pinecone api key</Label>
						<Input
							id="assets_pinecone_api_key"
							bind:value={vectorDatabasePineconeApiKey}
							type="password"
							class="rounded-xl"
						/>
					</div>
				{:else if vectorDatabaseProvider === 'weaviate'}
					<div class="space-y-2">
						<Label for="assets_weaviate_api_key">weaviate api key</Label>
						<Input
							id="assets_weaviate_api_key"
							bind:value={vectorDatabaseWeaviateApiKey}
							type="password"
							class="rounded-xl"
						/>
					</div>
				{:else if vectorDatabaseProvider === 'milvus'}
					<div class="space-y-2">
						<Label for="assets_milvus_token">milvus token</Label>
						<Input
							id="assets_milvus_token"
							bind:value={vectorDatabaseMilvusToken}
							type="password"
							class="rounded-xl"
						/>
					</div>
				{:else if vectorDatabaseProvider === 'redis'}
					<div class="space-y-2">
						<Label for="assets_redis_password">redis password</Label>
						<Input
							id="assets_redis_password"
							bind:value={vectorDatabaseRedisPassword}
							type="password"
							class="rounded-xl"
						/>
					</div>
				{:else if vectorDatabaseProvider === 'opensearch'}
					<div class="space-y-2">
						<Label for="assets_opensearch_api_key">opensearch api key</Label>
						<Input
							id="assets_opensearch_api_key"
							bind:value={vectorDatabaseOpensearchApiKey}
							type="password"
							class="rounded-xl"
						/>
					</div>
				{/if}
			</div>
		{/if}

		<h4 class="pt-2 text-sm font-medium text-zinc-400">vector settings</h4>
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="assets_collection_template">collection name template</Label>
				<Input
					id="assets_collection_template"
					bind:value={vectorCollectionTemplate}
					placeholder="nokodo-ai__{'{model}'}_bm25"
					class="rounded-xl"
				/>
				<p class="text-xs text-zinc-500">
					template for auto-generated collection names. use {'{'}}model} as a placeholder.
				</p>
			</div>
		</div>
		<div class="grid gap-4 md:grid-cols-2">
			<div
				class="flex items-center justify-between gap-2 rounded-xl border border-zinc-800 p-3"
			>
				<Label for="assets_sparse_enabled">sparse vectors (BM25)</Label>
				<Switch
					id="assets_sparse_enabled"
					checked={vectorSparseEnabled}
					onCheckedChange={(v) => {
						vectorSparseEnabled = v
					}}
				/>
			</div>
			<div
				class="flex items-center justify-between gap-2 rounded-xl border border-zinc-800 p-3"
			>
				<Label for="assets_normalize_scores">normalize scores</Label>
				<Switch
					id="assets_normalize_scores"
					checked={vectorNormalizeScores}
					onCheckedChange={(v) => {
						vectorNormalizeScores = v
					}}
				/>
			</div>
		</div>
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="assets_fusion_algorithm">fusion algorithm</Label>
				<p class="text-xs text-zinc-500">
					algorithm used to combine dense and sparse search scores.
				</p>
				<Select
					type="single"
					value={vectorFusionAlgorithm}
					onValueChange={(v: string) => {
						vectorFusionAlgorithm = v ?? 'rrf'
					}}
				>
					<SelectTrigger class="rounded-xl">
						{vectorFusionAlgorithm === 'rrf'
							? 'reciprocal rank fusion (RRF)'
							: 'distribution-based score fusion (DBSF)'}
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="rrf">reciprocal rank fusion (RRF)</SelectItem>
						<SelectItem value="dbsf">distribution-based score fusion (DBSF)</SelectItem>
					</SelectContent>
				</Select>
			</div>
		</div>

		<h4 class="pt-2 text-sm font-medium text-zinc-400">embeddings</h4>
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="assets_vector_size">vector size (dimensions)</Label>
				<p class="text-xs text-zinc-500">
					dimensions of the embedding vectors; must match the chosen model.
				</p>
				<Input
					id="assets_vector_size"
					type="number"
					bind:value={embeddingsVectorSize}
					placeholder="1536"
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="assets_batch_size">batch size</Label>
				<p class="text-xs text-zinc-500">
					texts embedded per API call during bulk vectorization.
				</p>
				<Input
					id="assets_batch_size"
					type="number"
					bind:value={embeddingsBatchSize}
					placeholder="64"
					class="rounded-xl"
				/>
			</div>
		</div>

		<h4 class="pt-2 text-sm font-medium text-zinc-400">reranking</h4>
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<Label for="assets_rerank_strategy">default strategy</Label>
				<p class="text-xs text-zinc-500">
					controls when and how results are reranked after retrieval.
				</p>
				<Select
					type="single"
					value={rerankDefaultStrategy}
					onValueChange={(v: string) => {
						rerankDefaultStrategy = v ?? 'native'
					}}
				>
					<SelectTrigger class="rounded-xl">
						{rerankDefaultStrategy}
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="none">none</SelectItem>
						<SelectItem value="native">native</SelectItem>
						<SelectItem value="external">external</SelectItem>
					</SelectContent>
				</Select>
			</div>
			<div class="space-y-2">
				<Label for="assets_rerank_top_k">rerank top-k</Label>
				<p class="text-xs text-zinc-500">final results kept after reranking.</p>
				<Input
					id="assets_rerank_top_k"
					type="number"
					bind:value={rerankTopK}
					placeholder="10"
					class="rounded-xl"
				/>
			</div>
		</div>

		<!-- storage -->
		<h4 class="pt-2 text-sm font-medium text-zinc-400">file storage</h4>
		<div class="space-y-2">
			<Label for="storage_backend">backend</Label>
			<p class="text-xs text-zinc-500">
				active storage system for uploaded files. only the selected backend is used.
			</p>
			<Select
				type="single"
				value={storageBackend}
				onValueChange={(v: string) => {
					storageBackend = (v ?? 'local') as StorageBackend
				}}
			>
				<SelectTrigger id="storage_backend" class="rounded-xl">
					{storageBackend}
				</SelectTrigger>
				<SelectContent>
					<SelectItem value="local">local</SelectItem>
					<SelectItem value="s3">s3</SelectItem>
				</SelectContent>
			</Select>
		</div>

		{#if storageBackend === 'local'}
			<div class="space-y-2">
				<Label for="storage_local_root">local root path</Label>
				<p class="text-xs text-zinc-500">root directory for local file storage.</p>
				<Input
					id="storage_local_root"
					bind:value={storageLocalRootPath}
					placeholder="data/uploads"
					class="rounded-xl"
				/>
			</div>
		{:else}
			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="s3_endpoint_url">endpoint url</Label>
					<p class="text-xs text-zinc-500">
						S3-compatible endpoint. leave empty for AWS S3.
					</p>
					<Input
						id="s3_endpoint_url"
						bind:value={storageS3EndpointUrl}
						placeholder="http://localhost:9000"
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_bucket">bucket</Label>
					<Input
						id="s3_bucket"
						bind:value={storageS3Bucket}
						placeholder="nokodo-ai"
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_region">region</Label>
					<Input
						id="s3_region"
						bind:value={storageS3Region}
						placeholder="us-east-1"
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_prefix">key prefix</Label>
					<Input
						id="s3_prefix"
						bind:value={storageS3Prefix}
						placeholder=""
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_access_key_id">access key id</Label>
					<Input
						id="s3_access_key_id"
						bind:value={storageS3AccessKeyId}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_secret_access_key">secret access key</Label>
					<Input
						id="s3_secret_access_key"
						type="password"
						bind:value={storageS3SecretAccessKey}
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_presigned_ttl">presigned URL TTL (seconds)</Label>
					<p class="text-xs text-zinc-500">
						how long presigned download URLs stay valid.
					</p>
					<Input
						id="s3_presigned_ttl"
						type="number"
						bind:value={storageS3PresignedUrlTtl}
						placeholder="3600"
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_multipart_threshold">multipart threshold (bytes)</Label>
					<p class="text-xs text-zinc-500">
						file size above which multipart upload is used.
					</p>
					<Input
						id="s3_multipart_threshold"
						type="number"
						bind:value={storageS3MultipartThreshold}
						placeholder="104857600"
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_multipart_chunk">multipart chunk size (bytes)</Label>
					<p class="text-xs text-zinc-500">size of each part in a multipart upload.</p>
					<Input
						id="s3_multipart_chunk"
						type="number"
						bind:value={storageS3MultipartChunkSize}
						placeholder="10485760"
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_max_retries">max retries</Label>
					<p class="text-xs text-zinc-500">
						maximum number of retry attempts on failed requests.
					</p>
					<Input
						id="s3_max_retries"
						type="number"
						bind:value={storageS3MaxRetries}
						placeholder="3"
						class="rounded-xl"
					/>
				</div>
				<div class="space-y-2">
					<Label for="s3_retry_mode">retry mode</Label>
					<p class="text-xs text-zinc-500">botocore retry strategy.</p>
					<Select
						value={storageS3RetryMode}
						onValueChange={(v: string) =>
							(storageS3RetryMode = v as 'legacy' | 'standard' | 'adaptive')}
					>
						<SelectTrigger id="s3_retry_mode" class="rounded-xl">
							<span class="truncate text-left">{storageS3RetryMode}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="legacy">legacy</SelectItem>
							<SelectItem value="standard">standard</SelectItem>
							<SelectItem value="adaptive">adaptive</SelectItem>
						</SelectContent>
					</Select>
				</div>
			</div>
		{/if}

		{#if modelsError}
			<p class="mt-3 text-xs text-red-300">{modelsError}</p>
		{/if}
	</CardContent>
</Card>
