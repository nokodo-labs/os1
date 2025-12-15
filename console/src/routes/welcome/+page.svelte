<script lang="ts">
	import { auth } from '$lib/auth.svelte'
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

	let step = $state<'welcome' | 'register'>('welcome')
	let email = $state('')
	let password = $state('')
	let isLoading = $state(false)
	let error = $state<string | null>(null)

	async function handleSubmit(e: Event) {
		e.preventDefault()
		isLoading = true
		error = null

		try {
			await auth.register(email, password)
			await auth.login(email, password)
			// Force a reload or re-check of initialization status if needed,
			// but navigation to / should trigger the layout logic which might need a refresh.
			// Since we are now authenticated, the layout should let us through to /
			// BUT isInitialized might still be false in the layout's state until we reload.
			// We might need to reload the page to reset the layout state.
			window.location.href = '/dashboard'
		} catch (e: any) {
			error = e.message
			isLoading = false
		}
	}
</script>

<div class="flex min-h-screen flex-col items-center justify-center bg-zinc-950 text-zinc-100">
	{#if step === 'welcome'}
		<div class="max-w-md space-y-6 p-6 text-center">
			<div class="space-y-2">
				<p class="text-sm tracking-[0.3em] text-zinc-400 uppercase">nokodo</p>
				<h1 class="text-4xl font-bold tracking-tight">welcome</h1>
			</div>
			<p class="text-zinc-400">
				it looks like this is a fresh installation. let's set up your admin account to get
				started.
			</p>
			<Button size="lg" onclick={() => (step = 'register')}>create admin account</Button>
		</div>
	{:else}
		<Card class="w-full max-w-sm border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader>
				<CardTitle class="text-2xl">create account</CardTitle>
				<CardDescription>enter your details to create an account</CardDescription>
			</CardHeader>
			<form onsubmit={handleSubmit}>
				<CardContent class="space-y-4">
					{#if error}
						<div class="rounded-md bg-red-500/10 p-3 text-sm text-red-500">
							{error}
						</div>
					{/if}
					<div class="space-y-2">
						<Label for="email">email</Label>
						<Input
							id="email"
							type="email"
							placeholder="m@example.com"
							required
							bind:value={email}
						/>
					</div>
					<div class="space-y-2">
						<Label for="password">password</Label>
						<Input id="password" type="password" required bind:value={password} />
					</div>
				</CardContent>
				<div class="flex gap-2 p-6 pt-0">
					<Button
						type="button"
						variant="ghost"
						class="w-full"
						onclick={() => (step = 'welcome')}
					>
						back
					</Button>
					<Button type="submit" class="w-full" disabled={isLoading}>
						{isLoading ? 'creating...' : 'create account'}
					</Button>
				</div>
			</form>
		</Card>
	{/if}
</div>
