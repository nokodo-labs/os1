// release orchestrator - main entry point.
// creates/updates release PRs with version bumps, changelogs, and tags.
//
// flow:
//   1. determine commits since last tag
//   2. compute next version (RC for dev, stable for stable)
//   3. create/update release PR with version bumps and changelog
//
// when a release PR is merged (detected by checking if HEAD is a merge of a release branch):
//   1. create git tag(s)
//   2. create GitHub release
//
// environment variables:
//   GITHUB_TOKEN - required for GitHub API
//   BRANCH - current branch name (dev or stable)
//   GITHUB_OUTPUT - path to write outputs (GitHub Actions)
//   RELEASE_AS - optional manual version override

import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import semver from "semver";
import {
	parseCommitRange,
	recommendBump,
	renderChangelog,
} from "./changelog.mjs";
import {
	PACKAGES,
	PRERELEASE_ID,
	PRERELEASE_LABELS,
	RELEASE_LABELS,
} from "./config.mjs";
import {
	getHighestTag,
	getLatestTag,
	getRepoSlug,
	getSemverTags,
	tagExists,
} from "./git.mjs";
import {
	createRelease,
	findMergedReleasePR,
	swapReleaseLabel,
	upsertReleasePR,
} from "./github.mjs";
import { readVersion, updateAllVersions } from "./version.mjs";

function git(...args) {
	return execFileSync("git", args, {
		encoding: "utf-8",
		stdio: ["pipe", "pipe", "pipe"],
	}).trim();
}

// compute the next RC version for the dev branch.
// compares against the last stable tag to detect bump escalation.
function computeNextRC(currentVersion, bumpType) {
	if (!currentVersion) {
		// no previous version at all, start at 0.0.1-rc.0
		return `0.0.1-${PRERELEASE_ID}.0`;
	}

	const pre = semver.prerelease(currentVersion);

	if (pre && pre[0] === PRERELEASE_ID) {
		// already in an RC series - check if bump level escalates the base
		const currentBase = `${semver.major(currentVersion)}.${semver.minor(currentVersion)}.${semver.patch(currentVersion)}`;

		// find the last stable tag to compare against
		const lastStable = getSemverTags().find((t) => !semver.prerelease(t));
		const stableVersion = lastStable ? semver.clean(lastStable) : "0.0.0";
		const escalatedBase = semver.inc(stableVersion, bumpType);

		if (semver.gt(escalatedBase, currentBase)) {
			// bump type exceeds current RC base, start new RC series
			return `${escalatedBase}-${PRERELEASE_ID}.0`;
		}

		// same or lower bump level, just increment RC number
		return semver.inc(currentVersion, "prerelease", PRERELEASE_ID);
	}

	// not an RC, start new RC series
	const newBase = semver.inc(currentVersion, bumpType);
	return `${newBase}-${PRERELEASE_ID}.0`;
}

// compute the next stable version.
function computeNextStable(currentVersion, bumpType) {
	if (!currentVersion) {
		return "0.0.1";
	}

	const pre = semver.prerelease(currentVersion);

	if (pre) {
		// strip prerelease to get the stable version
		return `${semver.major(currentVersion)}.${semver.minor(currentVersion)}.${semver.patch(currentVersion)}`;
	}

	// already stable, bump normally
	return semver.inc(currentVersion, bumpType);
}

// generate component tags for a given root version.
function getComponentTags(version) {
	const tags = [];
	for (const pkg of PACKAGES) {
		if (pkg.componentTag) {
			tags.push(`${pkg.name}-v${version}`);
		}
	}
	return tags;
}

// check if the current HEAD was merged from a release PR.
// returns the PR number if it was, null otherwise.
function getReleasePRMerge(branch, repoSlug) {
	const pr = findMergedReleasePR(repoSlug, branch);
	if (!pr) return null;

	// compare the merge commit SHA to the current HEAD
	const headSha = git("rev-parse", "HEAD");
	const mergeSha = pr.mergeCommit?.oid;
	if (mergeSha && headSha === mergeSha) return pr.number;

	// fallback: check commit message
	try {
		const msg = git("log", "-1", "--format=%s", "HEAD");
		if (msg.includes(`release/${branch}`)) return pr.number;
	} catch {
		// ignore
	}
	return null;
}

