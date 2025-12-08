<script lang="ts">
	import { auth } from "$lib/auth.svelte";
	import { LayoutDashboard, Server } from "@lucide/svelte";
	import Providers from "./Providers.svelte";

	let activeTab = $state("dashboard");
</script>

<div class="flex min-h-screen bg-zinc-950 text-zinc-100">
	<!-- Sidebar -->
	<aside class="flex w-64 flex-col border-r border-zinc-800 p-6">
		<div class="mb-8">
			<p class="text-sm uppercase tracking-[0.3em] text-zinc-400">
				nokodo
			</p>
			<h1 class="text-xl font-semibold">console</h1>
		</div>

		<nav class="flex-1 space-y-2">
			<button
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {activeTab ===
				'dashboard'
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
				onclick={() => (activeTab = "dashboard")}
			>
				<LayoutDashboard class="h-4 w-4" />
				dashboard
			</button>
			<button
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {activeTab ===
				'providers'
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
				onclick={() => (activeTab = "providers")}
			>
				<Server class="h-4 w-4" />
				providers
			</button>
		</nav>

		<button
			class="mt-auto text-left text-sm text-zinc-400 hover:text-zinc-100"
			onclick={() => auth.logout()}
		>
			sign out
		</button>
	</aside>

	<!-- Main Content -->
	<main class="flex-1 p-8">
		{#if activeTab === "dashboard"}
			<div class="space-y-6">
				<div>
					<h2 class="text-2xl font-bold tracking-tight">dashboard</h2>
					<p class="text-zinc-400">overview of your system.</p>
				</div>
				<div
					class="rounded-lg border border-dashed border-zinc-800 p-12 text-center text-zinc-500"
				>
					dashboard content coming soon
				</div>
			</div>
		{:else if activeTab === "providers"}
			<Providers />
		{/if}
	</main>
</div>
