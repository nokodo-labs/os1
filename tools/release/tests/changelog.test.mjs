// tests for changelog parsing, PR extraction, bump recommendation, and rendering.
// uses node:test built-in runner (Node 24+).

import { CommitParser } from "conventional-commits-parser";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { CHANGELOG_SECTIONS, SECTION_ORDER } from "../src/config.mjs";

// -- inline key functions from changelog.mjs to test without git deps --

const parser = new CommitParser({
	headerPattern: /^(\w*)(?:\(([^)]*)\))?!?:\s(.*)$/,
	headerCorrespondence: ["type", "scope", "subject"],
	noteKeywords: ["BREAKING CHANGE", "BREAKING-CHANGE"],
});

const typeToSection = new Map();
for (const entry of CHANGELOG_SECTIONS) {
	typeToSection.set(entry.type, entry.section);
}

function parseCommit(rawMessage) {
	return parser.parse(rawMessage);
}

function extractPRNumber(message) {
	const squashMatch = message.match(/\(#(\d+)\)\s*$/m);
	if (squashMatch) return parseInt(squashMatch[1], 10);
	const trailerMatch = message.match(
		/(?:PR-URL|Closes|Fixes|Resolves):\s*(?:.*\/pull\/|#)(\d+)/i,
	);
	if (trailerMatch) return parseInt(trailerMatch[1], 10);
	return null;
}

function recommendBump(parsedCommits) {
	let level = null;
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

function renderChangelog(parsedCommits, repoSlug, options = {}) {
	const grouped = new Map();
	for (const section of SECTION_ORDER) {
		grouped.set(section, []);
	}

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

	if (breakingChanges.length > 0) {
		lines.push("## ⚠️ breaking changes", "");
		for (const c of breakingChanges) {
			lines.push(formatCommitLine(c, repoSlug));
		}
		lines.push("");
	}

	for (const section of SECTION_ORDER) {
		const commits = grouped.get(section);
		if (!commits || commits.length === 0) continue;
		lines.push(`## ${section}`, "");
		for (const c of commits) {
			lines.push(formatCommitLine(c, repoSlug));
		}
		lines.push("");
	}

	if (options.compareFrom && options.compareTo && repoSlug) {
		lines.push("## 🔗 full changelog");
		lines.push(
			`https://github.com/${repoSlug}/compare/${options.compareFrom}...${options.compareTo}`,
		);
		lines.push("");
	}

	let result = lines.join("\n").trim();

	if (options.maxLength && result.length > options.maxLength) {
		const compareBlock =
			options.compareFrom && options.compareTo && repoSlug
				? `\n\n## 🔗 full changelog\nhttps://github.com/${repoSlug}/compare/${options.compareFrom}...${options.compareTo}`
				: "";
		const truncNote = `\n\n> **note:** changelog truncated (${parsedCommits.length} commits). see full changelog link below for complete diff.`;
		const budget =
			options.maxLength - truncNote.length - compareBlock.length - 10;
		result = result.slice(0, budget);
		const lastNewline = result.lastIndexOf("\n");
		if (lastNewline > 0) result = result.slice(0, lastNewline);
		result += truncNote + compareBlock;
	}

	return result;
}

// -- tests --

describe("parseCommit", () => {
	it("should parse a feat commit", () => {
		const result = parseCommit("feat(ui): add new button");
		assert.equal(result.type, "feat");
		assert.equal(result.scope, "ui");
		assert.equal(result.subject, "add new button");
	});

	it("should parse a fix commit without scope", () => {
		const result = parseCommit("fix: correct typo");
		assert.equal(result.type, "fix");
		assert.equal(result.scope, null);
		assert.equal(result.subject, "correct typo");
	});

	it("should detect breaking change via exclamation", () => {
		const result = parseCommit(
			"feat!: remove old API\n\nBREAKING CHANGE: removed v1 endpoints",
		);
		assert.equal(result.type, "feat");
		assert.ok(result.notes.length > 0);
		assert.equal(result.notes[0].title, "BREAKING CHANGE");
	});

	it("should detect breaking change via footer", () => {
		const result = parseCommit(
			"refactor: overhaul auth\n\nBREAKING-CHANGE: token format changed",
		);
		assert.ok(result.notes.length > 0);
	});

	it("should return null/undefined type for non-conventional messages", () => {
		const result = parseCommit("random commit message");
		assert.ok(!result.type, "type should be falsy for non-conventional");
	});

	it("should parse chore commit", () => {
		const result = parseCommit("chore(deps): update dependencies");
		assert.equal(result.type, "chore");
		assert.equal(result.scope, "deps");
	});
});

describe("extractPRNumber", () => {
	it("should extract from squash-merge subject", () => {
		assert.equal(extractPRNumber("feat(ui): add button (#42)"), 42);
	});

	it("should extract from PR-URL trailer", () => {
		assert.equal(
			extractPRNumber(
				"feat: something\n\nPR-URL: https://github.com/org/repo/pull/123",
			),
			123,
		);
	});

	it("should extract from Closes trailer", () => {
		assert.equal(extractPRNumber("fix: bug\n\nCloses: #99"), 99);
	});

	it("should extract from Fixes trailer with full URL", () => {
		assert.equal(
			extractPRNumber(
				"fix: crash\n\nFixes: https://github.com/org/repo/pull/55",
			),
			55,
		);
	});

	it("should return null when no PR reference", () => {
		assert.equal(extractPRNumber("feat: plain commit"), null);
	});

	it("should handle multiline body with PR in subject", () => {
		assert.equal(
			extractPRNumber(
				"feat(core): implement feature (#7)\n\nsome long description\nwith multiple lines",
			),
			7,
		);
	});

	it("should not match parenthetical numbers mid-line", () => {
		// (#123) must be at end of a line to match squash pattern
		assert.equal(
			extractPRNumber("feat: handle (#123) edge case properly"),
			null,
		);
	});
});

describe("recommendBump", () => {
	it("should return null for empty commits", () => {
		assert.equal(recommendBump([]), null);
	});

	it("should return null for non-bumping commits", () => {
		assert.equal(
			recommendBump([
				{ type: "chore", breaking: false },
				{ type: "docs", breaking: false },
			]),
			null,
		);
	});

	it("should return patch for fix commits", () => {
		assert.equal(
			recommendBump([{ type: "fix", breaking: false }]),
			"patch",
		);
	});

	it("should return minor for feat commits", () => {
		assert.equal(
			recommendBump([{ type: "feat", breaking: false }]),
			"minor",
		);
	});

	it("should return major for breaking changes", () => {
		assert.equal(recommendBump([{ type: "fix", breaking: true }]), "major");
	});

	it("should escalate from patch to minor", () => {
		assert.equal(
			recommendBump([
				{ type: "fix", breaking: false },
				{ type: "feat", breaking: false },
			]),
			"minor",
		);
	});

	it("should return major immediately on breaking", () => {
		assert.equal(
			recommendBump([
				{ type: "feat", breaking: false },
				{ type: "fix", breaking: true },
				{ type: "feat", breaking: false },
			]),
			"major",
		);
	});

	it("should handle perf as patch", () => {
		assert.equal(
			recommendBump([{ type: "perf", breaking: false }]),
			"patch",
		);
	});

	it("should handle refactor as patch", () => {
		assert.equal(
			recommendBump([{ type: "refactor", breaking: false }]),
			"patch",
		);
	});

	it("should handle revert as patch", () => {
		assert.equal(
			recommendBump([{ type: "revert", breaking: false }]),
			"patch",
		);
	});
});

describe("formatCommitLine", () => {
	it("should format basic commit line", () => {
		const line = formatCommitLine(
			{
				hash: "abc1234",
				scope: null,
				subject: "add feature",
				pr: null,
				author: null,
			},
			"org/repo",
		);
		assert.equal(
			line,
			"- add feature ([abc1234](https://github.com/org/repo/commit/abc1234))",
		);
	});

	it("should include scope", () => {
		const line = formatCommitLine(
			{
				hash: "abc1234",
				scope: "ui",
				subject: "add button",
				pr: null,
				author: null,
			},
			"org/repo",
		);
		assert.ok(line.includes("**ui:** add button"));
	});

	it("should include PR link", () => {
		const line = formatCommitLine(
			{
				hash: "abc1234",
				scope: null,
				subject: "fix bug",
				pr: 42,
				author: null,
			},
			"org/repo",
		);
		assert.ok(line.includes("[#42](https://github.com/org/repo/pull/42)"));
	});

	it("should include author", () => {
		const line = formatCommitLine(
			{
				hash: "abc1234",
				scope: null,
				subject: "fix bug",
				pr: null,
				author: "alice",
			},
			"org/repo",
		);
		assert.ok(line.includes("- @alice"));
	});

	it("should include all parts together", () => {
		const line = formatCommitLine(
			{
				hash: "abc1234",
				scope: "api",
				subject: "add endpoint",
				pr: 99,
				author: "bob",
			},
			"org/repo",
		);
		assert.ok(line.startsWith("- **api:** add endpoint"));
		assert.ok(line.includes("[abc1234]"));
		assert.ok(line.includes("[#99]"));
		assert.ok(line.includes("- @bob"));
	});

	it("should work without repoSlug", () => {
		const line = formatCommitLine(
			{
				hash: "abc1234",
				scope: null,
				subject: "change",
				pr: 5,
				author: "eve",
			},
			null,
		);
		assert.equal(line, "- change (abc1234) - @eve");
	});
});

describe("renderChangelog", () => {
	const commits = [
		{
			hash: "aaa1111",
			type: "feat",
			scope: "ui",
			subject: "add modal",
			section: "✨ new features",
			author: "alice",
			pr: 10,
			breaking: false,
		},
		{
			hash: "bbb2222",
			type: "fix",
			scope: null,
			subject: "fix crash",
			section: "🐛 bug fixes",
			author: "bob",
			pr: 11,
			breaking: false,
		},
		{
			hash: "ccc3333",
			type: "docs",
			scope: null,
			subject: "update readme",
			section: "📚 documentation",
			author: null,
			pr: null,
			breaking: false,
		},
	];

	it("should render sections in correct order", () => {
		const md = renderChangelog(commits, "org/repo");
		const featIdx = md.indexOf("## ✨ new features");
		const fixIdx = md.indexOf("## 🐛 bug fixes");
		const docsIdx = md.indexOf("## 📚 documentation");
		assert.ok(featIdx < fixIdx, "features should come before fixes");
		assert.ok(fixIdx < docsIdx, "fixes should come before docs");
	});

	it("should skip empty sections", () => {
		const md = renderChangelog(commits, "org/repo");
		assert.ok(!md.includes("## 🔧 improvements"));
		assert.ok(!md.includes("## 🧹 miscellaneous"));
	});

	it("should include compare link when refs provided", () => {
		const md = renderChangelog(commits, "org/repo", {
			compareFrom: "v1.0.0",
			compareTo: "v1.1.0",
		});
		assert.ok(md.includes("## 🔗 full changelog"));
		assert.ok(md.includes("org/repo/compare/v1.0.0...v1.1.0"));
	});

	it("should truncate when exceeding maxLength", () => {
		const md = renderChangelog(commits, "org/repo", {
			compareFrom: "v0",
			compareTo: "v1",
			maxLength: 200,
		});
		assert.ok(md.length <= 200 + 100); // some slack for the truncation note
		assert.ok(md.includes("changelog truncated"));
	});

	it("should render breaking changes section", () => {
		const breakingCommits = [
			{
				hash: "ddd4444",
				type: "feat",
				scope: null,
				subject: "new API",
				section: "✨ new features",
				author: "charlie",
				pr: 20,
				breaking: true,
			},
		];
		const md = renderChangelog(breakingCommits, "org/repo");
		assert.ok(md.includes("## ⚠️ breaking changes"));
		assert.ok(md.includes("new API"));
	});

	it("should include title when provided", () => {
		const md = renderChangelog(commits, "org/repo", {
			title: "v1.0.0",
		});
		assert.ok(md.startsWith("## v1.0.0"));
	});

	it("should return empty-ish for no commits", () => {
		const md = renderChangelog([], "org/repo");
		assert.equal(md, "");
	});
});

describe("typeToSection mapping", () => {
	it("should map feat to new features", () => {
		assert.equal(typeToSection.get("feat"), "✨ new features");
	});

	it("should map fix to bug fixes", () => {
		assert.equal(typeToSection.get("fix"), "🐛 bug fixes");
	});

	it("should map perf and refactor to improvements", () => {
		assert.equal(typeToSection.get("perf"), "🔧 improvements");
		assert.equal(typeToSection.get("refactor"), "🔧 improvements");
	});

	it("should map chore, style, deps to miscellaneous", () => {
		assert.equal(typeToSection.get("chore"), "🧹 miscellaneous");
		assert.equal(typeToSection.get("style"), "🧹 miscellaneous");
		assert.equal(typeToSection.get("deps"), "🧹 miscellaneous");
	});

	it("should map ci, ops, build, test to ops", () => {
		assert.equal(typeToSection.get("ci"), "♻️ ops");
		assert.equal(typeToSection.get("ops"), "♻️ ops");
		assert.equal(typeToSection.get("build"), "♻️ ops");
		assert.equal(typeToSection.get("test"), "♻️ ops");
	});

	it("should map docs to documentation", () => {
		assert.equal(typeToSection.get("docs"), "📚 documentation");
	});

	it("should map revert to reverts", () => {
		assert.equal(typeToSection.get("revert"), "⏪ reverts");
	});

	it("should not map unknown types", () => {
		assert.equal(typeToSection.get("unknown"), undefined);
	});
});