// main release logic.
function main() {
	const branch = process.env.BRANCH;
	if (!branch) {
		console.error("BRANCH environment variable is required");
		process.exit(1);
	}

	if (branch !== "dev" && branch !== "stable") {
		console.log(`Branch "${branch}" is not a release branch, skipping.`);
		writeOutputs({ release_created: false });
		return;
	}

	const repoSlug = process.env.GITHUB_REPOSITORY || getRepoSlug();
	if (!repoSlug) {
		console.error("Could not determine repo slug from git remote");
		process.exit(1);
	}

	console.log(`Release process for branch: ${branch}`);
	console.log(`Repository: ${repoSlug}`);

	// check if this is a merged release PR
	const mergedPRNumber = getReleasePRMerge(branch, repoSlug);
	if (mergedPRNumber) {
		console.log(
			`Detected merged release PR #${mergedPRNumber}, creating tags and GitHub release...`,
		);
		handleMergedReleasePR(branch, repoSlug, mergedPRNumber);
		return;
	}

	// regular push - create/update release PR
	handleReleasePR(branch, repoSlug);
}

// handle a regular push: analyze commits and create/update release PR.
function handleReleasePR(branch, repoSlug) {
	const lastTag = getLatestTag();
	const highestTag = getHighestTag();
	console.log(`Latest tag on branch: ${lastTag || "(none)"}`);
	console.log(`Highest tag in repo: ${highestTag || "(none)"}`);

	// use the highest tag across the repo for version computation to prevent regression
	const currentVersion = highestTag ? semver.clean(highestTag) : null;
	const manualVersion = process.env.RELEASE_AS;

	// parse commits since the last tag reachable from this branch (for changelog)
	const commits = parseCommitRange(lastTag, "HEAD");
	console.log(
		`Found ${commits.length} conventional commits since ${lastTag || "beginning"}`,
	);

	let nextVersion;
	if (commits.length === 0 && !manualVersion) {
		// check if this is a promotion: stable branch with a prerelease as latest tag
		if (
			branch === "stable" &&
			currentVersion &&
			semver.prerelease(currentVersion)
		) {
			nextVersion = computeNextStable(currentVersion, "patch");
			console.log(
				`Promoting RC ${currentVersion} to stable ${nextVersion}`,
			);
		} else {
			console.log("No releasable commits found, skipping.");
			writeOutputs({ release_created: false });
			return;
		}
	} else if (manualVersion) {
		nextVersion = semver.clean(manualVersion);
		if (!nextVersion) {
			console.error(`Invalid manual version: ${manualVersion}`);
			process.exit(1);
		}
		if (currentVersion && !semver.gt(nextVersion, currentVersion)) {
			console.error(
				`Manual version ${nextVersion} must be greater than current ${currentVersion}`,
			);
			process.exit(1);
		}
		console.log(`Using manual version override: ${nextVersion}`);
	} else {
		const bumpType = recommendBump(commits);
		if (!bumpType) {
			console.log("No version-bumping commits found, skipping.");
			writeOutputs({ release_created: false });
			return;
		}

		console.log(`Recommended bump: ${bumpType}`);

		if (branch === "dev") {
			nextVersion = computeNextRC(currentVersion, bumpType);
		} else {
			nextVersion = computeNextStable(currentVersion, bumpType);
		}
	}

	const tagName = `v${nextVersion}`;
	console.log(`Next version: ${nextVersion} (tag: ${tagName})`);

	// check if tag already exists
	if (tagExists(tagName)) {
		console.log(`Tag ${tagName} already exists, skipping.`);
		writeOutputs({ release_created: false });
		return;
	}

	// generate changelog (budget for PR body header/footer)
	const changelog = renderChangelog(commits, repoSlug, {
		compareFrom: lastTag || "",
		compareTo: tagName,
		maxLength: 60000,
	});

	// create/update release PR
	const isPrerelease = branch === "dev";
	const labels = isPrerelease ? PRERELEASE_LABELS : RELEASE_LABELS;
	const prTitle = isPrerelease
		? `chore(release): prerelease OS1 v${nextVersion}`
		: `chore(release): release OS1 v${nextVersion}`;

	const repoUrl = `https://github.com/${repoSlug}`;
	const prBody = [
		isPrerelease ? "## 🚀 pre-release" : "## 🚀 release",
		"",
		`> **version** \`${nextVersion}\` ${isPrerelease ? "*(release candidate)*" : ""}`,
		"",
		changelog,
		"",
		"---",
		`- 🤖 *this PR was created by the [release automation](${repoUrl}/actions)*`,
		`- merging will create tag [\`${tagName}\`](${repoUrl}/releases/tag/${tagName}) and a GitHub ${isPrerelease ? "pre-release" : "release"}`,
	].join("\n");

	// create the release head branch and push version changes
	const headBranch = `release/${branch}`;
	try {
		// create or reset the release branch from current branch
		try {
			git("branch", "-D", headBranch);
		} catch {
			// branch doesn't exist, that's fine
		}
		git("checkout", "-b", headBranch);

		// update version files
		const changedFiles = updateAllVersions(nextVersion);
		console.log(`Updated version files: ${changedFiles.length} files`);

		if (changedFiles.length > 0) {
			for (const f of changedFiles) {
				git("add", f);
			}
			git(
				"commit",
				"-m",
				`chore(release): bump version to ${nextVersion}`,
				"--no-verify",
			);
		}

		// push the branch
		git("push", "origin", headBranch, "--force");

		// switch back
		git("checkout", branch);
	} catch (err) {
		console.error(`Failed to create release branch: ${err.message}`);
		try {
			git("checkout", branch);
		} catch {
			// best effort
		}
		process.exit(1);
	}

	// create/update the PR
	upsertReleasePR(repoSlug, {
		branch,
		title: prTitle,
		body: prBody,
		labels,
		headBranch,
	});

	writeOutputs({
		release_created: false, // pr created, not release yet
		pr_created: true,
		tag_name: tagName,
		version: nextVersion,
	});
}

