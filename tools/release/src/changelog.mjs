// changelog generation - shared between release workflow and promotion PR.
// parses conventional commits and renders categorized markdown.

import { CommitParser } from "conventional-commits-parser";
import { BREAKING_KEYWORDS, CHANGELOG_SECTIONS, SECTION_ORDER } from "./config.mjs";
import { getCommits, shortHash } from "./git.mjs";

const parser = new CommitParser({
	headerPattern: /^(\w*)(?:\(([^)]*)\))?!?:\s(.*)$/,
	headerCorrespondence: ["type", "scope", "subject"],
	noteKeywords: BREAKING_KEYWORDS,
});

// build a type -> section lookup from config.
const typeToSection = new Map();
for (const entry of CHANGELOG_SECTIONS) {
	typeToSection.set(entry.type, entry.section);
}

// parse a raw commit message into a structured object.
export function parseCommit(rawMessage) {
	return parser.parse(rawMessage);
}

// extract PR number from commit message body trailers or squash-merge subject.
// GitHub adds (#123) to squash-merge subjects and trailers like "PR-URL: .../pull/123".
function extractPRNumber(message) {
	// squash-merge pattern: subject (#123)
	const squashMatch = message.match(/\(#(\d+)\)\s*$/m);
	if (squashMatch) return parseInt(squashMatch[1], 10);
	// trailer pattern: PR-URL or Closes
	const trailerMatch = message.match(
		/(?:PR-URL|Closes|Fixes|Resolves):\s*(?:.*\/pull\/|#)(\d+)/i,
	);
	if (trailerMatch) return parseInt(trailerMatch[1], 10);
	return null;
}

// parse all commits between two refs and return structured data.
// paths: optional array of file/dir paths to restrict commits to.
export function parseCommitRange(from, to = "HEAD", paths = []) {
	const rawCommits = getCommits(from, to, paths);
	const parsed = [];

	for (const { hash, author, message } of rawCommits) {
		const commit = parseCommit(message);
		if (!commit.type) continue;

		const section = typeToSection.get(commit.type);
		if (!section) continue;

		parsed.push({
			hash: shortHash(hash),
			type: commit.type,
			scope: commit.scope || null,
			subject: commit.subject,
			section,
			author: author || null,
			pr: extractPRNumber(message),
			breaking: commit.notes.some((n) =>
				BREAKING_KEYWORDS.includes(n.title),
			),
		});
	}

	return parsed;
}

// determine recommended bump type from parsed commits.
export function recommendBump(parsedCommits) {
	let level = null; // null = no bump, 'patch', 'minor', 'major'

	for (const commit of parsedCommits) {
		if (commit.breaking) return "major";

		if (commit.type === "feat") {
			if (level !== "major") level = "minor";
		} else if (
			["fix", "perf", "refactor", "revert"].includes(commit.type)
		) {
			if (!level) level = "patch";
		}
	}

	return level;
}

// render parsed commits into markdown changelog.
// repoSlug: "owner/repo" for generating links.
// options.compareFrom/compareTo: refs for the compare link.
// options.title: optional title override.
// options.maxLength: max character length; sections are trimmed if exceeded.
export function renderChangelog(parsedCommits, repoSlug, options = {}) {
	const grouped = new Map();
	for (const section of SECTION_ORDER) {
		grouped.set(section, []);
	}

	// collect breaking changes separately
	const breakingChanges = [];

	for (const commit of parsedCommits) {
		const list = grouped.get(commit.section);
		if (list) list.push(commit);
		if (commit.breaking) breakingChanges.push(commit);
	}

	const lines = [];

	if (options.title) {
		lines.push(`## ${options.title}`, "");
	}

	// breaking changes callout
	if (breakingChanges.length > 0) {
		lines.push("## ⚠️ breaking changes", "");
		for (const c of breakingChanges) {
			lines.push(formatCommitLine(c, repoSlug));
		}
		lines.push("");
	}

	// regular sections
	for (const section of SECTION_ORDER) {
		const commits = grouped.get(section);
		if (!commits || commits.length === 0) continue;
		lines.push(`## ${section}`, "");
		for (const c of commits) {
			lines.push(formatCommitLine(c, repoSlug));
		}
		lines.push("");
	}

	// compare link
	if (options.compareFrom && options.compareTo && repoSlug) {
		lines.push("## 🔗 full changelog");
		lines.push(
			`https://github.com/${repoSlug}/compare/${options.compareFrom}...${options.compareTo}`,
		);
		lines.push("");
	}

	let result = lines.join("\n").trim();

	// truncate if exceeding maxLength
	if (options.maxLength && result.length > options.maxLength) {
		const compareBlock =
			options.compareFrom && options.compareTo && repoSlug
				? `\n\n## 🔗 full changelog\nhttps://github.com/${repoSlug}/compare/${options.compareFrom}...${options.compareTo}`
				: "";
		const truncNote = `\n\n> **note:** changelog truncated (${parsedCommits.length} commits). see full changelog link below for complete diff.`;
		const budget =
			options.maxLength - truncNote.length - compareBlock.length - 10;
		result = result.slice(0, budget);
		// trim to last complete line
		const lastNewline = result.lastIndexOf("\n");
		if (lastNewline > 0) result = result.slice(0, lastNewline);
		result += truncNote + compareBlock;
	}

	return result;
}

function formatCommitLine(commit, repoSlug) {
	const scope = commit.scope ? `**${commit.scope}:** ` : "";
	const hash = repoSlug
		? `([${commit.hash}](https://github.com/${repoSlug}/commit/${commit.hash}))`
		: `(${commit.hash})`;
	const pr =
		commit.pr && repoSlug
			? ` [#${commit.pr}](https://github.com/${repoSlug}/pull/${commit.pr})`
			: "";
	const author = commit.author ? ` - @${commit.author}` : "";
	return `- ${scope}${commit.subject} ${hash}${pr}${author}`;
}

// CLI entry point: node src/changelog.mjs --from <ref> --to <ref>
// used by promotion.yml to generate changelog body.
if (process.argv[1] && process.argv[1].endsWith("changelog.mjs")) {
	const args = process.argv.slice(2);
	const fromIdx = args.indexOf("--from");
	const toIdx = args.indexOf("--to");

	if (fromIdx === -1 || toIdx === -1) {
		console.error("usage: node changelog.mjs --from <ref> --to <ref>");
		process.exit(1);
	}

	const from = args[fromIdx + 1];
	const to = args[toIdx + 1];

	const { getRepoSlug } = await import("./git.mjs");
	const repoSlug = getRepoSlug();
	const commits = parseCommitRange(from, to);
	const changelog = renderChangelog(commits, repoSlug, {
		compareFrom: from,
		compareTo: to,
	});

	process.stdout.write(changelog);
}
