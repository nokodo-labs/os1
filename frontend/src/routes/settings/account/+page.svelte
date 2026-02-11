<script lang="ts">
	import { apiClient } from '$lib/api/client'
	import Camera from '$lib/components/icons/Camera.svelte'
	import UserCircle from '$lib/components/icons/UserCircle.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { debounce, getUserInitials } from '$lib/utils'

	// local state for inline editing
	let displayName = $derived(session.currentUser?.display_name ?? '')
	let bio = $derived(preferences.data.account.bio ?? '')
	let birthDate = $derived(preferences.data.account.birthDate ?? '')
	let gender = $derived(preferences.data.account.gender ?? '')

	const avatarUrl = $derived(session.currentUser?.avatar_url ?? null)
	const email = $derived(session.currentUser?.email ?? '')

	// debounced saves
	const saveDisplayName = debounce(async (value: string) => {
		const uid = session.currentUser?.id
		if (!uid) return
		const { data: res } = await apiClient().PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: uid } },
			body: { display_name: value || null },
		})
		if (res) session.currentUser = { ...res }
	}, 600)

	const saveBio = debounce(
		(value: string) => void preferences.update('account', { bio: value || null }),
		600
	)

	function saveBirthDate(value: string): void {
		void preferences.update('account', { birthDate: value || null })
	}

	function saveGender(value: string): void {
		void preferences.update('account', { gender: value || null })
	}

	const genderOptions = [
		{ value: '', label: 'prefer not to say' },
		{ value: 'male', label: 'male' },
		{ value: 'female', label: 'female' },
		{ value: 'non-binary', label: 'non-binary' },
		{ value: 'other', label: 'other' },
	]
</script>

<SettingsSectionLayout
	icon={UserCircle}
	label="account"
	description="manage your profile and personal information"
>
	<div class="space-y-4">
		<!-- profile picture + name -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">profile</div>
			<div class="mt-1 text-sm text-white/50">
				your display name and avatar. visible to other users.
			</div>

			<div class="mt-4 flex items-center gap-5">
				<!-- avatar -->
				<button
					type="button"
					class="group relative h-18 w-18 shrink-0 cursor-pointer overflow-hidden rounded-full border-none bg-transparent"
					aria-label="change profile picture"
				>
					{#if avatarUrl}
						<img src={avatarUrl} alt="profile" class="h-full w-full object-cover" />
					{:else}
						<div
							class="flex h-full w-full items-center justify-center text-lg font-semibold text-white uppercase"
							style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
						>
							{getUserInitials(displayName || 'U')}
						</div>
					{/if}
					<div
						class="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 transition-opacity group-hover:opacity-100"
					>
						<Camera class="h-5 w-5 text-white" />
					</div>
				</button>

				<!-- name field -->
				<div class="flex-1">
					<label class="mb-1.5 block text-xs font-medium text-white/50" for="display-name"
						>display name</label
					>
					<input
						id="display-name"
						type="text"
						class="rounded-pill w-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white/90 placeholder-white/30 transition-colors outline-none focus:border-white/20 focus:bg-white/8"
						placeholder="your name"
						bind:value={displayName}
						oninput={() => saveDisplayName(displayName)}
					/>
				</div>
			</div>
		</div>

		<!-- email (read-only) -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">email</div>
			<div class="mt-1 text-sm text-white/50">
				your email address for notifications and account recovery.
			</div>
			<div
				class="rounded-pill mt-3 flex w-full items-center border border-white/8 bg-white/3 px-4 py-2.5 text-sm text-white/60"
			>
				{email}
			</div>
		</div>

		<!-- birth date -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">birth date</div>
			<div class="mt-1 text-sm text-white/50">used for personalization. never shared.</div>
			<input
				type="date"
				class="rounded-pill mt-3 w-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white/90 scheme-dark transition-colors outline-none focus:border-white/20 focus:bg-white/8"
				value={birthDate}
				onchange={(e) => saveBirthDate(e.currentTarget.value)}
			/>
		</div>

		<!-- gender -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">gender</div>
			<div class="mt-1 text-sm text-white/50">
				optional. used for personalization and pronouns.
			</div>
			<select
				class="rounded-pill mt-3 w-full cursor-pointer appearance-none border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white/90 scheme-dark transition-colors outline-none focus:border-white/20 focus:bg-white/8"
				value={gender}
				onchange={(e) => saveGender(e.currentTarget.value)}
			>
				{#each genderOptions as opt (opt.value)}
					<option value={opt.value} class="bg-neutral-900">{opt.label}</option>
				{/each}
			</select>
		</div>

		<!-- bio -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white">bio</div>
			<div class="mt-1 text-sm text-white/50">
				a short description about yourself. visible on your profile.
			</div>
			<textarea
				class="mt-3 w-full resize-none rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 placeholder-white/30 transition-colors outline-none focus:border-white/20 focus:bg-white/8"
				rows="3"
				placeholder="tell others a bit about yourself..."
				bind:value={bio}
				oninput={() => saveBio(bio)}
			></textarea>
		</div>
	</div>
</SettingsSectionLayout>
