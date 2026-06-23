<script lang="ts">
	import SettingsPublicBadge from '$lib/components/settings/SettingsPublicBadge.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Switch } from '$lib/components/ui/switch'
	import { Textarea } from '$lib/components/ui/textarea'
	import { KeyRound } from '@lucide/svelte'

	type Props = {
		webPushEnabled?: boolean
		webPushTtlSeconds?: string
		notificationTtlSeconds?: string
		missedGraceDays?: string
		lookaheadDays?: string
		vapidPublicKey?: string
		vapidPrivateKey?: string
		isGeneratingVapidKeys?: boolean
		vapidGenerationError?: string | null
		onGenerateVapidKeys?: () => void | Promise<void>
	}

	let {
		webPushEnabled = $bindable(false),
		webPushTtlSeconds = $bindable(''),
		notificationTtlSeconds = $bindable(''),
		missedGraceDays = $bindable(''),
		lookaheadDays = $bindable(''),
		vapidPublicKey = $bindable(''),
		vapidPrivateKey = $bindable(''),
		isGeneratingVapidKeys = false,
		vapidGenerationError = null,
		onGenerateVapidKeys,
	}: Props = $props()

	const vapidHasAnyKey = $derived(
		vapidPublicKey.trim().length > 0 || vapidPrivateKey.trim().length > 0
	)
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>notifications</CardTitle>
		<CardDescription>delivery behavior for in-app and background notifications.</CardDescription
		>
	</CardHeader>
	<CardContent class="space-y-5">
		<div class="flex items-center justify-between gap-4">
			<div class="space-y-0.5">
				<div class="flex items-center gap-2">
					<Label for="web_push_enabled">web push</Label>
					<SettingsPublicBadge />
				</div>
				<p class="text-xs text-zinc-500">
					enable server-side Web Push delivery when VAPID keys are configured.
				</p>
			</div>
			<Switch
				id="web_push_enabled"
				checked={webPushEnabled}
				onCheckedChange={(value: boolean) => (webPushEnabled = value)}
			/>
		</div>

		<div class="grid gap-4 md:grid-cols-4">
			<div class="space-y-2">
				<Label for="web_push_ttl">web push TTL seconds</Label>
				<p class="text-xs text-zinc-500">provider retention window for push messages.</p>
				<Input
					id="web_push_ttl"
					type="number"
					placeholder="86400"
					bind:value={webPushTtlSeconds}
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="notification_ttl">native TTL seconds</Label>
				<p class="text-xs text-zinc-500">empty keeps inbox notifications indefinitely.</p>
				<Input
					id="notification_ttl"
					type="number"
					placeholder="empty"
					bind:value={notificationTtlSeconds}
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="missed_grace_days">missed grace days</Label>
				<p class="text-xs text-zinc-500">
					lookback window for scheduled notification recovery.
				</p>
				<Input
					id="missed_grace_days"
					type="number"
					placeholder="7"
					bind:value={missedGraceDays}
					class="rounded-xl"
				/>
			</div>
			<div class="space-y-2">
				<Label for="lookahead_days">lookahead days</Label>
				<p class="text-xs text-zinc-500">
					future scheduling window for notification tasks.
				</p>
				<Input
					id="lookahead_days"
					type="number"
					placeholder="366"
					bind:value={lookaheadDays}
					class="rounded-xl"
				/>
			</div>
		</div>

		<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
			<div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
				<div>
					<div class="mb-1 flex items-center gap-2">
						<p class="text-sm font-medium">VAPID key pair</p>
					</div>
					<p class="text-xs text-zinc-500">
						key material used for browser push subscriptions.
					</p>
				</div>
				<Button
					variant="secondary"
					class="rounded-xl"
					onclick={() => onGenerateVapidKeys?.()}
					disabled={isGeneratingVapidKeys || vapidHasAnyKey}
				>
					<KeyRound class="mr-1.5 h-4 w-4" />
					{isGeneratingVapidKeys
						? 'generating...'
						: vapidHasAnyKey
							? 'keys present'
							: 'generate keys'}
				</Button>
			</div>

			<div class="grid gap-4 md:grid-cols-2">
				<div class="space-y-2">
					<Label for="vapid_public_key">public key</Label>
					<Input
						id="vapid_public_key"
						bind:value={vapidPublicKey}
						class="rounded-xl font-mono text-xs"
					/>
				</div>
				<div class="space-y-2">
					<Label for="vapid_private_key">private key</Label>
					<Textarea
						id="vapid_private_key"
						bind:value={vapidPrivateKey}
						class="min-h-24 rounded-xl font-mono text-xs"
					/>
				</div>
			</div>

			{#if vapidGenerationError}
				<p class="mt-3 text-xs text-red-300">{vapidGenerationError}</p>
			{/if}
		</div>
	</CardContent>
</Card>
