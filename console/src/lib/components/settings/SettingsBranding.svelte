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
	import { Lock } from '@lucide/svelte'

	type Props = {
		siteName?: string
		logoUrl?: string
		faviconUrl?: string
		primaryColor?: string
		supportEmail?: string
		adminEmail?: string
		publicFrontendOrigin?: string
		publicCdnOrigin?: string
		publicConsoleOrigin?: string
		pwaManifestUrl?: string
		// read-only (write-locked)
		appVersion?: string
		analyticsKeyConfigured?: boolean
	}

	let {
		siteName = $bindable(''),
		logoUrl = $bindable(''),
		faviconUrl = $bindable(''),
		primaryColor = $bindable(''),
		supportEmail = $bindable(''),
		adminEmail = $bindable(''),
		publicFrontendOrigin = $bindable(''),
		publicCdnOrigin = $bindable(''),
		publicConsoleOrigin = $bindable(''),
		pwaManifestUrl = $bindable(''),
		appVersion = '',
		analyticsKeyConfigured = false,
	}: Props = $props()
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>branding</CardTitle>
		<CardDescription>public-facing brand configuration.</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="site_name">site name</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">
					display name shown in the browser tab, emails, and UI.
				</p>
				<Input id="site_name" bind:value={siteName} class="rounded-xl" />
			</div>
			<div class="space-y-2">
				<div class="flex items-center justify-between gap-2">
					<div class="flex items-center gap-2">
						<Label for="app_version">app version</Label>
						<SettingsPublicBadge />
					</div>
					<span
						class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
					>
						<Lock class="h-3 w-3" />
						env-only
					</span>
				</div>
				<Input id="app_version" value={appVersion} disabled class="rounded-xl" />
				<p class="text-xs text-zinc-500">set via environment variables only.</p>
			</div>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="primary_color">primary color</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">
					accent color used throughout the frontend (CSS hex value).
				</p>
				<Input
					id="primary_color"
					bind:value={primaryColor}
					placeholder="#6366f1"
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<div class="flex items-center justify-between gap-2">
					<Label for="analytics_key">analytics key</Label>
					<span
						class="inline-flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300"
					>
						<Lock class="h-3 w-3" />
						env-only
					</span>
				</div>
				<Input
					id="analytics_key"
					value={analyticsKeyConfigured ? '(configured)' : '(not set)'}
					disabled
					class="rounded-xl"
				/>
				<p class="text-xs text-zinc-500">set via environment variables only.</p>
			</div>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="support_email">support email</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">
					shown to users awaiting account approval or needing help.
				</p>
				<Input
					id="support_email"
					type="email"
					bind:value={supportEmail}
					placeholder="support@example.com"
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="admin_email">admin email</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">internal / escalation contact for operators.</p>
				<Input
					id="admin_email"
					type="email"
					bind:value={adminEmail}
					placeholder="admin@example.com"
					class="rounded-xl"
				/>
			</div>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="logo_url">logo url</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">
					URL for the app logo used in the sidebar and outgoing emails.
				</p>
				<Input
					id="logo_url"
					bind:value={logoUrl}
					placeholder="https://…"
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="favicon_url">favicon url</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">URL for the browser tab favicon.</p>
				<Input
					id="favicon_url"
					bind:value={faviconUrl}
					placeholder="https://…"
					class="rounded-xl"
				/>
			</div>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="public_frontend_origin">public frontend origin</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">
					base URL of the user-facing frontend; used to build absolute links in emails and
					OIDC.
				</p>
				<Input
					id="public_frontend_origin"
					bind:value={publicFrontendOrigin}
					placeholder="https://app.nokodo.net"
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Label for="public_cdn_origin">public cdn origin</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">base URL for CDN-hosted static assets.</p>
				<Input
					id="public_cdn_origin"
					bind:value={publicCdnOrigin}
					placeholder="https://cdn.nokodo.net"
					class="rounded-xl"
				/>
			</div>
		</div>

		<div class="space-y-2">
			<div class="flex items-center gap-2">
				<Label for="public_console_origin">public console origin</Label>
				<SettingsPublicBadge />
			</div>
			<p class="text-xs text-zinc-500">
				base URL of this admin console; used for OIDC redirect URIs and internal links.
			</p>
			<Input
				id="public_console_origin"
				bind:value={publicConsoleOrigin}
				placeholder="https://console.nokodo.net"
				class="rounded-xl"
			/>
		</div>

		<div class="space-y-2">
			<div class="flex items-center gap-2">
				<Label for="pwa_manifest_url">pwa manifest url</Label>
				<SettingsPublicBadge />
			</div>
			<Input
				id="pwa_manifest_url"
				bind:value={pwaManifestUrl}
				placeholder="https://cdn.example.com/manifest.json"
				class="rounded-xl"
			/>
			<p class="text-xs text-zinc-500">
				external manifest.json for PWA configuration. served directly in the frontend HTML.
			</p>
		</div>
	</CardContent>
</Card>
