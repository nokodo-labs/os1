<script lang="ts">
	import Lock from '$lib/components/icons/Lock.svelte'
	import LockClosed from '$lib/components/icons/LockClosed.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
</script>

<SettingsSectionLayout
	icon={Lock}
	label="security"
	description="authentication, passwords, and access control"
>
	<div class="space-y-4">
		<!-- JWT / session info -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="flex items-center gap-2">
				<LockClosed class="h-4.5 w-4.5 text-white/60" />
				<div class="text-sm font-semibold text-white">session</div>
			</div>
			<div class="mt-1 text-sm text-white/50">
				your current session is secured with a JWT token. tokens are automatically
				refreshed.
			</div>
			<div class="mt-4 flex items-center gap-3">
				<div
					class="rounded-pill flex items-center gap-2 border border-green-500/30 bg-green-500/10 px-3 py-1.5 text-xs text-green-400"
				>
					<span class="h-1.5 w-1.5 rounded-full bg-green-400"></span>
					active session
				</div>
			</div>
		</div>

		<!-- change password -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">change password</div>
			<div class="mt-1 text-sm text-white/50">
				update your account password. you'll need to enter your current password.
			</div>
			<form class="mt-4 space-y-3" onsubmit={(e) => e.preventDefault()} autocomplete="off">
				<div>
					<label
						class="mb-1.5 block text-xs font-medium text-white/50"
						for="current-password">current password</label
					>
					<input
						id="current-password"
						type="password"
						autocomplete="current-password"
						class="rounded-pill w-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white/90 placeholder-white/30 transition-colors outline-none focus:border-white/20 focus:bg-white/8"
						placeholder="enter current password"
						disabled
					/>
				</div>
				<div>
					<label class="mb-1.5 block text-xs font-medium text-white/50" for="new-password"
						>new password</label
					>
					<input
						id="new-password"
						type="password"
						autocomplete="new-password"
						class="rounded-pill w-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white/90 placeholder-white/30 transition-colors outline-none focus:border-white/20 focus:bg-white/8"
						placeholder="enter new password"
						disabled
					/>
				</div>
				<button
					type="submit"
					disabled
					class="rounded-pill border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/40 transition-colors"
				>
					update password
				</button>
				<p class="text-xs text-white/30">coming soon</p>
			</form>
		</div>

		<!-- OIDC -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">external authentication</div>
			<div class="mt-1 text-sm text-white/50">
				connect your account to an external identity provider via OpenID Connect (OIDC) for
				single sign-on.
			</div>
			<div class="mt-4">
				<button
					type="button"
					disabled
					class="rounded-pill border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/40 transition-colors"
				>
					connect OIDC provider
				</button>
				<p class="mt-2 text-xs text-white/30">coming soon</p>
			</div>
		</div>
	</div>
</SettingsSectionLayout>
