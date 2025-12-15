<script lang="ts">
	let { expanded = true, shimmer = true } = $props()
</script>

<div class="brand-text" class:expanded class:splash-shimmer={shimmer}>
	<span class="brand-hidden">n</span><span class="brand-visible">ok</span><span
		class="brand-hidden">odo</span
	>
</div>

<style>
	@font-face {
		font-family: 'nokodoFont';
		src: url('https://nokodo.net/static/fonts/researcher-regular.woff2') format('woff2');
		font-weight: 600;
		font-style: normal;
		font-display: swap;
	}

	.brand-text {
		font-family:
			'nokodoFont',
			-apple-system,
			BlinkMacSystemFont,
			'Segoe UI',
			Roboto,
			'Helvetica Neue',
			Arial,
			sans-serif;
		font-size: clamp(3rem, 8vw, 5rem);
		font-weight: 600;
		line-height: 1.2;
		color: var(--text-primary);
		white-space: nowrap;
		position: relative;
		isolation: isolate;

		transform: translateX(calc(0.5em));
		transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.brand-text.expanded {
		transform: translateX(0);
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

	.brand-text.expanded .brand-hidden {
		opacity: 1;
	}

	/* Theme-specific color variables */
	:global(html.light) {
		--text-primary: #1a1a1a;
	}

	:global(html.dark) {
		--text-primary: #ffffff;
	}

	/* Force exact dark-mode base color for splash banner text */
	:global(html.dark) .brand-text {
		color: #f8f3f8ff;
	}

	/* Accessibility: Respect reduced motion preference */
	@media (prefers-reduced-motion: reduce) {
		.brand-text {
			transition: all 0.2s ease;
		}

		.brand-hidden {
			transition: all 0.2s ease;
		}
	}

	@keyframes splash-shimmer {
		0% {
			/* start with the highlight off to the left side */
			background-position: 150%;
		}
		100% {
			/* move image left so the highlight sweeps left->right */
			background-position: -50%;
		}
	}

	.splash-shimmer::after {
		content: '';
		position: absolute;
		inset: 0;
		pointer-events: none;
		z-index: 1;
		background-image: linear-gradient(
			90deg,
			transparent 0%,
			rgba(0, 0, 0, 0) 20%,
			rgba(0, 0, 0, 0.46) 40%,
			rgba(0, 0, 0, 0.66) 50%,
			rgba(0, 0, 0, 0.46) 60%,
			rgba(0, 0, 0, 0) 80%,
			transparent 100%
		);
		background-repeat: no-repeat;
		background-position: 0%;
		background-size: 300%;
		animation: splash-shimmer 2s linear infinite;
		mix-blend-mode: multiply;
		will-change: background-position;
	}
</style>
