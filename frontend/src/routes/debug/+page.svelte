<script>
	import { resolve } from '$app/paths'
</script>

<div class="mx-auto w-full max-w-4xl px-6 pt-10 pb-24">
	<h1 class="text-xl font-semibold">debug</h1>
	<p class="text-muted-foreground mt-2 text-sm">
		quick access to visual test pages and playgrounds.
	</p>

	<div class="mt-6 grid gap-3 sm:grid-cols-2">
		<a
			href={resolve('/debug/shimmer')}
			class="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/80 transition hover:border-white/20 hover:bg-white/8"
		>
			shimmer playground
		</a>
		<a
			href={resolve('/debug/liquid-glass')}
			class="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/80 transition hover:border-white/20 hover:bg-white/8"
		>
			liquid glass lab
		</a>
		<a
			href={resolve('/debug/pwa')}
			class="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/80 transition hover:border-white/20 hover:bg-white/8"
		>
			pwa debug
		</a>
	</div>
</div>
