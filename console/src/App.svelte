<script lang="ts">
	const shortcuts = [
		{
			label: "Users",
			description: "Manage members, invitations, and roles",
		},
		{ label: "Projects", description: "Review project status and quotas" },
		{
			label: "Providers",
			description: "Configure runtime providers and credentials",
		},
		{
			label: "Activity",
			description: "Inspect audit logs and recent actions",
		},
	];
</script>

<main class="min-h-screen bg-slate-950 text-slate-100">
	<section class="mx-auto flex max-w-5xl flex-col gap-8 px-6 py-16">
		<header class="space-y-3">
			<p class="text-sm uppercase tracking-[0.3em] text-slate-400">
				nokodo
			</p>
			<h1 class="text-4xl font-semibold">Console</h1>
			<p class="max-w-2xl text-base text-slate-400">
				High-leverage administrative tooling for operators. This
				scaffold intentionally keeps styles minimal so we can snap stock
				shadcn components in place without customization.
			</p>
		</header>

		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			{#each shortcuts as shortcut}
				<article
					class="rounded-lg border border-slate-800 bg-slate-900/80 p-5 shadow-lg shadow-black/30"
				>
					<p class="text-sm text-slate-500">Shortcut</p>
					<p class="text-xl font-medium text-slate-100">
						{shortcut.label}
					</p>
					<p class="text-sm text-slate-400">{shortcut.description}</p>
				</article>
			{/each}
		</div>

		<footer class="text-xs text-slate-500">
			Authentication, API clients, and shadcn integration arrive next.
		</footer>
	</section>
</main>
