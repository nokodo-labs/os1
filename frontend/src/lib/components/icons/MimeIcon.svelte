<script lang="ts">
	import type { Component } from 'svelte'
	import Code from './Code.svelte'
	import CommandLine from './CommandLine.svelte'
	import Database from './Database.svelte'
	import Document from './Document.svelte'
	import DocumentChartBar from './DocumentChartBar.svelte'
	import DocumentPage from './DocumentPage.svelte'
	import Film from './Film.svelte'
	import Headphone from './Headphone.svelte'
	import Photo from './Photo.svelte'

	interface Props {
		mimeType?: string | null
		class?: string
	}

	let { mimeType = null, class: className = '' }: Props = $props()

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const Icon: Component<any> = $derived.by(() => {
		if (!mimeType) return Document
		const lower = mimeType.toLowerCase()
		const [primary, sub] = lower.split('/')

		if (primary === 'image') return Photo
		if (primary === 'video') return Film
		if (primary === 'audio') return Headphone

		// code / script types
		if (
			sub === 'javascript' ||
			sub === 'typescript' ||
			sub === 'x-python' ||
			sub === 'x-ruby' ||
			sub === 'x-java-source' ||
			sub === 'x-c' ||
			sub === 'x-c++' ||
			sub === 'x-go' ||
			sub === 'x-rust' ||
			sub === 'x-swift' ||
			sub === 'x-kotlin' ||
			sub === 'html' ||
			sub === 'xml' ||
			sub === 'css' ||
			sub === 'json' ||
			sub === 'yaml' ||
			sub === 'x-yaml' ||
			sub === 'toml'
		)
			return Code

		// shell / terminal
		if (sub === 'x-sh' || sub === 'x-shellscript' || sub === 'x-bash') return CommandLine

		// spreadsheets / data
		if (
			sub === 'csv' ||
			sub === 'vnd.ms-excel' ||
			sub === 'vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
			sub === 'x-csv'
		)
			return DocumentChartBar

		// database
		if (sub === 'sql' || sub === 'x-sql' || sub === 'x-sqlite3') return Database

		// documents / PDF
		if (
			sub === 'pdf' ||
			sub === 'msword' ||
			sub === 'vnd.openxmlformats-officedocument.wordprocessingml.document' ||
			sub === 'rtf'
		)
			return DocumentPage

		// plain text
		if (primary === 'text') return Document

		return Document
	})
</script>

<Icon class={className} />
