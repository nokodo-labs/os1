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

	let {
		onLogin,
		isRegister: initialIsRegister = false,
	}: { onLogin: () => void; isRegister?: boolean } = $props();

	let email = $state("");
	let username = $state("");
	let password = $state("");
	let isLoading = $state(false);
	let isRegister = $state(initialIsRegister);
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

<div class="flex min-h-screen items-center justify-center bg-zinc-950 p-4">
	<Card class="w-full max-w-sm border-zinc-800 bg-zinc-900 text-zinc-100">
		<CardHeader>
			<CardTitle class="text-2xl">
				{isRegister ? "create account" : "admin console"}
			</CardTitle>
			<CardDescription>
				{isRegister
					? "enter your details to create an account"
					: "enter your credentials to access the console"}
			</CardDescription>
		</CardHeader>
		<form onsubmit={handleSubmit}>
			<CardContent class="space-y-4">
				{#if error}
					<div
						class="rounded-md bg-red-500/10 p-3 text-sm text-red-500"
					>
						{error}
					</div>
				{/if}
				{#if isRegister}
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
						<Label for="username">username</Label>
						<Input
							id="username"
							type="text"
							placeholder="jdoe"
							required
							bind:value={username}
						/>
					</div>
				{/if}
				{#if !isRegister}
					<div class="space-y-2">
						<Label for="email">email or username</Label>
						<Input
							id="email"
							type="text"
							placeholder="m@example.com"
							required
							bind:value={email}
						/>
					</div>
				{/if}
				<div class="space-y-2">
					<Label for="password">password</Label>
					<Input
						id="password"
						type="password"
						required
						bind:value={password}
					/>
				</div>
			</CardContent>
			<CardFooter class="flex flex-col gap-4">
				<Button class="w-full" type="submit" disabled={isLoading}>
					{isLoading
						? "loading..."
						: isRegister
							? "create account"
							: "sign in"}
				</Button>
				<div class="text-center text-sm text-zinc-400">
					{#if isRegister}
						already have an account?
						<button
							type="button"
							class="underline hover:text-zinc-100"
							onclick={() => (isRegister = false)}
						>
							sign in
						</button>
					{:else}
						don't have an account?
						<button
							type="button"
							class="underline hover:text-zinc-100"
							onclick={() => (isRegister = true)}
						>
							create one
						</button>
					{/if}
				</div>
			</CardFooter>
		</form>
	</Card>
</div>
