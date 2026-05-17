<script lang="ts">
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'

	type Props = {
		maxThreadsPerUser?: string
		maxMessagesPerThread?: string
		maxChatInputChars?: string
		maxFileSizeMb?: string
		rateLimitRequestsPerMinute?: string
		accessibleUsersTtlSeconds?: string
	}

	let {
		maxThreadsPerUser = $bindable(''),
		maxMessagesPerThread = $bindable(''),
		maxChatInputChars = $bindable(''),
		maxFileSizeMb = $bindable(''),
		rateLimitRequestsPerMinute = $bindable(''),
		accessibleUsersTtlSeconds = $bindable(''),
	}: Props = $props()
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>limits</CardTitle>
		<CardDescription>protect the system with sane caps.</CardDescription>
	</CardHeader>
	<CardContent class="grid gap-4 md:grid-cols-2">
		<div class="space-y-2">
			<Label for="max_threads">max threads per user</Label>
			<p class="text-xs text-zinc-500">
				hard cap on threads per account; prevents runaway data growth.
			</p>
			<Input
				id="max_threads"
				type="number"
				placeholder="100"
				bind:value={maxThreadsPerUser}
				class="rounded-xl"
			/>
		</div>
		<div class="space-y-2">
			<Label for="max_messages">max messages per thread</Label>
			<p class="text-xs text-zinc-500">hard cap on messages per thread.</p>
			<Input
				id="max_messages"
				type="number"
				placeholder="1000"
				bind:value={maxMessagesPerThread}
				class="rounded-xl"
			/>
		</div>
		<div class="space-y-2">
			<Label for="max_chat_input_chars">max chat input characters</Label>
			<p class="text-xs text-zinc-500">hard cap on a single chat input.</p>
			<Input
				id="max_chat_input_chars"
				type="number"
				placeholder="200000"
				bind:value={maxChatInputChars}
				class="rounded-xl"
			/>
		</div>
		<div class="space-y-2">
			<Label for="max_file_size">max file size (MB)</Label>
			<p class="text-xs text-zinc-500">maximum allowed size for a single file upload.</p>
			<Input
				id="max_file_size"
				type="number"
				placeholder="50"
				bind:value={maxFileSizeMb}
				class="rounded-xl"
			/>
		</div>
		<div class="space-y-2">
			<Label for="rate_limit">rate limit (requests/min)</Label>
			<p class="text-xs text-zinc-500">
				API requests allowed per minute per authenticated user.
			</p>
			<Input
				id="rate_limit"
				type="number"
				placeholder="1500"
				bind:value={rateLimitRequestsPerMinute}
				class="rounded-xl"
			/>
		</div>
		<div class="space-y-2">
			<Label for="accessible_users_ttl">share recipient cache TTL (seconds)</Label>
			<p class="text-xs text-zinc-500">
				redis TTL for cached recipient lists used by realtime sharing events.
			</p>
			<Input
				id="accessible_users_ttl"
				type="number"
				placeholder="86400"
				bind:value={accessibleUsersTtlSeconds}
				class="rounded-xl"
			/>
		</div>
	</CardContent>
</Card>
