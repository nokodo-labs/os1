<script lang="ts">
	import type { BackgroundType } from '$lib/api'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'

	type ThemeMode = 'light' | 'dark' | 'system'

	const backgroundOptions: { value: BackgroundType; label: string }[] = [
		{ value: 'galaxy', label: 'galaxy' },
		{ value: 'darkveil', label: 'dark veil' },
		{ value: 'lightbends', label: 'light bends' },
		{ value: 'lightrays', label: 'light rays' },
		{ value: 'silk', label: 'silk' },
		{ value: 'fog', label: 'fog' },
		{ value: 'clouds', label: 'clouds' },
		{ value: 'clouds-dark', label: 'clouds dark' },
		{ value: 'clouds2', label: 'clouds 2' },
		{ value: 'clouds2-dark', label: 'clouds 2 dark' },
		{ value: 'grainient', label: 'grainient' },
		{ value: 'iridescence', label: 'iridescence' },
		{ value: 'static', label: 'static' },
		{ value: 'none', label: 'none' },
	]

	function backgroundLabel(v: string): string {
		return backgroundOptions.find((o) => o.value === v)?.label ?? v
	}

	function themeLabel(v: ThemeMode): string {
		if (v === 'light') return 'light'
		if (v === 'dark') return 'dark'
		return 'system'
	}

	type Props = {
		defaultTheme?: ThemeMode
		defaultBackground?: BackgroundType | null
		authPagesBackground?: BackgroundType | null
		sidebarCollapsed?: boolean
	}

	let {
		defaultTheme = $bindable('system'),
		defaultBackground = $bindable(null),
		authPagesBackground = $bindable(null),
		sidebarCollapsed = $bindable(false),
	}: Props = $props()
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>UI</CardTitle>
		<CardDescription>console UX defaults.</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		<div class="space-y-2">
			<Label for="default_theme">default theme</Label>
			<p class="text-xs text-zinc-500">
				color scheme applied to the frontend app by default.
			</p>
			<Select
				value={defaultTheme}
				onValueChange={(v: string) => (defaultTheme = v as ThemeMode)}
			>
				<SelectTrigger id="default_theme" class="rounded-xl">
					<span class="truncate text-left">{themeLabel(defaultTheme)}</span>
				</SelectTrigger>
				<SelectContent>
					<SelectItem value="system">system</SelectItem>
					<SelectItem value="light">light</SelectItem>
					<SelectItem value="dark">dark</SelectItem>
				</SelectContent>
			</Select>
		</div>

		<div class="flex items-center justify-between">
			<div class="space-y-0.5">
				<Label for="sidebar_collapsed">sidebar collapsed</Label>
				<p class="text-xs text-zinc-500">collapse sidebar by default.</p>
			</div>
			<Switch
				id="sidebar_collapsed"
				checked={sidebarCollapsed}
				onCheckedChange={(v: boolean) => (sidebarCollapsed = v)}
			/>
		</div>

		<div class="space-y-2">
			<Label for="default_background">default background</Label>
			<p class="text-xs text-zinc-500">
				animated background shown in the main app interface.
			</p>
			<Select
				value={defaultBackground || 'darkveil'}
				onValueChange={(v: string) => (defaultBackground = v as BackgroundType)}
			>
				<SelectTrigger id="default_background" class="rounded-xl">
					<span class="truncate text-left"
						>{backgroundLabel(defaultBackground || 'darkveil')}</span
					>
				</SelectTrigger>
				<SelectContent>
					{#each backgroundOptions as opt (opt.value)}
						<SelectItem value={opt.value}>{opt.label}</SelectItem>
					{/each}
				</SelectContent>
			</Select>
		</div>

		<div class="space-y-2">
			<Label for="auth_pages_background">auth pages background</Label>
			<p class="text-xs text-zinc-500">
				animated background shown on login and signup pages.
			</p>
			<Select
				value={authPagesBackground || 'lightrays'}
				onValueChange={(v: string) => (authPagesBackground = v as BackgroundType)}
			>
				<SelectTrigger id="auth_pages_background" class="rounded-xl">
					<span class="truncate text-left"
						>{backgroundLabel(authPagesBackground || 'lightrays')}</span
					>
				</SelectTrigger>
				<SelectContent>
					{#each backgroundOptions as opt (opt.value)}
						<SelectItem value={opt.value}>{opt.label}</SelectItem>
					{/each}
				</SelectContent>
			</Select>
		</div>
	</CardContent>
</Card>
