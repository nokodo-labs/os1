// shared configuration for release tooling.
// single source of truth for changelog categories, package definitions, and constants.

export const PRERELEASE_ID = "rc";

// conventional commit type -> changelog section mapping.
// order determines display order in release notes.
export const CHANGELOG_SECTIONS = [
	{ type: "feat", section: "✨ new features" },
	{ type: "fix", section: "🐛 bug fixes" },
	{ type: "perf", section: "🔧 improvements" },
	{ type: "refactor", section: "🔧 improvements" },
	{ type: "chore", section: "🧹 miscellaneous" },
	{ type: "style", section: "🧹 miscellaneous" },
	{ type: "deps", section: "🧹 miscellaneous" },
	{ type: "ci", section: "♻️ ops" },
	{ type: "ops", section: "♻️ ops" },
	{ type: "build", section: "♻️ ops" },
	{ type: "test", section: "♻️ ops" },
	{ type: "docs", section: "📚 documentation" },
	{ type: "revert", section: "⏪ reverts" },
];

// unique section names in display order.
export const SECTION_ORDER = [
	"✨ new features",
	"🐛 bug fixes",
	"🔧 improvements",
	"🧹 miscellaneous",
	"♻️ ops",
	"📚 documentation",
	"⏪ reverts",
];

// packages tracked in this monorepo.
// - path: relative to repo root
// - name: component name used in tags (e.g., library-v0.0.2)
// - releaseType: determines how version files are updated
// - componentTag: whether to create a separate component tag
export const PACKAGES = [
	{ path: ".", name: "os1", releaseType: "simple", componentTag: false },
	{
		path: "backend/nokodo_ai",
		name: "library",
		releaseType: "python",
		componentTag: true,
		extraLabels: ["backend"],
		versionDir: "backend",
	},
	{
		path: "backend/api",
		name: "api",
		releaseType: "none",
		componentTag: true,
		extraLabels: ["api"],
	},
	{
		path: "frontend",
		name: "frontend",
		releaseType: "node",
		componentTag: true,
		extraLabels: ["frontend"],
	},
	{
		path: "console",
		name: "console",
		releaseType: "node",
		componentTag: true,
		extraLabels: ["console"],
	},
];

// commit types that trigger a version bump.
export const BUMP_TYPES = ["feat", "fix", "perf", "refactor", "revert"];

// commit types that trigger a breaking change bump regardless.
export const BREAKING_KEYWORDS = ["BREAKING CHANGE", "BREAKING-CHANGE"];

// labels applied to release PRs.
export const RELEASE_LABELS = ["bot", "release", "release: pending"];
export const PRERELEASE_LABELS = [
	"bot",
	"release",
	"prerelease",
	"release: pending",
];
// label swapped in after release is tagged.
export const RELEASE_TAGGED_LABEL = "release: tagged";
