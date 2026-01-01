<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { api } from '$lib/api'
	import * as Button from '$lib/components/ui/button'

	let email = $state('')
	let displayName = $state('')
	let password = $state('')
	let passwordConfirm = $state('')
	let isSubmitting = $state(false)
	let errorMessage = $state<string | null>(null)

	const canSubmit = $derived(
		email.trim().length > 0 &&
			password.length >= 1 &&
			passwordConfirm.length >= 1 &&
			password === passwordConfirm
	)

	async function onSubmit(event: SubmitEvent) {
		event.preventDefault()
		if (isSubmitting) return

		errorMessage = null

		if (password !== passwordConfirm) {
			errorMessage = 'passwords do not match'
			return
		}

		isSubmitting = true
		try {
			await api.createUser({
				email: email.trim(),
				password,
				is_active: true,
				is_superuser: false,
				display_name: displayName.trim() ? displayName.trim() : null,
			})
			// @ts-expect-error resolve typing is narrower than our constructed URL
			await goto(resolve(`/login?email=${encodeURIComponent(email.trim())}` as never))
		} catch (err) {
			errorMessage = err instanceof Error ? err.message : 'failed to create account'
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
					class="liquid-glass liquid-glass--frosted rounded-container overflow-hidden shadow-[0_28px_80px_rgba(0,0,0,0.45)]"
				>
					<div class="p-8">
						<div class="mb-8 space-y-2">
							<h1 class="text-2xl font-medium text-white">create your account</h1>
							<p class="text-sm text-white/55">sign up to get started</p>
						</div>

						<form class="space-y-4" onsubmit={onSubmit}>
							<div class="space-y-2">
								<label class="text-sm font-medium text-white/75" for="displayName"
									>name</label
								>
								<input
									id="displayName"
									type="text"
									autocomplete="name"
									bind:value={displayName}
									placeholder="optional"
									class="w-full rounded-full border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

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
									class="w-full rounded-full border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							<div class="space-y-2">
								<label class="text-sm font-medium text-white/75" for="password"
									>password</label
								>
								<input
									id="password"
									type="password"
									autocomplete="new-password"
									required
									bind:value={password}
									placeholder="••••••••"
									class="w-full rounded-full border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							<div class="space-y-2">
								<label
									class="text-sm font-medium text-white/75"
									for="passwordConfirm">confirm password</label
								>
								<input
									id="passwordConfirm"
									type="password"
									autocomplete="new-password"
									required
									bind:value={passwordConfirm}
									placeholder="••••••••"
									class="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							{#if passwordConfirm.length > 0 && password !== passwordConfirm}
								<div class="text-sm text-white/55">passwords must match</div>
							{/if}

							{#if errorMessage}
								<div
									class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/75"
								>
									{errorMessage}
								</div>
							{/if}

							<Button.Root
								type="submit"
								disabled={!canSubmit || isSubmitting}
								class="h-11 w-full rounded-full"
							>
								{isSubmitting ? 'creating account…' : 'sign up'}
							</Button.Root>
						</form>

						<div class="mt-6 text-center text-sm text-white/55">
							already have an account?
							<a
								href={resolve('/login')}
								class="ml-1 font-medium text-white/80 hover:text-white"
							>
								sign in
							</a>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</div>
