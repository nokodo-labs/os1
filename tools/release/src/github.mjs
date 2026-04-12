// github operations - releases, PRs, labels.
// uses execFileSync with argument arrays to prevent shell injection.

import { execFileSync } from "node:child_process";

function ghEnv() {
	const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
	if (!token)
		throw new Error("GITHUB_TOKEN environment variable is required");
	return { ...process.env, GH_TOKEN: token };
}

function gh(args, opts = {}) {
	return execFileSync("gh", args, {
		encoding: "utf-8",
		env: ghEnv(),
		...opts,
	}).trim();
}

// create a GitHub release.
export function createRelease(
	repoSlug,
	tagName,
	body,
	{ prerelease = false } = {},
) {
	const name = prerelease ? `🚀 ${tagName} (pre-release)` : `🚀 ${tagName}`;
	const args = [
		"release",
		"create",
		tagName,
		"--repo",
		repoSlug,
		"--title",
		name,
		"--notes-file",
		"-",
	];
	if (prerelease) args.push("--prerelease");
	else args.push("--latest");

	execFileSync("gh", args, {
		encoding: "utf-8",
		input: body,
		env: ghEnv(),
	});
}

// find an existing release PR on a branch.
export function findReleasePR(repoSlug, branch, headBranch) {
	const head = headBranch || `release/${branch}`;
	try {
		const raw = gh([
			"pr",
			"list",
			"--repo",
			repoSlug,
			"--head",
			head,
			"--base",
			branch,
			"--state",
			"open",
			"--json",
			"number,labels",
			"--limit",
			"1",
		]);
		const prs = raw ? JSON.parse(raw) : [];
		if (prs.length > 0) return prs[0];
	} catch {
		// no PR found
	}
	return null;
}

// create or update a release PR.
export function upsertReleasePR(
	repoSlug,
	{ branch, title, body, labels = [], headBranch },
) {
	const head = headBranch || `release/${branch}`;
	const existing = findReleasePR(repoSlug, branch, head);

	// ensure labels exist before creating/editing the PR
	if (labels.length > 0) {
		ensureLabels(repoSlug, labels);
	}

	if (existing) {
		execFileSync(
			"gh",
			[
				"pr",
				"edit",
				String(existing.number),
				"--repo",
				repoSlug,
				"--title",
				title,
				"--body-file",
				"-",
			],
			{
				encoding: "utf-8",
				input: body,
				env: ghEnv(),
			},
		);

		// sync labels on existing PR
		if (labels.length > 0) {
			try {
				gh([
					"pr",
					"edit",
					String(existing.number),
					"--repo",
					repoSlug,
					"--add-label",
					labels.join(","),
				]);
			} catch {
				// best effort - labels might already be applied
			}
		}

		console.log(`updated release PR #${existing.number}`);
		return existing;
	}

	// create new PR
	const args = [
		"pr",
		"create",
		"--repo",
		repoSlug,
		"--head",
		head,
		"--base",
		branch,
		"--title",
		title,
		"--body-file",
		"-",
	];
	if (labels.length > 0) args.push("--label", labels.join(","));

	const result = execFileSync("gh", args, {
		encoding: "utf-8",
		input: body,
		env: ghEnv(),
	}).trim();

	const prNumber = result.match(/\/pull\/(\d+)/)?.[1];
	console.log(`created release PR ${result}`);

	return { number: prNumber ? parseInt(prNumber, 10) : null, url: result };
}

// ensure labels exist in the repo.
function ensureLabels(repoSlug, labels) {
	const LABEL_COLORS = {
		bot: "000000",
		release: "0e8a16",
		prerelease: "fbca04",
		backend: "3572A5",
		api: "3572A5",
		frontend: "f1e05a",
		console: "f1e05a",
	};

	for (const label of labels) {
		try {
			gh([
				"label",
				"create",
				label,
				"--repo",
				repoSlug,
				"--color",
				LABEL_COLORS[label] || "ededed",
				"--description",
				"managed by release tooling",
				"--force",
			]);
		} catch {
			// label may already exist
		}
	}
}

// find a merged release PR for the given branch.
// returns { number, title } or null.
export function findMergedReleasePR(repoSlug, branch) {
	const head = `release/${branch}`;
	try {
		const raw = gh([
			"pr",
			"list",
			"--repo",
			repoSlug,
			"--head",
			head,
			"--base",
			branch,
			"--state",
			"merged",
			"--json",
			"number,title",
			"--limit",
			"5",
		]);
		const prs = raw ? JSON.parse(raw) : [];
		return prs.length > 0 ? prs[0] : null;
	} catch {
		return null;
	}
}

// check if a GitHub release exists for a tag.
export function releaseExists(repoSlug, tagName) {
	try {
		gh([
			"release",
			"view",
			tagName,
			"--repo",
			repoSlug,
			"--json",
			"tagName",
		]);
		return true;
	} catch {
		return false;
	}
}

// close component PRs and delete their branches after root PR merge.
export function closeComponentPRs(repoSlug, branch, componentNames) {
	for (const name of componentNames) {
		const headBranch = `release--${name}/${branch}`;
		try {
			// find open component PR
			const raw = gh([
				"pr",
				"list",
				"--repo",
				repoSlug,
				"--head",
				headBranch,
				"--base",
				branch,
				"--state",
				"open",
				"--json",
				"number",
				"--limit",
				"1",
			]);
			const prs = raw ? JSON.parse(raw) : [];
			if (prs.length > 0) {
				gh([
					"pr",
					"close",
					String(prs[0].number),
					"--repo",
					repoSlug,
					"--delete-branch",
				]);
				console.log(`closed component PR #${prs[0].number} (${name})`);
			}
		} catch {
			// best effort - branch may already be deleted
		}
	}
}
