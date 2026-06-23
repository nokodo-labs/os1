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
		maxReminderHierarchyDepth?: string
		maxScheduledItemsWindowDays?: string
		rateLimitRequestsPerMinute?: string
		accessibleUsersTtlSeconds?: string
		scheduledItemsTtlSeconds?: string
		resourcePayloadTtlSeconds?: string
		promptTemplateTtlSeconds?: string
		mcpSnapshotTtlSeconds?: string
	}

	let {
		maxThreadsPerUser = $bindable(''),
		maxMessagesPerThread = $bindable(''),
		maxChatInputChars = $bindable(''),
		maxFileSizeMb = $bindable(''),
		maxReminderHierarchyDepth = $bindable(''),
		maxScheduledItemsWindowDays = $bindable(''),
		rateLimitRequestsPerMinute = $bindable(''),
		accessibleUsersTtlSeconds = $bindable(''),
		scheduledItemsTtlSeconds = $bindable(''),
		resourcePayloadTtlSeconds = $bindable(''),
		promptTemplateTtlSeconds = $bindable(''),
		mcpSnapshotTtlSeconds = $bindable(''),
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
			<Label for="max_reminder_hierarchy_depth">max reminder nesting depth</Label>
			<p class="text-xs text-zinc-500">maximum sub-reminder levels per reminder.</p>
			<Input
				id="max_reminder_hierarchy_depth"
				type="number"
				placeholder="5"
				bind:value={maxReminderHierarchyDepth}
				class="rounded-xl"
			/>
		</div>
		<div class="space-y-2">
			<Label for="max_scheduled_items_window_days">scheduled items window (days)</Label>
			<p class="text-xs text-zinc-500">
				maximum time window for scheduled items queries (calendar, tasks).
			</p>
			<Input
				id="max_scheduled_items_window_days"
				type="number"
				placeholder="90"
				bind:value={maxScheduledItemsWindowDays}
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
		<div class="space-y-2">
			<Label for="scheduled_items_ttl">scheduled items cache TTL (seconds)</Label>
			<p class="text-xs text-zinc-500">TTL for cached scheduled items (calendar/tasks).</p>
			<Input
				id="scheduled_items_ttl"
				type="number"
				placeholder="300"
				bind:value={scheduledItemsTtlSeconds}
				class="rounded-xl"
			/>
		</div>
		<div class="space-y-2">
			<Label for="resource_payload_ttl">resource payload cache TTL (seconds)</Label>
			<p class="text-xs text-zinc-500">TTL for cached resource payload entries.</p>
			<Input
				id="resource_payload_ttl"
				type="number"
				placeholder="300"
				bind:value={resourcePayloadTtlSeconds}
				class="rounded-xl"
			/>
		</div>
		<div class="space-y-2">
			<Label for="prompt_template_ttl">prompt template cache TTL (seconds)</Label>
			<p class="text-xs text-zinc-500">TTL for cached prompt template entries.</p>
			<Input
				id="prompt_template_ttl"
				type="number"
				placeholder="28800"
				bind:value={promptTemplateTtlSeconds}
				class="rounded-xl"
			/>
		</div>
		<div class="space-y-2">
			<Label for="mcp_snapshot_ttl">MCP snapshot cache TTL (seconds)</Label>
			<p class="text-xs text-zinc-500">TTL for cached MCP DB snapshot entries.</p>
			<Input
				id="mcp_snapshot_ttl"
				type="number"
				placeholder="86400"
				bind:value={mcpSnapshotTtlSeconds}
				class="rounded-xl"
			/>
		</div>
	</CardContent>
</Card>
