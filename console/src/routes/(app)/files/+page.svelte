<script lang="ts">
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
</script>

<div class="space-y-6">
	<div>
		<h2 class="text-2xl font-bold tracking-tight">files</h2>
		<p class="text-zinc-400">file management for the platform.</p>
	</div>

	<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
		<CardHeader>
			<CardTitle>coming soon</CardTitle>
			<CardDescription>
				the files API is not yet available. this page will be populated once file management
				endpoints are implemented.
			</CardDescription>
		</CardHeader>
		<CardContent>
			<div
				class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
			>
				no file endpoints available yet
			</div>
		</CardContent>
	</Card>
</div>
