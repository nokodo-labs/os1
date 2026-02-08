<script lang="ts">
	import {
		type AccessLevel,
		type ActionPermission,
		type DefaultPermissions_Input,
	} from '$lib/api'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'

	type PermissionsValue = DefaultPermissions_Input

	let { value = $bindable<PermissionsValue>(), allowInherit = true } = $props()

	type ResourceField = 'thread' | 'project' | 'file' | 'note' | 'group'

	const accessLevelOptions: Array<{ value: AccessLevel; label: string }> = [
		{ value: 'reader', label: 'reader' },
		{ value: 'editor', label: 'editor' },
		{ value: 'admin', label: 'admin' },
	]

	const resourceAccessFields: Array<{ key: ResourceField; label: string }> = [
		{ key: 'thread', label: 'threads' },
		{ key: 'project', label: 'projects' },
		{ key: 'file', label: 'files' },
		{ key: 'note', label: 'notes' },
		{ key: 'group', label: 'groups' },
	]

	const actionPermissionGroups: Array<{
		title: string
		items: Array<{ value: ActionPermission; label: string }>
	}> = [
		{
			title: 'roles',
			items: [
				{ value: 'roles:read', label: 'read' },
				{ value: 'roles:manage', label: 'manage' },
			],
		},
		{
			title: 'users',
			items: [
				{ value: 'users:read', label: 'read' },
				{ value: 'users:manage', label: 'manage' },
				{ value: 'users:create', label: 'create' },
			],
		},
		{
			title: 'settings',
			items: [
				{ value: 'settings:read', label: 'read' },
				{ value: 'settings:write', label: 'write' },
			],
		},
		{
			title: 'events',
			items: [
				{ value: 'events:read', label: 'read' },
				{ value: 'events:manage', label: 'manage' },
			],
		},
		{
			title: 'agents',
			items: [
				{ value: 'agents:read', label: 'read' },
				{ value: 'agents:manage', label: 'manage' },
			],
		},
		{
			title: 'models',
			items: [
				{ value: 'models:read', label: 'read' },
				{ value: 'models:manage', label: 'manage' },
			],
		},
		{
			title: 'providers',
			items: [
				{ value: 'providers:read', label: 'read' },
				{ value: 'providers:manage', label: 'manage' },
			],
		},
		{
			title: 'plugins',
			items: [
				{ value: 'plugins:read', label: 'read' },
				{ value: 'plugins:manage', label: 'manage' },
			],
		},
		{
			title: 'prompts',
			items: [
				{ value: 'prompts:read', label: 'read' },
				{ value: 'prompts:manage', label: 'manage' },
			],
		},
		{
			title: 'features',
			items: [{ value: 'files:upload', label: 'file uploads' }],
		},
	]

	const inheritValue = 'inherit'
	const noneValue = 'none'

	function displayLabel(field: ResourceField): string {
		const val = resourceValue(field)
		if (val) return val
		return allowInherit ? 'inherit' : 'no access'
	}

	function selectValue(field: ResourceField): string {
		return resourceValue(field) ?? (allowInherit ? inheritValue : noneValue)
	}

	function resourceValue(field: ResourceField): AccessLevel | null | undefined {
		return value.resource_access?.[field]
	}

	function setResourceValue(field: ResourceField, level: AccessLevel | null) {
		value = {
			...value,
			resource_access: {
				...(value.resource_access ?? {}),
				[field]: level,
			},
		}
	}

	function parseAccessLevel(value: string): AccessLevel | null {
		if (value === 'reader') return 'reader'
		if (value === 'editor') return 'editor'
		if (value === 'admin') return 'admin'
		return null
	}

	function isActionEnabled(permission: ActionPermission): boolean {
		return value.action_permissions?.includes(permission) ?? false
	}

	function toggleAction(permission: ActionPermission) {
		const current = value.action_permissions ?? []
		const next = current.includes(permission)
			? current.filter((p: ActionPermission) => p !== permission)
			: [...current, permission]

		value = {
			...value,
			action_permissions: next,
		}
	}
</script>

<div class="space-y-6">
	<div>
		<h3 class="text-sm font-semibold text-zinc-200">resource access</h3>
		<p class="text-sm text-zinc-500">
			set per-resource default access for user-owned content. {allowInherit
				? '"inherit" defers to global defaults.'
				: '"no access" means users cannot see resources they don\'t own.'}
		</p>
	</div>
	<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
		{#each resourceAccessFields as field (field.key)}
			<div class="space-y-2">
				<Label>{field.label}</Label>
				<Select
					value={selectValue(field.key)}
					onValueChange={(v: string) =>
						setResourceValue(
							field.key,
							v === (allowInherit ? inheritValue : noneValue)
								? null
								: parseAccessLevel(v)
						)}
				>
					<SelectTrigger
						class="rounded-xl {!resourceValue(field.key) && !allowInherit
							? 'border-red-900/50 text-red-400'
							: ''}"
					>
						<span class="truncate text-left">
							{displayLabel(field.key)}
						</span>
					</SelectTrigger>
					<SelectContent>
						{#if allowInherit}
							<SelectItem value={inheritValue}>inherit</SelectItem>
						{:else}
							<SelectItem value={noneValue}>
								<span class="text-red-400">no access</span>
							</SelectItem>
						{/if}
						{#each accessLevelOptions as option (option.value)}
							<SelectItem value={option.value}>{option.label}</SelectItem>
						{/each}
					</SelectContent>
				</Select>
			</div>
		{/each}
	</div>

	<div>
		<h3 class="text-sm font-semibold text-zinc-200">action permissions</h3>
		<p class="text-sm text-zinc-500">toggle default permissions granted by this scope.</p>
	</div>
	<div class="grid gap-6 xl:grid-cols-2">
		{#each actionPermissionGroups as group (group.title)}
			<div class="space-y-3 rounded-xl border border-zinc-800 bg-zinc-950 p-4">
				<div class="text-sm font-medium text-zinc-200">{group.title}</div>
				<div class="space-y-3">
					{#each group.items as item (item.value)}
						<div class="flex items-center justify-between gap-3">
							<div class="text-sm text-zinc-300">{item.label}</div>
							<Switch
								checked={isActionEnabled(item.value)}
								onCheckedChange={() => toggleAction(item.value)}
							/>
						</div>
					{/each}
				</div>
			</div>
		{/each}
	</div>
</div>
