<script lang="ts">
	import { Handle, Position, type Node, type NodeProps } from '@xyflow/svelte'

	type MessageNodeData = {
		role: string
		label: string
		isCurrent: boolean
		createdAt: string
	}

	type MessageNode = Node<MessageNodeData, 'message'>

	let { data, id }: NodeProps<MessageNode> = $props()

	const roleColors: Record<string, string> = {
		user: 'border-blue-700 bg-blue-950/60',
		assistant: 'border-emerald-700 bg-emerald-950/60',
		tool: 'border-amber-700 bg-amber-950/60',
		system: 'border-purple-700 bg-purple-950/60',
	}

	const roleBadgeColors: Record<string, string> = {
		user: 'bg-blue-800 text-blue-200',
		assistant: 'bg-emerald-800 text-emerald-200',
		tool: 'bg-amber-800 text-amber-200',
		system: 'bg-purple-800 text-purple-200',
	}

	let colorClass = $derived(roleColors[data.role] ?? 'border-zinc-700 bg-zinc-900')
	let badgeClass = $derived(roleBadgeColors[data.role] ?? 'bg-zinc-800 text-zinc-200')
</script>

<div
	class="w-60 rounded-xl border p-2.5 shadow-md {colorClass}"
	class:ring-2={data.isCurrent}
	class:ring-sky-500={data.isCurrent}
>
	<div class="flex items-center gap-1.5">
		<span class="rounded-md px-1.5 py-0.5 text-[10px] font-medium {badgeClass}">
			{data.role}
		</span>
		<span class="truncate text-[10px] text-zinc-500">{id.slice(0, 8)}</span>
	</div>
	<div class="mt-1.5 text-xs break-all whitespace-pre-wrap text-zinc-200">
		{data.label || '(empty)'}
	</div>
	<div class="mt-1 text-[10px] text-zinc-500">
		{new Date(data.createdAt).toLocaleTimeString()}
	</div>
</div>

<Handle type="target" position={Position.Top} class="h-2! w-2! rounded-full! bg-zinc-600!" />
<Handle type="source" position={Position.Bottom} class="h-2! w-2! rounded-full! bg-zinc-600!" />
