/**
 * centralized citation source configuration.
 *
 * maps each CitationSource to its display metadata: icon component,
 * color class, url builder, widget component, and fallback label.
 * add new source types here - consumers pick them up automatically.
 */

import type { components } from '$lib/api/types'
import Brain from '$lib/components/icons/Brain.svelte'
import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
import CommandLine from '$lib/components/icons/CommandLine.svelte'
import Document from '$lib/components/icons/Document.svelte'
import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
import type { WidgetProps } from '$lib/components/widgets/types'
import type { Component } from 'svelte'

type CitationSource = components['schemas']['CitationSource']

export interface CitationSourceConfig {
	/** svelte icon component for inline previews */
	icon: Component<Record<string, unknown>>
	/** tailwind text color class for the icon */
	color: string
	/** tailwind bg class for small icon badges (pill, overlapping circles) */
	iconBg: string
	/** whether the icon supports variant="solid" */
	iconVariant?: 'solid'
	/** build a navigable URL from source_id */
	href: (sourceId: string) => string
	/** widget component to render the full card (lazy) */
	widget: () => Promise<{ default: Component<WidgetProps> }>
	/** resource type for the widget's ResourceItem */
	resourceType: string
	/** fallback display label when title is empty */
	label: string
}

/**
 * registry of all citation source types.
 * to add a new source type: add the backend enum value, then add an entry here.
 */
export const citationConfig: Record<CitationSource, CitationSourceConfig> = {
	url: {
		icon: GlobeAlt,
		color: 'text-sky-400',
		iconBg: 'bg-sky-500/20',
		iconVariant: 'solid',
		href: (id) => id,
		widget: () => import('$lib/components/widgets/UrlWidget.svelte'),
		resourceType: 'file',
		label: 'source',
	},
	file: {
		icon: Document,
		color: 'text-rose-400',
		iconBg: 'bg-rose-500/20',
		iconVariant: 'solid',
		href: (id) => `/api/v1/files/${id}/content`,
		widget: () => import('$lib/components/widgets/FileWidget.svelte'),
		resourceType: 'file',
		label: 'file',
	},
	note: {
		icon: Document,
		color: 'text-amber-400',
		iconBg: 'bg-amber-500/20',
		iconVariant: 'solid',
		href: (id) => `/notes/${id}`,
		widget: () => import('$lib/components/widgets/NoteWidget.svelte'),
		resourceType: 'note',
		label: 'note',
	},
	memory: {
		icon: Brain,
		color: 'text-purple-400',
		iconBg: 'bg-purple-500/20',
		href: () => '#',
		widget: () => import('$lib/components/widgets/UrlWidget.svelte'),
		resourceType: 'file',
		label: 'memory',
	},
	thread: {
		icon: ChatBubbles,
		color: 'text-emerald-400',
		iconBg: 'bg-emerald-500/20',
		iconVariant: 'solid',
		href: (id) => `/c/${id}`,
		widget: () => import('$lib/components/widgets/ChatWidget.svelte'),
		resourceType: 'thread',
		label: 'thread',
	},
	tool_result: {
		icon: CommandLine,
		color: 'text-orange-400',
		iconBg: 'bg-orange-500/20',
		href: () => '#',
		widget: () => import('$lib/components/widgets/UrlWidget.svelte'),
		resourceType: 'file',
		label: 'tool result',
	},
}

/** get config for a source type, with url as fallback for unknown types */
export function getSourceConfig(sourceType: CitationSource): CitationSourceConfig {
	return citationConfig[sourceType] ?? citationConfig.url
}
