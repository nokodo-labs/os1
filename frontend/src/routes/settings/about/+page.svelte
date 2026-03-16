<script lang="ts">
	import Github from '$lib/components/icons/Github.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Heart from '$lib/components/icons/Heart.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { settingsState } from '$lib/stores/settings.svelte'

	const appVersion = $derived(settingsState.data?.branding?.app_version ?? '0.0.0')

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
			<img
				src="https://nokodo.net/media/images/logo_full.svg"
				alt="nokodo logo"
				class="h-10 w-auto object-contain"
			/>

			<div
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/50 mt-3 border px-3 py-1 text-xs"
			>
				v{appVersion}
			</div>
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
		<div class="text-foreground/50 flex w-full justify-center">
			created by &nbsp;<a href="https://nokodo.net" class="text-foreground/70">nokodo</a>
			&nbsp; with&nbsp;
			<span class="inline-block animate-pulse text-red-400">
				<Heart variant="solid" class="inline h-4 w-4" />
			</span>
		</div>
	</div>
</SettingsSectionLayout>
