<script lang="ts">
	import { goto } from "$app/navigation";
	import { auth } from "$lib/auth.svelte";
	import { Button } from "$lib/components/ui/button";
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from "$lib/components/ui/card";
	import { Input } from "$lib/components/ui/input";
	import { Label } from "$lib/components/ui/label";

	let email = $state("");
	let password = $state("");
	let isLoading = $state(false);
	let error = $state<string | null>(null);

	async function handleSubmit(e: Event) {
		e.preventDefault();
		isLoading = true;
		error = null;

		try {
			await auth.login(email, password);
			goto("/dashboard");
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
			<CardTitle class="text-2xl">admin console</CardTitle>
			<CardDescription>
				enter your credentials to access the console
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
			<div class="p-6 pt-0">
				<Button type="submit" class="w-full" disabled={isLoading}>
					{isLoading ? "signing in..." : "sign in"}
				</Button>
			</div>
		</form>
	</Card>
</div>
