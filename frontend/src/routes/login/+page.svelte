<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/stores'
	import { AuthService } from '$lib/api/generated'
	import * as Button from '$lib/components/ui/button'
	import { refreshSession, setSessionToken } from '$lib/stores/session'

	let email = $state('')
	let password = $state('')
	let isSubmitting = $state(false)
	let errorMessage = $state<string | null>(null)

	const next = $derived($page.url.searchParams.get('next') ?? '/')

	$effect(() => {
		const fromQuery = $page.url.searchParams.get('email')
		if (fromQuery && !email) email = fromQuery
	})

	async function onSubmit(event: SubmitEvent) {
		event.preventDefault()
		if (isSubmitting) return

		errorMessage = null
		isSubmitting = true

		try {
			const token = await AuthService.loginAccessTokenAuthLoginAccessTokenPost({
				username: email.trim(),
				password,
			})
			setSessionToken(token.access_token)
			void refreshSession()
			// @ts-expect-error resolve typing is narrower than our constructed URL
			await goto(resolve(next as never))
		} catch (err) {
			errorMessage = err instanceof Error ? err.message : 'failed to sign in'
		} finally {
			isSubmitting = false
		}
	}
</script>

<div class="flex-1 overflow-y-auto">
	<div class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-8 pt-8 pb-24">
		<div class="flex flex-1 items-center justify-center">
			<div class="w-full max-w-md">
				<div
					class="overflow-hidden rounded-3xl border border-white/10 bg-black/65 shadow-[0_28px_80px_rgba(0,0,0,0.45)] backdrop-blur-md"
				>
					<div class="p-8">
						<div class="mb-8 space-y-2">
							<h1 class="text-2xl font-medium text-white">welcome back</h1>
							<p class="text-sm text-white/55">sign in to continue</p>
						</div>

						<form class="space-y-4" onsubmit={onSubmit}>
							<div class="space-y-2">
								<label class="text-sm font-medium text-white/75" for="email"
									>email</label
								>
								<input
									id="email"
									type="email"
									autocomplete="email"
									required
									bind:value={email}
									placeholder="you@company.com"
									class="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							<div class="space-y-2">
								<label class="text-sm font-medium text-white/75" for="password"
									>password</label
								>
								<input
									id="password"
									type="password"
									autocomplete="current-password"
									required
									bind:value={password}
									placeholder="••••••••"
									class="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							{#if errorMessage}
								<div
									class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/75"
								>
									{errorMessage}
								</div>
							{/if}

							<Button.Root
								type="submit"
								disabled={isSubmitting}
								class="h-11 w-full rounded-2xl"
							>
								{isSubmitting ? 'signing in…' : 'sign in'}
							</Button.Root>
						</form>

						<div class="mt-6 text-center text-sm text-white/55">
							don't have an account?
							<a
								href={resolve('/signup')}
								class="ml-1 font-medium text-white/80 hover:text-white"
							>
								sign up
							</a>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</div>
