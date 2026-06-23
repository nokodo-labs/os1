<script lang="ts">
	import type { Schemas } from '$lib/api'

	type DefaultPermissionsSettings = Schemas['DefaultPermissionsSettings']

	import DefaultPermissionsEditor from '$lib/components/DefaultPermissionsEditor.svelte'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'

	type Props = {
		value?: DefaultPermissionsSettings
	}

	let {
		value = $bindable({
			resource_access: {
				thread: null,
				project: null,
				file: null,
				calendar: null,
				note: null,
				group: null,
				reminder_list: null,
			},
			action_permissions: [],
		}),
	}: Props = $props()
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>default permissions</CardTitle>
		<CardDescription>
			global defaults applied when no role or explicit rule grants access.
		</CardDescription>
	</CardHeader>
	<CardContent>
		<DefaultPermissionsEditor bind:value allowInherit={false} />
	</CardContent>
</Card>
