<script lang="ts">
	let {
		shimmer = true,
		expanded = true,
		className = '',
	} = $props<{
		shimmer?: boolean
		expanded?: boolean
		className?: string
	}>()
</script>

<div class={`brand ${className}`} class:expanded>
	<div class="brand-solid">
		<span class="brand-hidden">n</span><span class="brand-visible">ok</span><span
			class="brand-hidden">odo</span
		>
	</div>
	{#if shimmer}
		<div class="brand-shimmer" aria-hidden="true">
			<span class="brand-hidden">n</span><span class="brand-visible">ok</span><span
				class="brand-hidden">odo</span
			>
		</div>
	{/if}
</div>

<style>
	@font-face {
		font-family: 'nokodoFont';
		src: url('https://nokodo.net/static/fonts/researcher-regular.woff2') format('woff2');
		font-weight: 600;
		font-style: normal;
		font-display: swap;
	}

	.brand {
		font-family:
			'nokodoFont',
			-apple-system,
			BlinkMacSystemFont,
			'Segoe UI',
			Roboto,
			'Helvetica Neue',
			Arial,
			sans-serif;
		font-size: clamp(2.25rem, 6vw, 3.25rem);
		font-weight: 600;
		line-height: 1.1;
		color: rgb(255 255 255 / 0.92);
		white-space: nowrap;
		position: relative;
		isolation: isolate;
		user-select: none;

		transform: translateX(calc(0.5em));
		transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.brand.expanded {
		transform: translateX(0);
	}

	.brand-solid,
	.brand-shimmer {
		display: inline-block;
	}

	.brand-shimmer {
		position: absolute;
		inset: 0;
		pointer-events: none;
		z-index: 1;

		/* Clip the animated gradient *into* the glyphs (no shimmer outside the logo). */
		color: transparent;
		background-image: linear-gradient(
			90deg,
			transparent 0%,
			rgb(255 255 255 / 0) 20%,
			rgb(255 255 255 / 0.35) 40%,
			rgb(255 255 255 / 0.75) 50%,
			rgb(255 255 255 / 0.35) 60%,
			rgb(255 255 255 / 0) 80%,
			transparent 100%
		);
		background-repeat: no-repeat;
		background-size: 300% 100%;
		background-position: 150% 0;
		animation: splash-shimmer 2s linear infinite;

		-webkit-background-clip: text;
		background-clip: text;
	}

	.brand-visible {
		display: inline-block;
		opacity: 1;
	}

	.brand-hidden {
		display: inline-block;
		opacity: 0;
		transition: opacity 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.brand.expanded .brand-hidden {
		opacity: 1;
	}

	@keyframes splash-shimmer {
		0% {
			background-position: 150% 0;
		}
		100% {
			background-position: -50% 0;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.brand {
			transition: transform 0.2s ease;
		}
		.brand-hidden {
			transition: opacity 0.2s ease;
		}
		.brand-shimmer {
			animation: none;
		}
	}
</style>
