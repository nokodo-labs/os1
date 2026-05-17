<script lang="ts">
	import Github from '$lib/components/icons/Github.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Heart from '$lib/components/icons/Heart.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import NokodoBrandLogo from '$lib/components/NokodoBrandLogo.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { settingsState } from '$lib/stores/settings.svelte'
	import { onMount } from 'svelte'

	const appVersion = $derived(settingsState.data?.branding?.app_version ?? '0.0.0')
	let stableVersion = $state<string | null>(null)
	let stableReleaseUrl = $state('https://github.com/nokodo-labs/os1/releases/latest')

	type GithubRelease = {
		tag_name?: unknown
		html_url?: unknown
	}

	function releaseFromJson(value: unknown): { version: string; url: string } | null {
		if (value === null || typeof value !== 'object') return null
		const release = value as GithubRelease
		const tagName = typeof release.tag_name === 'string' ? release.tag_name : null
		const htmlUrl = typeof release.html_url === 'string' ? release.html_url : null
		if (!tagName || !htmlUrl) return null
		return { version: tagName.replace(/^v/i, ''), url: htmlUrl }
	}

	onMount(() => {
		let cancelled = false
		void (async () => {
			try {
				const response = await fetch(
					'https://api.github.com/repos/nokodo-labs/os1/releases/latest',
					{
						headers: { Accept: 'application/vnd.github+json' },
					}
				)
				if (!response.ok) return
				const release = releaseFromJson(await response.json())
				if (!release || cancelled) return
				stableVersion = release.version
				stableReleaseUrl = release.url
			} catch {
				// keep the local backend version fallback when GitHub is unreachable.
			}
		})()
		return () => {
			cancelled = true
		}
	})

	interface ExternalLink {
		label: string
		href: string
		icon?: 'globe' | 'github'
	}

	const links: ExternalLink[] = [
		{ label: 'nokodo.net', href: 'https://nokodo.net', icon: 'globe' },
		{ label: 'nokodo.ai', href: 'https://nokodo.ai', icon: 'globe' },
		{
			label: 'GitHub',
			href: 'https://github.com/nokodo-labs/os1',
			icon: 'github',
		},
		{
			label: 'changelog',
			href: 'https://github.com/nokodo-labs/os1/releases',
			icon: 'github',
		},
	]

	const shields: { label: string; src: string; href: string }[] = [
		{
			label: 'GitHub stars',
			src: 'https://img.shields.io/github/stars/nokodo-labs/os1?style=flat-square&color=8b5cf6',
			href: 'https://github.com/nokodo-labs/os1/stargazers',
		},
		{
			label: 'License',
			src: 'https://img.shields.io/github/license/nokodo-labs/os1?style=flat-square&color=8b5cf6',
			href: 'https://github.com/nokodo-labs/os1/blob/dev/LICENSE',
		},
	]
</script>

<SettingsSectionLayout icon={InfoCircle} label="about" description="OS1 information">
	<div class="space-y-4">
		<!-- brand -->
		<div class="rounded-container bg-foreground/5 flex flex-col items-center p-8 text-center">
			<NokodoBrandLogo class="h-24" />

			<a
				href={stableReleaseUrl}
				target="_blank"
				rel="external noopener noreferrer"
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/50 hover:bg-foreground/8 hover:text-foreground/70 mt-3 border px-3 py-1 text-xs no-underline transition-colors"
			>
				v{stableVersion ?? appVersion}
			</a>
		</div>

		<!-- links -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-foreground text-sm font-semibold">links</div>
			<div class="mt-3 space-y-1">
				{#each links as link (link.href)}
					<a
						href={link.href}
						target="_blank"
						rel="external noopener noreferrer"
						class="rounded-pill text-foreground/70 hover:bg-foreground/8 hover:text-foreground/90 flex items-center gap-3 px-3 py-2.5 text-sm no-underline transition-all"
					>
						{#if link.icon === 'github'}
							<Github class="h-4.5 w-4.5 shrink-0" />
						{:else}
							<GlobeAlt class="h-4.5 w-4.5 shrink-0" />
						{/if}
						<span>{link.label}</span>
					</a>
				{/each}
			</div>
		</div>

		<!-- shields -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-foreground text-sm font-semibold">community</div>
			<div class="mt-3 flex flex-wrap gap-2">
				{#each shields as badge (badge.label)}
					<a href={badge.href} target="_blank" rel="external noopener noreferrer">
						<img src={badge.src} alt={badge.label} class="h-5" />
					</a>
				{/each}
			</div>
		</div>

		<!-- legal -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-foreground text-sm font-semibold">legal</div>
			<div class="text-foreground/50 mt-2 space-y-2 text-xs">
				<p>&copy; {new Date().getFullYear()} nokodo. all rights reserved.</p>
				<p>
					this software includes open-source components licensed under their respective
					terms. see the project repository for full dependency licenses (copyleft where
					applicable).
				</p>
			</div>
		</div>
		<div
			class="text-foreground/50 flex w-full flex-col items-center justify-center gap-2 text-xs"
		>
			<div>created by</div>
			<a href="https://nokodo.net" target="_blank" rel="external noopener noreferrer">
				<img
					src="https://nokodo.net/media/images/logo_full.svg"
					alt="nokodo"
					class="h-8 w-auto opacity-80"
				/>
			</a>
			<div class="flex items-center gap-1.5">
				<span>with</span>
				<span class="about-heart text-red-400" aria-label="love">
					<Heart variant="solid" class="h-4 w-4" />
				</span>
			</div>
		</div>
	</div>
</SettingsSectionLayout>

<style>
	.about-heart {
		animation: about-heart-pulse 1.2s ease-in-out infinite;
		transform-origin: center;
	}

	@keyframes about-heart-pulse {
		0%,
		100% {
			transform: scale(1);
		}
		30% {
			transform: scale(1.22);
		}
		48% {
			transform: scale(0.92);
		}
		68% {
			transform: scale(1.12);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.about-heart {
			animation: none;
		}
	}
</style>
