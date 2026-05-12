<script lang="ts">
	import SettingsPublicBadge from '$lib/components/settings/SettingsPublicBadge.svelte'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'

	type Props = {
		baseUrl?: string
		faviconUrl?: string
		appleTouchIconUrl?: string
		sidebarLogoUrl?: string
		splashLogoUrl?: string
	}

	let {
		baseUrl = $bindable(''),
		faviconUrl = $bindable(''),
		appleTouchIconUrl = $bindable(''),
		sidebarLogoUrl = $bindable(''),
		splashLogoUrl = $bindable(''),
	}: Props = $props()
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>media</CardTitle>
		<CardDescription>
			URL overrides for individual frontend media assets. these take precedence over the base
			URL.
		</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		<div class="space-y-2">
			<div class="flex items-center gap-2">
				<Label for="media_base_url">base URL</Label>
				<SettingsPublicBadge />
			</div>
			<p class="text-xs text-zinc-500">
				fallback base URL for all media assets not explicitly overridden below.
			</p>
			<Input
				id="media_base_url"
				bind:value={baseUrl}
				placeholder="https://cdn.nokodo.net/media"
				class="rounded-xl"
			/>
		</div>
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="media_favicon_url">favicon URL</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">
					overrides the branding favicon for frontend pages.
				</p>
				<Input
					id="media_favicon_url"
					bind:value={faviconUrl}
					placeholder="https://…"
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="media_apple_touch_icon_url">Apple touch icon URL</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">
					icon used when adding the app to an iOS home screen.
				</p>
				<Input
					id="media_apple_touch_icon_url"
					bind:value={appleTouchIconUrl}
					placeholder="https://…"
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="media_sidebar_logo_url">sidebar logo URL</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">logo shown in the frontend sidebar.</p>
				<Input
					id="media_sidebar_logo_url"
					bind:value={sidebarLogoUrl}
					placeholder="https://…"
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="media_splash_logo_url">splash logo URL</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">logo shown on the splash/loading screen.</p>
				<Input
					id="media_splash_logo_url"
					bind:value={splashLogoUrl}
					placeholder="https://…"
					class="rounded-xl"
				/>
			</div>
		</div>
	</CardContent>
</Card>
