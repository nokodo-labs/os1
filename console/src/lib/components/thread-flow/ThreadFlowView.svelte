<script lang="ts">
	import {
		Background,
		BackgroundVariant,
		Controls,
		SvelteFlow,
		SvelteFlowProvider,
		type Edge,
		type Node,
	} from '@xyflow/svelte'
	import '@xyflow/svelte/dist/style.css'
	import ThreadFlowNode from './ThreadFlowNode.svelte'

	type Message = {
		id: string
		parent_id?: string | null
		type?: string
		content?: { type: string; text?: string; data?: unknown; reason?: string }[]
		tool_calls?: Record<string, unknown>[]
		created_at: string
	}

	type Props = {
		messages: Message[]
		currentMessageId?: string | null
	}

	let { messages, currentMessageId }: Props = $props()

	const nodeTypes = { message: ThreadFlowNode }

	function extractLabel(msg: Message): string {
		const parts = msg.content ?? []
		for (const p of parts) {
			if ('text' in p && typeof p.text === 'string') {
				return p.text
			}
			if ('data' in p && p.data) {
				return JSON.stringify(p.data, null, 2)
			}
			if ('reason' in p && typeof p.reason === 'string') {
				return `refusal: ${p.reason}`
			}
		}
		if (msg.tool_calls?.length) {
			return msg.tool_calls
				.map((tc) => {
					const r = tc as Record<string, unknown>
					const name = r.name ?? '?'
					const args = r.arguments ?? r.args ?? null
					if (args) {
						let parsed: string
						if (typeof args === 'string') {
							try {
								parsed = JSON.stringify(JSON.parse(args), null, 2)
							} catch {
								parsed = args
							}
						} else {
							parsed = JSON.stringify(args, null, 2)
						}
						return `${name}(\n${parsed}\n)`
					}
					return `${name}()`
				})
				.join('\n\n')
		}
		return '(no content)'
	}

	// Build tree layout from messages
	function buildLayout(msgs: Message[]): { nodes: Node[]; edges: Edge[] } {
		if (msgs.length === 0) return { nodes: [], edges: [] }

		const byId: Record<string, Message> = {}
		const childrenMap: Record<string, string[]> = {}

		for (const m of msgs) {
			byId[m.id] = m
			if (!childrenMap[m.id]) childrenMap[m.id] = []
			const pid = m.parent_id ?? null
			if (pid) {
				if (!childrenMap[pid]) childrenMap[pid] = []
				childrenMap[pid].push(m.id)
			}
		}

		// find roots (no parent or parent not in set)
		const roots = msgs.filter((m) => !m.parent_id || !byId[m.parent_id])

		// BFS to assign levels and positions
		const levelOffset = 350
		const siblingOffset = 270
		const posMap: Record<string, { level: number; position: number }> = {}
		const layerWidths: Record<number, number> = {}

		const queue: { id: string; level: number }[] = roots.map((r) => ({
			id: r.id,
			level: 0,
		}))

		while (queue.length > 0) {
			const item = queue.shift()
			if (!item) break
			if (posMap[item.id]) continue

			const level = item.level
			if (!layerWidths[level]) layerWidths[level] = 0
			posMap[item.id] = { level, position: layerWidths[level]++ }

			const children = childrenMap[item.id] ?? []
			for (const cid of children) {
				if (!posMap[cid]) {
					queue.push({ id: cid, level: level + 1 })
				}
			}
		}

		const nodes: Node[] = []
		const edges: Edge[] = []

		for (const m of msgs) {
			const pos = posMap[m.id]
			if (!pos) continue

			nodes.push({
				id: m.id,
				type: 'message',
				style: 'background: transparent; border: none; padding: 0; box-shadow: none;',
				data: {
					role: m.type ?? 'message',
					label: extractLabel(m),
					isCurrent: m.id === currentMessageId,
					createdAt: m.created_at,
				},
				position: {
					x: pos.position * siblingOffset,
					y: pos.level * levelOffset,
				},
			})

			if (m.parent_id && byId[m.parent_id]) {
				const isOnActivePath =
					m.id === currentMessageId || isAncestorOf(m.id, currentMessageId, childrenMap)
				edges.push({
					id: `${m.parent_id}-${m.id}`,
					source: m.parent_id,
					target: m.id,
					type: 'smoothstep',
					animated: isOnActivePath,
					style: isOnActivePath
						? 'stroke: rgb(56, 189, 248); stroke-width: 2px;'
						: 'stroke: rgb(63, 63, 70); stroke-width: 1.5px;',
				})
			}
		}

		return { nodes, edges }
	}

	function isAncestorOf(
		nodeId: string,
		targetId: string | null | undefined,
		childrenMap: Record<string, string[]>
	): boolean {
		if (!targetId) return false
		const children = childrenMap[nodeId] ?? []
		return children.some((cid) => cid === targetId || isAncestorOf(cid, targetId, childrenMap))
	}

	let layout = $derived(buildLayout(messages))

	// Compute canvas dimensions from node bounding box so the wrapper sizes to content
	let canvasDims = $derived(
		layout.nodes.reduce(
			(acc, n) => ({
				w: Math.max(acc.w, n.position.x + 300),
				h: Math.max(acc.h, n.position.y + 400),
			}),
			{ w: 400, h: 300 }
		)
	)
</script>

<div
	class="flow-wrap overflow-hidden rounded-xl bg-zinc-950"
	style="width: min({canvasDims.w}px, 80vw); height: min({canvasDims.h}px, 75vh);"
>
	<SvelteFlowProvider>
		<SvelteFlow
			nodes={layout.nodes}
			edges={layout.edges}
			{nodeTypes}
			fitView
			minZoom={0.05}
			maxZoom={2}
			colorMode="dark"
			nodesConnectable={false}
			nodesDraggable={false}
			elementsSelectable={false}
		>
			<Background variant={BackgroundVariant.Dots} patternColor="rgba(255,255,255,0.07)" />
			<Controls showLock={false} />
		</SvelteFlow>
	</SvelteFlowProvider>
</div>

<style>
	.flow-wrap :global(.svelte-flow) {
		background: transparent;
	}

	.flow-wrap :global(.svelte-flow__node) {
		background: transparent;
		border: none;
		padding: 0;
		box-shadow: none;
	}

	.flow-wrap :global(.svelte-flow__controls) {
		box-shadow: none;
		overflow: hidden;
		border: 1px solid rgb(63 63 70);
		border-radius: 0.5rem;
	}

	.flow-wrap :global(.svelte-flow__controls-button) {
		background: rgb(24 24 27);
		border-bottom-color: rgb(63 63 70);
		fill: rgb(161 161 170);
		color: rgb(161 161 170);
	}

	.flow-wrap :global(.svelte-flow__controls-button:hover) {
		background: rgb(39 39 42);
		fill: rgb(228 228 231);
	}

	.flow-wrap :global(.svelte-flow__edge path) {
		stroke-width: 1.5;
	}
</style>
