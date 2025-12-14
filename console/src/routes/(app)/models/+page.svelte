<script lang="ts">
	import {
		api,
		type Model,
		type ModelCreate,
		type ModelUpdate,
		type Provider,
	} from "$lib/api";
	import EmptyState from "$lib/components/EmptyState.svelte";
	import NokodoLoader from "$lib/components/NokodoLoader.svelte";
	import { Button } from "$lib/components/ui/button";
	import {
		Card,
		CardContent,
		CardDescription,
		CardFooter,
		CardHeader,
		CardTitle,
	} from "$lib/components/ui/card";
	import { Input } from "$lib/components/ui/input";
	import { Label } from "$lib/components/ui/label";
	import {
		Select,
		SelectContent,
		SelectItem,
		SelectTrigger,
	} from "$lib/components/ui/select";
	import { Switch } from "$lib/components/ui/switch";
	import { Pencil, Plus, Trash2 } from "@lucide/svelte";
	import { onMount } from "svelte";

	let models = $state<Model[]>([]);
	let providers = $state<Provider[]>([]);
	let showModal = $state(false);
	let modalMode = $state<"create" | "edit">("create");
	let isLoading = $state(false);
	let isFetching = $state(true);
	let editingId = $state<string | null>(null);
	let error = $state<string | null>(null);
	let submitError = $state<string | null>(null);

	const hasProviders = $derived(providers.length > 0);
	const addModelDisabledReason = "add a provider to enable model creation.";
	const emptyStateNoProvidersMessage = "no providers configured yet.";
	const emptyStateNoProvidersHint = "add a provider first to create models.";
	const emptyStateNoModelsMessage = "no models configured yet.";

	// Form state
	let formState = $state<ModelCreate>({
		name: "",
		display_name: "",
		model_type: "llm",
		provider_id: "",
		enabled: true,
		is_autofetched: false,
	});

	// Optional numeric fields are modeled as strings so they can be blank.
	let contextWindowInput = $state<string>("");
	let inputCostInput = $state<string>("");
	let outputCostInput = $state<string>("");

	async function fetchData() {
		isFetching = true;
		try {
			const [modelsData, providersData] = await Promise.all([
				api.getModels(),
				api.getProviders(),
			]);
			models = modelsData;
			providers = providersData;
		} catch (e) {
			console.error("Failed to fetch data", e);
			error = "Failed to load models";
		} finally {
			isFetching = false;
		}
	}

	onMount(() => {
		fetchData();
	});

	function openCreateModal() {
		if (!hasProviders) return;
		modalMode = "create";
		formState = {
			name: "",
			display_name: "",
			model_type: "llm",
			provider_id: providers.length > 0 ? providers[0].id : "",
			enabled: true,
			is_autofetched: false,
		};
		contextWindowInput = "";
		inputCostInput = "";
		outputCostInput = "";
		showModal = true;
		submitError = null;
	}

	function openEditModal(model: Model) {
		modalMode = "edit";
		editingId = model.id;
		formState = {
			name: model.name,
			display_name: model.display_name || "",
			model_type: model.model_type,
			provider_id: model.provider_id,
			enabled: model.enabled,
			is_autofetched: model.is_autofetched,
		};
		contextWindowInput =
			model.context_window === null || model.context_window === undefined
				? ""
				: String(model.context_window);
		inputCostInput =
			model.input_cost === null || model.input_cost === undefined
				? ""
				: String(model.input_cost);
		outputCostInput =
			model.output_cost === null || model.output_cost === undefined
				? ""
				: String(model.output_cost);
		showModal = true;
		submitError = null;
	}

	function parseOptionalNumber(value: string): number | null {
		const trimmed = value.trim();
		if (!trimmed) return null;
		const parsed = Number(trimmed);
		return Number.isFinite(parsed) ? parsed : null;
	}

	async function handleSubmit(e: Event) {
		e.preventDefault();
		isLoading = true;
		submitError = null;

		if (modalMode === "create" && !formState.provider_id) {
			submitError = "a provider is required to create a model.";
			isLoading = false;
			return;
		}

		try {
			if (modalMode === "create") {
				const createPayload: ModelCreate = {
					...formState,
				};
				const contextWindow = parseOptionalNumber(contextWindowInput);
				const inputCost = parseOptionalNumber(inputCostInput);
				const outputCost = parseOptionalNumber(outputCostInput);
				if (contextWindow !== null)
					createPayload.context_window = contextWindow;
				if (inputCost !== null) createPayload.input_cost = inputCost;
				if (outputCost !== null) createPayload.output_cost = outputCost;
				await api.createModel(createPayload);
			} else if (editingId) {
				// Exclude provider_id from update
				const { provider_id, ...rest } = formState;
				const updatePayload: ModelUpdate = {
					...rest,
					context_window: parseOptionalNumber(contextWindowInput),
					input_cost: parseOptionalNumber(inputCostInput),
					output_cost: parseOptionalNumber(outputCostInput),
				};
				await api.updateModel(editingId, updatePayload);
			}
			showModal = false;
			await fetchData();
		} catch (e: any) {
			console.error("Failed to save model", e);
			submitError = e.message || "Failed to save model";
		} finally {
			isLoading = false;
		}
	}

	async function handleDeleteFromModal() {
		if (!editingId) return;
		if (!confirm("Are you sure you want to delete this model?")) return;
		isLoading = true;
		try {
			await api.deleteModel(editingId);
			showModal = false;
			await fetchData();
		} catch (e) {
			console.error("Failed to delete model", e);
			submitError = "Failed to delete model";
		} finally {
			isLoading = false;
		}
	}

	async function handleDelete(id: string) {
		if (!confirm("Are you sure you want to delete this model?")) return;
		try {
			await api.deleteModel(id);
			await fetchData();
		} catch (e) {
			console.error("Failed to delete model", e);
			alert("Failed to delete model");
		}
	}

	function getProviderName(id: string) {
		const p = providers.find((p) => p.id === id);
		return p ? p.name : id;
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">models</h2>
			<p class="text-zinc-400">manage your AI models.</p>
		</div>
		{#if hasProviders}
			<Button onclick={openCreateModal}>
				<Plus class="mr-2 h-4 w-4" />
				add model
			</Button>
		{:else}
			<div class="flex flex-col items-end gap-1">
				<span title={addModelDisabledReason}>
					<Button onclick={openCreateModal} disabled>
						<Plus class="mr-2 h-4 w-4" />
						add model
					</Button>
				</span>
				<a
					href="/providers"
					class="text-xs text-zinc-500 underline underline-offset-4 hover:text-zinc-300"
				>
					{addModelDisabledReason}
				</a>
			</div>
		{/if}
	</div>

	{#if isFetching}
		<div class="flex h-64 items-center justify-center">
			<NokodoLoader />
		</div>
	{:else if error}
		<div class="rounded-md bg-red-500/10 p-4 text-red-500">
			{error}
		</div>
	{:else}
		<div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
			{#each models as model}
				<Card class="bg-zinc-900 border-zinc-800 text-zinc-100">
					<CardHeader
						class="flex flex-row items-start justify-between space-y-0 pb-2"
					>
						<CardTitle class="text-base font-medium">
							{model.display_name || model.name}
						</CardTitle>
						<div class="flex gap-2">
							<Button
								variant="ghost"
								size="icon"
								class="h-8 w-8 text-zinc-400 hover:text-zinc-100"
								onclick={() => openEditModal(model)}
							>
								<Pencil class="h-4 w-4" />
							</Button>
							<Button
								variant="ghost"
								size="icon"
								class="h-8 w-8 text-zinc-400 hover:text-red-500"
								onclick={() => handleDelete(model.id)}
							>
								<Trash2 class="h-4 w-4" />
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						<div class="text-sm text-zinc-400 mb-4">
							{getProviderName(model.provider_id)} • {model.model_type}
						</div>
						<div class="flex items-center gap-2">
							<div
								class={`h-2 w-2 rounded-full ${
									model.enabled
										? "bg-green-500"
										: "bg-zinc-700"
								}`}
							></div>
							<span class="text-xs text-zinc-500">
								{model.enabled ? "enabled" : "disabled"}
							</span>
							{#if model.is_autofetched}
								<span class="text-xs text-blue-500 ml-2"
									>autofetched</span
								>
							{/if}
						</div>
					</CardContent>
				</Card>
			{/each}

			{#if models.length === 0}
				{#if !hasProviders}
					<EmptyState
						message={emptyStateNoProvidersMessage}
						hint={emptyStateNoProvidersHint}
					/>
				{:else}
					<EmptyState message={emptyStateNoModelsMessage} />
				{/if}
			{/if}
		</div>
	{/if}
</div>

{#if showModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
	>
		<Card class="w-full max-w-lg border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader>
				<CardTitle
					>{modalMode === "create"
						? "add model"
						: "edit model"}</CardTitle
				>
				<CardDescription>configure model details</CardDescription>
			</CardHeader>
			<form onsubmit={handleSubmit}>
				<CardContent
					class="space-y-4 max-h-[60vh] overflow-y-auto pr-2"
				>
					{#if submitError}
						<div
							class="rounded-md bg-red-500/10 p-3 text-sm text-red-500"
						>
							{submitError}
						</div>
					{/if}

					<div class="space-y-2">
						<Label for="provider">provider</Label>
						<Select
							value={formState.provider_id}
							onValueChange={(value: string) =>
								(formState.provider_id = value)}
						>
							<SelectTrigger class="rounded-xl">
								<span class="truncate text-left">
									{formState.provider_id
										? getProviderName(formState.provider_id)
										: "select provider"}
								</span>
							</SelectTrigger>
							<SelectContent>
								{#each providers as provider}
									<SelectItem value={provider.id}
										>{provider.name}</SelectItem
									>
								{/each}
							</SelectContent>
						</Select>
					</div>

					<div class="space-y-2">
						<Label for="name">model name (id)</Label>
						<Input
							id="name"
							placeholder="gpt-4-turbo"
							bind:value={formState.name}
							disabled={modalMode === "edit" &&
								formState.is_autofetched}
							class="rounded-xl"
						/>
						<p class="text-xs text-zinc-500">
							the exact model identifier used by the provider API.
						</p>
					</div>

					<div class="space-y-2">
						<Label for="display_name">display name</Label>
						<Input
							id="display_name"
							placeholder="GPT-4 Turbo"
							bind:value={formState.display_name}
							class="rounded-xl"
						/>
					</div>

					<div class="space-y-2">
						<Label for="type">type</Label>
						<Select
							value={formState.model_type}
							onValueChange={(value: Model["model_type"]) =>
								(formState.model_type = value)}
						>
							<SelectTrigger class="rounded-xl">
								<span class="truncate text-left">
									{formState.model_type}
								</span>
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="llm">LLM</SelectItem>
								<SelectItem value="embedding"
									>embedding</SelectItem
								>
								<SelectItem value="image_generation"
									>image generation</SelectItem
								>
								<SelectItem value="audio">audio</SelectItem>
								<SelectItem value="video">video</SelectItem>
							</SelectContent>
						</Select>
					</div>

					<div class="grid gap-4 sm:grid-cols-2">
						<div class="space-y-2">
							<Label for="context"
								>context window (optional)</Label
							>
							<Input
								id="context"
								type="number"
								placeholder="optional"
								bind:value={contextWindowInput}
								class="rounded-xl"
							/>
							<p class="text-xs text-zinc-500">optional</p>
						</div>
						<div class="space-y-2">
							<Label for="input_cost"
								>input cost ($ / 1M tokens) (optional)</Label
							>
							<Input
								id="input_cost"
								type="number"
								step="0.0001"
								placeholder="optional"
								bind:value={inputCostInput}
								class="rounded-xl"
							/>
							<p class="text-xs text-zinc-500">optional</p>
						</div>
						<div class="space-y-2">
							<Label for="output_cost"
								>output cost ($ / 1M tokens) (optional)</Label
							>
							<Input
								id="output_cost"
								type="number"
								step="0.0001"
								placeholder="optional"
								bind:value={outputCostInput}
								class="rounded-xl"
							/>
							<p class="text-xs text-zinc-500">optional</p>
						</div>
					</div>

					<div
						class="flex items-center justify-between rounded-xl border border-zinc-800 p-4"
					>
						<div class="space-y-0.5">
							<Label>enabled</Label>
							<div class="text-sm text-zinc-500">
								make this model available for use
							</div>
						</div>
						<Switch bind:checked={formState.enabled} />
					</div>
				</CardContent>
				<CardFooter class="flex justify-between gap-2">
					{#if modalMode === "edit"}
						<Button
							type="button"
							variant="destructive"
							class="rounded-xl"
							disabled={isLoading}
							onclick={handleDeleteFromModal}
						>
							delete
						</Button>
					{:else}
						<div></div>
					{/if}
					<div class="flex justify-end gap-2">
						<Button
							type="button"
							variant="outline"
							class="rounded-xl"
							onclick={() => (showModal = false)}
						>
							cancel
						</Button>
						<Button
							type="submit"
							disabled={isLoading}
							class="rounded-xl"
						>
							{isLoading
								? "saving..."
								: modalMode === "create"
									? "add model"
									: "save changes"}
						</Button>
					</div>
				</CardFooter>
			</form>
		</Card>
	</div>
{/if}
