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
	title,
	body,
	{ prerelease = false, latest = false } = {},
) {
	const args = [
		"release",
		"create",
		tagName,
		"--repo",
		repoSlug,
		"--title",
		title,
		"--notes-file",
		"-",
	];
	if (prerelease) args.push("--prerelease");
	if (latest) args.push("--latest");
	else args.push("--latest=false");

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
	} catch (err) {
		if (err?.status !== 1) throw err;
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

		// sync labels on existing PR - release:pending is critical for detection
		if (labels.length > 0) {
			gh([
				"pr",
				"edit",
				String(existing.number),
				"--repo",
				repoSlug,
				"--add-label",
				labels.join(","),
			]);
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
		"release:pending": "c2e0c6",
		prerelease: "fbca04",
		backend: "3572A5",
		api: "3572A5",
		frontend: "f1e05a",
		console: "f1e05a",
	};

	for (const label of labels) {
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
	}
}

// find merged release PRs that haven't been processed yet.
// uses the release:pending label to identify unprocessed PRs.
// returns an array of { number, title }.
export function findPendingReleasePRs(repoSlug, branch) {
	const raw = gh([
		"pr",
		"list",
		"--repo",
		repoSlug,
		"--base",
		branch,
		"--state",
		"merged",
		"--label",
		"release:pending",
		"--json",
		"number,title",
	]);
	return raw ? JSON.parse(raw) : [];
}

// remove a label from a PR.
export function removePRLabel(repoSlug, prNumber, label) {
	gh([
		"pr",
		"edit",
		String(prNumber),
		"--repo",
		repoSlug,
		"--remove-label",
		label,
	]);
}

// delete a remote branch.
export function deleteBranch(repoSlug, branchName) {
	try {
		gh([
			"api",
			"-X",
			"DELETE",
			`repos/${repoSlug}/git/refs/heads/${branchName}`,
		]);
		console.log(`deleted branch: ${branchName}`);
	} catch (err) {
		// branch may already be deleted
		if (err?.status !== 1) throw err;
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
	} catch (err) {
		if (err?.status !== 1) throw err;
		return false;
	}
}

// add a comment to a PR.
export function addPRComment(repoSlug, prNumber, body) {
	execFileSync(
		"gh",
		[
			"pr",
			"comment",
			String(prNumber),
			"--repo",
			repoSlug,
			"--body-file",
			"-",
		],
		{
			encoding: "utf-8",
			input: body,
			env: ghEnv(),
		},
	);
}

// close component PRs and delete their branches after root PR merge.
// componentTags: optional map of { name: tagString } for release comments.
export function closeComponentPRs(
	repoSlug,
	branch,
	componentNames,
	componentTags = {},
) {
	const repoUrl = `https://github.com/${repoSlug}`;
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
				// add release comment before closing
				const tag = componentTags[name];
				if (tag) {
					try {
						addPRComment(
							repoSlug,
							prs[0].number,
							`🏷️ released as [\`${tag}\`](${repoUrl}/releases/tag/${tag})`,
						);
					} catch (err) {
						// comment is non-critical, but only swallow expected errors
						if (err?.status !== 1) throw err;
					}
				}
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
		} catch (err) {
			// PR or branch may already be deleted/closed
			if (err?.status !== 1) throw err;
		}
	}
}
