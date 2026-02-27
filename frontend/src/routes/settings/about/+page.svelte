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
			href: 'https://github.com/nokodo-labs/nokodo-ai',
			icon: 'github',
		},
		{
			label: 'changelog',
			href: 'https://github.com/nokodo-labs/nokodo-ai/releases',
			icon: 'github',
		},
	]

	const shields: { label: string; src: string; href: string }[] = [
		{
			label: 'GitHub stars',
			src: 'https://img.shields.io/github/stars/nokodo-labs/nokodo-ai?style=flat-square&color=8b5cf6',
			href: 'https://github.com/nokodo-labs/nokodo-ai/stargazers',
		},
		{
			label: 'License',
			src: 'https://img.shields.io/github/license/nokodo-labs/nokodo-ai?style=flat-square&color=8b5cf6',
			href: 'https://github.com/nokodo-labs/nokodo-ai/blob/dev/LICENSE',
		},
	]
</script>

<SettingsSectionLayout icon={InfoCircle} label="about" description="nokodo AI information">
	<div class="space-y-4">
		<!-- brand -->
		<div class="rounded-container flex flex-col items-center bg-white/5 p-8 text-center">
			<img
				src="https://nokodo.net/media/images/logo_full.svg"
				alt="nokodo logo"
				class="h-10 w-auto object-contain"
			/>

			<div
				class="rounded-pill mt-3 border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/50"
			>
				v{appVersion}
			</div>
		</div>

		<!-- links -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-white">links</div>
			<div class="mt-3 space-y-1">
				{#each links as link (link.href)}
					<a
						href={link.href}
						target="_blank"
						rel="external noopener noreferrer"
						class="rounded-pill flex items-center gap-3 px-3 py-2.5 text-sm text-white/70 no-underline transition-all hover:bg-white/8 hover:text-white/90"
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
			<div class="text-sm font-semibold text-white">community</div>
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
			<div class="text-sm font-semibold text-white">legal</div>
			<div class="mt-2 space-y-2 text-xs text-white/50">
				<p>&copy; {new Date().getFullYear()} nokodo. all rights reserved.</p>
				<p>
					this software includes open-source components licensed under their respective
					terms. see the project repository for full dependency licenses (copyleft where
					applicable).
				</p>
			</div>
		</div>
		<div class="flex w-full justify-center text-white/50">
			created by &nbsp;<a href="https://nokodo.net" class="text-white/70">nokodo</a>
			&nbsp; with&nbsp;
			<span class="inline-block animate-pulse text-red-400">
				<Heart variant="solid" class="inline h-4 w-4" />
			</span>
		</div>
	</div>
</SettingsSectionLayout>
