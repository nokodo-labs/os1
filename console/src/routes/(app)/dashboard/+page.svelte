<script lang="ts">
	import { api, unwrap } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import {
		Activity,
		Bot,
		Brain,
		CalendarDays,
		FileText,
		Folder,
		ListChecks,
		MessageSquare,
		Server,
		Shield,
		StickyNote,
		Users,
	} from '@lucide/svelte'
	import { onMount } from 'svelte'

	type StatCard = {
		label: string
		value: string | number
		icon: typeof Users
		color: string
	}

	let isLoading = $state(true)
	let error = $state<string | null>(null)

	let stats = $state<StatCard[]>([])

	async function loadStats() {
		isLoading = true
		error = null
		try {
			const [
				userCount,
				agentCount,
				models,
				providers,
				threadCount,
				noteCount,
				groupCount,
				roleCount,
				promptCount,
				reminderListCount,
				calendarCount,
			] = await Promise.all([
				api
					.GET('/v1/users/count')
					.then((r) => unwrap(r))
					.catch(() => 0),
				api
					.GET('/v1/agents/count')
					.then((r) => unwrap(r))
					.catch(() => 0),
				api
					.GET('/v1/models')
					.then((r) => unwrap(r))
					.catch(() => []),
				api
					.GET('/v1/providers')
					.then((r) => unwrap(r))
					.catch(() => []),
				api
					.GET('/v1/threads/count')
					.then((r) => unwrap(r))
					.catch(() => 0),
				api
					.GET('/v1/notes/count')
					.then((r) => unwrap(r))
					.catch(() => 0),
				api
					.GET('/v1/groups/count')
					.then((r) => unwrap(r))
					.catch(() => 0),
				api
					.GET('/v1/roles/count')
					.then((r) => unwrap(r))
					.catch(() => 0),
				api
					.GET('/v1/prompts/count')
					.then((r) => unwrap(r))
					.catch(() => 0),
				api
					.GET('/v1/reminder-lists/count')
					.then((r) => unwrap(r))
					.catch(() => 0),
				api
					.GET('/v1/calendars/count')
					.then((r) => unwrap(r))
					.catch(() => 0),
			])

			stats = [
				{
					label: 'users',
					value: userCount,
					icon: Users,
					color: 'text-blue-400',
				},
				{
					label: 'groups',
					value: groupCount,
					icon: Folder,
					color: 'text-indigo-400',
				},
				{
					label: 'roles',
					value: roleCount,
					icon: Shield,
					color: 'text-teal-400',
				},
				{
					label: 'agents',
					value: agentCount,
					icon: Bot,
					color: 'text-emerald-400',
				},
				{
					label: 'models',
					value: models.length,
					icon: Brain,
					color: 'text-purple-400',
				},
				{
					label: 'providers',
					value: providers.length,
					icon: Server,
					color: 'text-amber-400',
				},
				{
					label: 'threads',
					value: threadCount,
					icon: MessageSquare,
					color: 'text-cyan-400',
				},
				{
					label: 'prompts',
					value: promptCount,
					icon: FileText,
					color: 'text-fuchsia-400',
				},
				{
					label: 'notes',
					value: noteCount,
					icon: StickyNote,
					color: 'text-pink-400',
				},
				{
					label: 'reminder lists',
					value: reminderListCount,
					icon: ListChecks,
					color: 'text-lime-400',
				},
				{
					label: 'calendars',
					value: calendarCount,
					icon: CalendarDays,
					color: 'text-rose-400',
				},
			]
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'failed to load stats'
		} finally {
			isLoading = false
		}
	}

	onMount(() => {
		loadStats()
	})
</script>

<div class="min-h-0 flex-1 overflow-y-auto">
	<div class="space-y-6">
		<div class="flex items-center justify-between">
			<div>
				<h2 class="text-2xl font-bold tracking-tight">dashboard</h2>
				<p class="text-zinc-400">overview of your system.</p>
			</div>
		</div>

		{#if isLoading}
			<div class="flex min-h-[50vh] items-center justify-center">
				<NokodoLoader />
			</div>
		{:else if error}
			<div
				class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
			>
				{error}
			</div>
		{:else}
			<!-- stat cards -->
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
				{#each stats as stat (stat.label)}
					<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
						<CardContent class="flex items-center gap-4 p-5">
							<div
								class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-800"
							>
								<stat.icon class="h-5 w-5 {stat.color}" />
							</div>
							<div>
								<div class="text-2xl font-bold">{stat.value}</div>
								<div class="text-sm text-zinc-400">{stat.label}</div>
							</div>
						</CardContent>
					</Card>
				{/each}
			</div>
		{/if}

		<!-- placeholder panels for future charts -->
		<div class="grid gap-6 lg:grid-cols-2">
			<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Activity class="h-4 w-4 text-zinc-400" />
						usage over time
					</CardTitle>
					<CardDescription>messages, threads, and active users per day.</CardDescription>
				</CardHeader>
				<CardContent>
					<div
						class="flex h-48 items-center justify-center rounded-xl border border-dashed border-zinc-800 text-sm text-zinc-500"
					>
						chart coming soon
					</div>
				</CardContent>
			</Card>

			<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Brain class="h-4 w-4 text-zinc-400" />
						model usage
					</CardTitle>
					<CardDescription>
						token consumption and cost breakdown by model.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div
						class="flex h-48 items-center justify-center rounded-xl border border-dashed border-zinc-800 text-sm text-zinc-500"
					>
						charts coming soon
					</div>
				</CardContent>
			</Card>
		</div>
	</div>
</div>
