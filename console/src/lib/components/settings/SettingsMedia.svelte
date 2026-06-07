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

	type MediaAssetSource = 'default' | 'cdn' | 'custom'

	type Props = {
		publicCdnOrigin?: string
		faviconSource?: MediaAssetSource
		faviconUrl?: string
		appleTouchIconSource?: MediaAssetSource
		appleTouchIconUrl?: string
		sidebarLogoSource?: MediaAssetSource
		sidebarLogoUrl?: string
		splashLogoSource?: MediaAssetSource
		splashLogoUrl?: string
	}

	let {
		publicCdnOrigin = '',
		faviconSource = $bindable<MediaAssetSource>('default'),
		faviconUrl = $bindable(''),
		appleTouchIconSource = $bindable<MediaAssetSource>('default'),
		appleTouchIconUrl = $bindable(''),
		sidebarLogoSource = $bindable<MediaAssetSource>('default'),
		sidebarLogoUrl = $bindable(''),
		splashLogoSource = $bindable<MediaAssetSource>('default'),
		splashLogoUrl = $bindable(''),
	}: Props = $props()

	function stripTrailingSlash(url: string): string {
		return url.replace(/\/+$/, '')
	}

	function cdnUrl(path: string): string {
		const trimmed = publicCdnOrigin.trim()
		return trimmed ? `${stripTrailingSlash(trimmed)}/${path}` : ''
	}
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>media</CardTitle>
		<CardDescription>
			frontend media tags only: browser favicon and iOS home-screen icon. PWA manifest icons
			and screenshots are controlled by branding.
		</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		<div class="rounded-lg border border-zinc-800 bg-zinc-950/35 p-3 text-xs text-zinc-500">
			<span class="font-medium text-zinc-300">CDN-default</span> uses the public CDN origin
			from branding. Leave assets on <span class="font-medium text-zinc-300">default</span> to
			use nokodo-hosted defaults, or choose
			<span class="font-medium text-zinc-300">custom URL</span>
			for a full per-file override. <SettingsPublicBadge />
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<SettingsAssetSourceRow
				id="media_favicon"
				title="favicon"
				description="browser tab icon"
				bind:source={faviconSource}
				bind:url={faviconUrl}
				defaultUrl="https://nokodo.net/static/os1/favicon.svg"
				cdnUrl={cdnUrl('static/os1/favicon.svg')}
				customPlaceholder="https://cdn.example.com/static/os1/favicon.svg"
			/>

			<SettingsAssetSourceRow
				id="media_apple_touch_icon"
				title="Apple touch icon"
				description="iOS home-screen icon"
				bind:source={appleTouchIconSource}
				bind:url={appleTouchIconUrl}
				defaultUrl="https://nokodo.net/static/os1/icon-512-any.png"
				cdnUrl={cdnUrl('static/os1/icon-512-any.png')}
				customPlaceholder="https://cdn.example.com/static/os1/icon-512-any.png"
			/>

			<SettingsAssetSourceRow
				id="media_sidebar_logo"
				title="sidebar logo"
				description="logo shown in the app sidebar"
				bind:source={sidebarLogoSource}
				bind:url={sidebarLogoUrl}
				defaultUrl="https://nokodo.net/static/os1/logo.svg"
				cdnUrl={cdnUrl('static/os1/logo.svg')}
				customPlaceholder="https://cdn.example.com/static/os1/logo.svg"
			/>

			<SettingsAssetSourceRow
				id="media_splash_logo"
				title="splash logo"
				description="logo shown on the loading/splash screen"
				bind:source={splashLogoSource}
				bind:url={splashLogoUrl}
				defaultUrl="https://nokodo.net/static/os1/logo.svg"
				cdnUrl={cdnUrl('static/os1/logo.svg')}
				customPlaceholder="https://cdn.example.com/static/os1/logo.svg"
			/>
		</div>
	</CardContent>
</Card>
