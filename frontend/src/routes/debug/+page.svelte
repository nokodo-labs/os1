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
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-4 py-3 text-sm transition"
		>
			shimmer playground
		</a>
		<a
			href={resolve('/debug/liquid-glass')}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-4 py-3 text-sm transition"
		>
			liquid glass lab
		</a>
		<a
			href={resolve('/debug/liquid-metal')}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-4 py-3 text-sm transition"
		>
			liquid metal svg lab
		</a>
		<a
			href={resolve('/debug/pwa')}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-4 py-3 text-sm transition"
		>
			pwa debug
		</a>
		<a
			href={resolve('/debug/runs')}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-4 py-3 text-sm transition"
		>
			runs & caches
		</a>
		<a
			href={resolve('/debug/backgrounds')}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-4 py-3 text-sm transition"
		>
			backgrounds debug
		</a>
		<a
			href={resolve('/debug/toasts')}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-4 py-3 text-sm transition"
		>
			toast playground
		</a>
		<a
			href={resolve('/debug/open-webui-import')}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-4 py-3 text-sm transition"
		>
			Open WebUI import debug
		</a>
	</div>
</div>