// handle a merged release PR: create tags and GitHub release.
function handleMergedReleasePR(branch, repoSlug, prNumber) {
	// try packages with version files until one succeeds
	const versionPkg = PACKAGES.find(
		(p) => p.releaseType === "node" || p.releaseType === "python",
	);
	const version = versionPkg ? readVersion(versionPkg) : null;

	if (!version) {
		console.error("Could not read version from package files after merge");
		process.exit(1);
	}

	const tagName = `v${version}`;
	const isPrerelease = branch === "dev";

	console.log(`Creating release for version ${version} (tag: ${tagName})`);

	// generate changelog BEFORE creating tags (so getLatestTag finds the previous one)
	const lastStableTag = getSemverTags().find(
		(t) => !semver.prerelease(t) && t !== tagName,
	);
	const prevTag = isPrerelease
		? getLatestTag() // for RC, compare to previous tag
		: lastStableTag; // for stable, compare to last stable

	const commits = parseCommitRange(prevTag, "HEAD");
	const changelog = renderChangelog(commits, repoSlug, {
		compareFrom: prevTag || "",
		compareTo: tagName,
	});

	// create root tag
	if (!tagExists(tagName)) {
		git("tag", "-a", tagName, "-m", `Release ${tagName}`);
		console.log(`Created tag: ${tagName}`);
	}

	// create component tags
	const componentTags = getComponentTags(version);
	for (const ct of componentTags) {
		if (!tagExists(ct)) {
			git("tag", "-a", ct, "-m", `Release ${ct}`);
			console.log(`Created component tag: ${ct}`);
		}
	}

	// push all tags
	git("push", "origin", "--tags");
	console.log("Pushed tags to origin");

	// create GitHub release
	createRelease(repoSlug, tagName, changelog, {
		prerelease: isPrerelease,
	});
	console.log(
		`Created GitHub ${isPrerelease ? "pre-release" : "release"}: ${tagName}`,
	);

	// swap release: pending -> release: tagged
	if (prNumber) {
		swapReleaseLabel(repoSlug, prNumber);
	}

	writeOutputs({
		release_created: true,
		tag_name: tagName,
		version,
	});
}

function writeOutputs(outputs) {
	const outputFile = process.env.GITHUB_OUTPUT;
	if (outputFile) {
		for (const [key, value] of Object.entries(outputs)) {
			appendFileSync(outputFile, `${key}=${value}\n`);
		}
	}

	for (const [key, value] of Object.entries(outputs)) {
		console.log(`Output: ${key}=${value}`);
	}
}

try {
	main();
} catch (err) {
	console.error("Release failed:", err);
	process.exit(1);
}
