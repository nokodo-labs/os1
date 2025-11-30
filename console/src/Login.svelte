<script lang="ts">
	import { auth } from "$lib/auth.svelte";
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
	let username = $state("");
	let password = $state("");
	let isLoading = $state(false);
	let isRegister = $state(false);
	let error = $state<string | null>(null);

	async function handleSubmit(e: Event) {
		e.preventDefault();
		isLoading = true;
		error = null;

		try {
			if (isRegister) {
				await auth.register(email, username, password);
				await auth.login(email, password);
			} else {
				await auth.login(email, password);
			}
			onLogin();
		} catch (e: any) {
			error = e.message;
		} finally {
			isLoading = false;
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-slate-950 p-4">
	<Card class="w-full max-w-sm border-slate-800 bg-slate-900 text-slate-100">
		<CardHeader>
			<CardTitle class="text-2xl">
				{isRegister ? "create account" : "admin console"}
			</CardTitle>
			<CardDescription class="text-slate-400">
				{isRegister
					? "create a new admin account."
					: "enter your credentials to access the dashboard."}
			</CardDescription>
		</CardHeader>
		<CardContent class="grid gap-4">
			{#if error}
				<div class="text-red-500 text-sm">{error}</div>
			{/if}
			<form onsubmit={handleSubmit} class="grid gap-4">
				<div class="grid gap-2">
					<Label for="email" class="text-slate-200">email</Label>
					<Input
						id="email"
						type="email"
						placeholder="admin@nokodo.ai"
						required
						bind:value={email}
						class="border-slate-800 bg-slate-950 text-slate-100 placeholder:text-slate-500 focus-visible:ring-slate-700"
					/>
				</div>
				{#if isRegister}
					<div class="grid gap-2">
						<Label for="username" class="text-slate-200"
							>username</Label
						>
						<Input
							id="username"
							type="text"
							placeholder="admin"
							required
							bind:value={username}
							class="border-slate-800 bg-slate-950 text-slate-100 placeholder:text-slate-500 focus-visible:ring-slate-700"
						/>
					</div>
				{/if}
				<div class="grid gap-2">
					<Label for="password" class="text-slate-200">password</Label
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
						{isRegister ? "creating account..." : "signing in..."}
					{:else}
						{isRegister ? "create account" : "sign in"}
					{/if}
				</Button>
			</form>
		</CardContent>
		<CardFooter class="flex flex-col gap-2">
			<Button
				variant="link"
				class="text-slate-400 hover:text-slate-100"
				onclick={() => (isRegister = !isRegister)}
			>
				{isRegister
					? "already have an account? sign in"
					: "need an account? create one"}
			</Button>
			<p class="text-xs text-slate-500 text-center w-full">
				restricted access. authorized personnel only.
			</p>
		</CardFooter>
	</Card>
</div>
