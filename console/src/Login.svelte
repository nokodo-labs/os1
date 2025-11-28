<script lang="ts">
	import { Button } from "$lib/components/ui/button";
	import {
		Card,
		CardContent,
		CardDescription,
		CardFooter,
		CardHeader,
		CardTitle,
	} from "$lib/components/ui/card";
	import { Input } from "$lib/components/ui/input";
	import { Label } from "$lib/components/ui/label";

	let { onLogin }: { onLogin: () => void } = $props();

	let email = $state("");
	let password = $state("");
	let isLoading = $state(false);

	function handleLogin(e: Event) {
		e.preventDefault();
		isLoading = true;
		// Simulate login
		setTimeout(() => {
			isLoading = false;
			console.log("Login attempt", { email, password });
			onLogin();
		}, 1000);
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-slate-950 p-4">
	<Card class="w-full max-w-sm border-slate-800 bg-slate-900 text-slate-100">
		<CardHeader>
			<CardTitle class="text-2xl">Admin Console</CardTitle>
			<CardDescription class="text-slate-400">
				Enter your credentials to access the dashboard.
			</CardDescription>
		</CardHeader>
		<CardContent class="grid gap-4">
			<form onsubmit={handleLogin} class="grid gap-4">
				<div class="grid gap-2">
					<Label for="email" class="text-slate-200">Email</Label>
					<Input
						id="email"
						type="email"
						placeholder="admin@nokodo.ai"
						required
						bind:value={email}
						class="border-slate-800 bg-slate-950 text-slate-100 placeholder:text-slate-500 focus-visible:ring-slate-700"
					/>
				</div>
				<div class="grid gap-2">
					<Label for="password" class="text-slate-200">Password</Label
					>
					<Input
						id="password"
						type="password"
						required
						bind:value={password}
						class="border-slate-800 bg-slate-950 text-slate-100 placeholder:text-slate-500 focus-visible:ring-slate-700"
					/>
				</div>
				<Button type="submit" class="w-full" disabled={isLoading}>
					{#if isLoading}
						Signing in...
					{:else}
						Sign in
					{/if}
				</Button>
			</form>
		</CardContent>
		<CardFooter>
			<p class="text-xs text-slate-500 text-center w-full">
				Restricted access. Authorized personnel only.
			</p>
		</CardFooter>
	</Card>
</div>
