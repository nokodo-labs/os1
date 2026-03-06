<script lang="ts">
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Label } from '$lib/components/ui/label'
	import { Switch } from '$lib/components/ui/switch'

	type Props = {
		threads?: boolean
		notes?: boolean
		files?: boolean
	}

	let {
		threads = $bindable(true),
		notes = $bindable(true),
		files = $bindable(true),
	}: Props = $props()
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>soft delete</CardTitle>
		<CardDescription>
			when enabled, deleting a resource marks it as deleted rather than permanently removing
			it from the database.
		</CardDescription>
	</CardHeader>
	<CardContent class="space-y-3">
		<div class="flex items-center justify-between">
			<div class="space-y-0.5">
				<Label for="soft_delete_threads">threads</Label>
				<p class="text-xs text-zinc-500">
					soft-delete threads instead of permanently removing them.
				</p>
			</div>
			<Switch
				id="soft_delete_threads"
				checked={threads}
				onCheckedChange={(v: boolean) => (threads = v)}
			/>
		</div>
		<div class="flex items-center justify-between">
			<div class="space-y-0.5">
				<Label for="soft_delete_notes">notes</Label>
				<p class="text-xs text-zinc-500">
					soft-delete notes instead of permanently removing them.
				</p>
			</div>
			<Switch
				id="soft_delete_notes"
				checked={notes}
				onCheckedChange={(v: boolean) => (notes = v)}
			/>
		</div>
		<div class="flex items-center justify-between">
			<div class="space-y-0.5">
				<Label for="soft_delete_files">files</Label>
				<p class="text-xs text-zinc-500">
					soft-delete files instead of permanently removing them.
				</p>
			</div>
			<Switch
				id="soft_delete_files"
				checked={files}
				onCheckedChange={(v: boolean) => (files = v)}
			/>
		</div>
	</CardContent>
</Card>
