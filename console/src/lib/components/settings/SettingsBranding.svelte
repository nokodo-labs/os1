<script lang="ts">
	import SettingsAssetSourceRow from '$lib/components/settings/SettingsAssetSourceRow.svelte'
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

	type OptionalAssetSource = 'default' | 'cdn' | 'custom' | 'disabled'

	type PwaAssetDraft = {
		source: OptionalAssetSource
		url: string
	}

	type PwaManifestAssetsDraft = {
		icon_1024_maskable: PwaAssetDraft
		icon_512_any: PwaAssetDraft
		shortcut_notes: PwaAssetDraft
		shortcut_reminders: PwaAssetDraft
		shortcut_calendar: PwaAssetDraft
		shortcut_messages: PwaAssetDraft
		shortcut_projects: PwaAssetDraft
		shortcut_library: PwaAssetDraft
		shortcut_social: PwaAssetDraft
		shortcut_settings: PwaAssetDraft
		screenshot_narrow_1: PwaAssetDraft
		screenshot_narrow_2: PwaAssetDraft
		screenshot_narrow_3: PwaAssetDraft
		screenshot_narrow_4: PwaAssetDraft
		screenshot_narrow_5: PwaAssetDraft
		screenshot_wide_1: PwaAssetDraft
		screenshot_wide_2: PwaAssetDraft
		screenshot_wide_3: PwaAssetDraft
		screenshot_wide_4: PwaAssetDraft
		screenshot_wide_5: PwaAssetDraft
		screenshot_wide_6: PwaAssetDraft
		screenshot_wide_7: PwaAssetDraft
		screenshot_wide_8: PwaAssetDraft
	}

	function asset(): PwaAssetDraft {
		return { source: 'default', url: '' }
	}

	function defaultPwaAssets(): PwaManifestAssetsDraft {
		return {
			icon_1024_maskable: asset(),
			icon_512_any: asset(),
			shortcut_notes: asset(),
			shortcut_reminders: asset(),
			shortcut_calendar: asset(),
			shortcut_messages: asset(),
			shortcut_projects: asset(),
			shortcut_library: asset(),
			shortcut_social: asset(),
			shortcut_settings: asset(),
			screenshot_narrow_1: asset(),
			screenshot_narrow_2: asset(),
			screenshot_narrow_3: asset(),
			screenshot_narrow_4: asset(),
			screenshot_narrow_5: asset(),
			screenshot_wide_1: asset(),
			screenshot_wide_2: asset(),
			screenshot_wide_3: asset(),
			screenshot_wide_4: asset(),
			screenshot_wide_5: asset(),
			screenshot_wide_6: asset(),
			screenshot_wide_7: asset(),
			screenshot_wide_8: asset(),
		}
	}

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
		pwaAssets?: PwaManifestAssetsDraft
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
		pwaAssets = $bindable(defaultPwaAssets()),
		appVersion = '',
		analyticsKeyConfigured = false,
	}: Props = $props()

	function stripTrailingSlash(url: string): string {
		return url.replace(/\/+$/, '')
	}

	function cdnPath(path: string): string {
		const trimmed = publicCdnOrigin.trim()
		const base = trimmed ? stripTrailingSlash(trimmed) : '{cdn}'
		return `${base}/static/os1/${path}`
	}

	function defaultPath(path: string): string {
		return `https://nokodo.net/static/os1/${path}`
	}

	function frontendPath(path: string): string {
		const trimmed = publicFrontendOrigin.trim()
		const base = trimmed ? stripTrailingSlash(trimmed) : '{frontend}'
		return `${base}${path}`
	}
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>branding</CardTitle>
		<CardDescription>
			public identity, public origins, and PWA manifest configuration.
		</CardDescription>
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
				<Input id="site_name" bind:value={siteName} placeholder="OS1" class="rounded-xl" />
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
				<p class="text-xs text-zinc-500">brand metadata URL</p>
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
				<p class="text-xs text-zinc-500">
					brand metadata URL. the browser tab favicon uses media settings.
				</p>
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
				<p class="text-xs text-zinc-500">
					used only by the autogenerated PWA manifest for app icons and screenshots.
				</p>
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

		<div class="space-y-5 rounded-xl border border-zinc-800 bg-zinc-950/40 p-4">
			<div class="space-y-1">
				<p class="text-sm font-medium text-zinc-100">generated manifest assets</p>
				<p class="text-xs text-zinc-500">
					blank manifest URL uses /system/manifest.json. each file below can stay on the
					built-in default, use the same path under public CDN origin, use a full custom
					URL, or be omitted from the generated manifest.
				</p>
			</div>

			<div class="space-y-3">
				<p class="text-xs font-medium tracking-wide text-zinc-400 uppercase">app icons</p>
				<div class="grid gap-3 md:grid-cols-2">
					<SettingsAssetSourceRow
						id="pwa_icon_1024_maskable"
						title="1024 maskable icon"
						description="maskable PNG used by install prompts"
						bind:source={pwaAssets.icon_1024_maskable.source}
						bind:url={pwaAssets.icon_1024_maskable.url}
						defaultUrl={defaultPath('icon-1024-maskable.png')}
						cdnUrl={cdnPath('icon-1024-maskable.png')}
						allowDisabled
						customPlaceholder="https://cdn.example.com/static/os1/icon-1024-maskable.png"
					/>
					<SettingsAssetSourceRow
						id="pwa_icon_512_any"
						title="512 any icon"
						description="any-purpose PNG app icon and Apple touch default"
						bind:source={pwaAssets.icon_512_any.source}
						bind:url={pwaAssets.icon_512_any.url}
						defaultUrl={defaultPath('icon-512-any.png')}
						cdnUrl={cdnPath('icon-512-any.png')}
						allowDisabled
						customPlaceholder="https://cdn.example.com/static/os1/icon-512-any.png"
					/>
				</div>
			</div>

			<div class="space-y-3">
				<p class="text-xs font-medium tracking-wide text-zinc-400 uppercase">
					shortcut icons
				</p>
				<div class="grid gap-3 md:grid-cols-2">
					<SettingsAssetSourceRow
						id="pwa_shortcut_notes"
						title="notes"
						description="shortcut icon PNG"
						bind:source={pwaAssets.shortcut_notes.source}
						bind:url={pwaAssets.shortcut_notes.url}
						defaultUrl={frontendPath('/shortcuts/notes.png')}
						cdnUrl={cdnPath('shortcuts/notes.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_shortcut_reminders"
						title="reminders"
						description="shortcut icon PNG"
						bind:source={pwaAssets.shortcut_reminders.source}
						bind:url={pwaAssets.shortcut_reminders.url}
						defaultUrl={frontendPath('/shortcuts/reminders.png')}
						cdnUrl={cdnPath('shortcuts/reminders.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_shortcut_calendar"
						title="calendar"
						description="shortcut icon PNG"
						bind:source={pwaAssets.shortcut_calendar.source}
						bind:url={pwaAssets.shortcut_calendar.url}
						defaultUrl={frontendPath('/shortcuts/calendar.png')}
						cdnUrl={cdnPath('shortcuts/calendar.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_shortcut_messages"
						title="messages"
						description="shortcut icon PNG"
						bind:source={pwaAssets.shortcut_messages.source}
						bind:url={pwaAssets.shortcut_messages.url}
						defaultUrl={frontendPath('/shortcuts/messages.png')}
						cdnUrl={cdnPath('shortcuts/messages.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_shortcut_projects"
						title="projects"
						description="shortcut icon PNG"
						bind:source={pwaAssets.shortcut_projects.source}
						bind:url={pwaAssets.shortcut_projects.url}
						defaultUrl={frontendPath('/shortcuts/projects.png')}
						cdnUrl={cdnPath('shortcuts/projects.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_shortcut_library"
						title="files"
						description="shortcut icon PNG"
						bind:source={pwaAssets.shortcut_library.source}
						bind:url={pwaAssets.shortcut_library.url}
						defaultUrl={frontendPath('/shortcuts/library.png')}
						cdnUrl={cdnPath('shortcuts/library.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_shortcut_social"
						title="social"
						description="shortcut icon PNG"
						bind:source={pwaAssets.shortcut_social.source}
						bind:url={pwaAssets.shortcut_social.url}
						defaultUrl={frontendPath('/shortcuts/social.png')}
						cdnUrl={cdnPath('shortcuts/social.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_shortcut_settings"
						title="settings"
						description="shortcut icon PNG"
						bind:source={pwaAssets.shortcut_settings.source}
						bind:url={pwaAssets.shortcut_settings.url}
						defaultUrl={frontendPath('/shortcuts/settings.png')}
						cdnUrl={cdnPath('shortcuts/settings.png')}
						allowDisabled
					/>
				</div>
			</div>

			<div class="space-y-3">
				<p class="text-xs font-medium tracking-wide text-zinc-400 uppercase">screenshots</p>
				<div class="grid gap-3 md:grid-cols-2">
					<SettingsAssetSourceRow
						id="pwa_screenshot_narrow_1"
						title="narrow screenshot 1"
						bind:source={pwaAssets.screenshot_narrow_1.source}
						bind:url={pwaAssets.screenshot_narrow_1.url}
						defaultUrl={defaultPath('screenshots/narrow-1-1770x3835.png')}
						cdnUrl={cdnPath('screenshots/narrow-1-1770x3835.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_narrow_2"
						title="narrow screenshot 2"
						bind:source={pwaAssets.screenshot_narrow_2.source}
						bind:url={pwaAssets.screenshot_narrow_2.url}
						defaultUrl={defaultPath('screenshots/narrow-2-1770x3835.png')}
						cdnUrl={cdnPath('screenshots/narrow-2-1770x3835.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_narrow_3"
						title="narrow screenshot 3"
						bind:source={pwaAssets.screenshot_narrow_3.source}
						bind:url={pwaAssets.screenshot_narrow_3.url}
						defaultUrl={defaultPath('screenshots/narrow-3-1770x3835.png')}
						cdnUrl={cdnPath('screenshots/narrow-3-1770x3835.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_narrow_4"
						title="narrow screenshot 4"
						bind:source={pwaAssets.screenshot_narrow_4.source}
						bind:url={pwaAssets.screenshot_narrow_4.url}
						defaultUrl={defaultPath('screenshots/narrow-4-1770x3835.png')}
						cdnUrl={cdnPath('screenshots/narrow-4-1770x3835.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_narrow_5"
						title="narrow screenshot 5"
						bind:source={pwaAssets.screenshot_narrow_5.source}
						bind:url={pwaAssets.screenshot_narrow_5.url}
						defaultUrl={defaultPath('screenshots/narrow-5-1770x3835.png')}
						cdnUrl={cdnPath('screenshots/narrow-5-1770x3835.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_wide_1"
						title="wide screenshot 1"
						bind:source={pwaAssets.screenshot_wide_1.source}
						bind:url={pwaAssets.screenshot_wide_1.url}
						defaultUrl={defaultPath('screenshots/wide-1-3840x2160.png')}
						cdnUrl={cdnPath('screenshots/wide-1-3840x2160.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_wide_2"
						title="wide screenshot 2"
						bind:source={pwaAssets.screenshot_wide_2.source}
						bind:url={pwaAssets.screenshot_wide_2.url}
						defaultUrl={defaultPath('screenshots/wide-2-3840x2160.png')}
						cdnUrl={cdnPath('screenshots/wide-2-3840x2160.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_wide_3"
						title="wide screenshot 3"
						bind:source={pwaAssets.screenshot_wide_3.source}
						bind:url={pwaAssets.screenshot_wide_3.url}
						defaultUrl={defaultPath('screenshots/wide-3-3840x2160.png')}
						cdnUrl={cdnPath('screenshots/wide-3-3840x2160.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_wide_4"
						title="wide screenshot 4"
						bind:source={pwaAssets.screenshot_wide_4.source}
						bind:url={pwaAssets.screenshot_wide_4.url}
						defaultUrl={defaultPath('screenshots/wide-4-3840x2160.png')}
						cdnUrl={cdnPath('screenshots/wide-4-3840x2160.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_wide_5"
						title="wide screenshot 5"
						bind:source={pwaAssets.screenshot_wide_5.source}
						bind:url={pwaAssets.screenshot_wide_5.url}
						defaultUrl={defaultPath('screenshots/wide-5-3840x2160.png')}
						cdnUrl={cdnPath('screenshots/wide-5-3840x2160.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_wide_6"
						title="wide screenshot 6"
						bind:source={pwaAssets.screenshot_wide_6.source}
						bind:url={pwaAssets.screenshot_wide_6.url}
						defaultUrl={defaultPath('screenshots/wide-6-3840x2160.png')}
						cdnUrl={cdnPath('screenshots/wide-6-3840x2160.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_wide_7"
						title="wide screenshot 7"
						bind:source={pwaAssets.screenshot_wide_7.source}
						bind:url={pwaAssets.screenshot_wide_7.url}
						defaultUrl={defaultPath('screenshots/wide-7-3840x2160.png')}
						cdnUrl={cdnPath('screenshots/wide-7-3840x2160.png')}
						allowDisabled
					/>
					<SettingsAssetSourceRow
						id="pwa_screenshot_wide_8"
						title="wide screenshot 8"
						bind:source={pwaAssets.screenshot_wide_8.source}
						bind:url={pwaAssets.screenshot_wide_8.url}
						defaultUrl={defaultPath('screenshots/wide-8-3840x2160.png')}
						cdnUrl={cdnPath('screenshots/wide-8-3840x2160.png')}
						allowDisabled
					/>
				</div>
			</div>

			<p class="text-xs text-zinc-500">
				manifest URL overrides must be served as <code class="text-zinc-300"
					>application/manifest+json</code
				>
				with CORS enabled. when the manifest URL below is set, these generated-manifest asset
				controls do not affect that external file.
			</p>
		</div>

		<div class="space-y-2">
			<div class="flex items-center gap-2">
				<Label for="pwa_manifest_url">pwa manifest url</Label>
				<SettingsPublicBadge />
			</div>
			<Input
				id="pwa_manifest_url"
				bind:value={pwaManifestUrl}
				placeholder="blank uses backend-generated manifest"
				class="rounded-xl"
			/>
			<p class="text-xs text-zinc-500">
				optional full-manifest override. blank uses the backend-generated manifest from the
				configured public origins.
			</p>
		</div>
	</CardContent>
</Card>
