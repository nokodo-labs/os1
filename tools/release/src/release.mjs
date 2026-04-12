// release orchestrator - main entry point.
// runs on every push to dev/stable (via main.yml -> release.yml).
//
// auto-detects which mode to run:
//
// create-pr mode (default):
//   analyze commits since last tag, compute next version, create/update
//   a release PR targeting the current branch.
//
// tag-release mode (on merged release PR):
//   when a release PR is merged, the next push detects it via GitHub API.
//   the version is extracted from the PR title. if no tag exists yet for
//   that version, tags are created and a GitHub release is published.
//
// environment variables:
//   GITHUB_TOKEN - required for GitHub API
//   BRANCH - current branch name (dev or stable)
//   GITHUB_OUTPUT - path to write outputs (GitHub Actions)
//   RELEASE_AS - optional manual version override

import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
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
	getLatestComponentTag,
	getLatestTag,
	getRepoSlug,
	getSemverTags,
	tagExists,
} from "./git.mjs";
import {
	closeComponentPRs,
	createRelease,
	findMergedReleasePR,
	releaseExists,
	upsertReleasePR,
} from "./github.mjs";
import { writeVersion } from "./version.mjs";

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

// generate a map of component name -> version string for docker tagging.
function getComponentTagMap(version) {
	const map = {};
	for (const pkg of PACKAGES) {
		if (pkg.componentTag) {
			map[pkg.name] = version;
		}
	}
	return map;
}

// extract the version string from a release PR title.
// supports titles like "chore(release): prerelease OS1 v0.1.0-rc.0"
// or "chore(release): release OS1 v1.2.3".
// returns the version string if found, null otherwise.
export function extractVersionFromTitle(title) {
	const match = title?.match(/\bv(\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?)\s*$/);
	return match ? match[1] : null;
}

// main release logic.
function main() {
	const branch = process.env.BRANCH;
	if (!branch) {
		console.error("BRANCH environment variable is required");
		process.exit(1);
	}

	if (branch !== "dev" && branch !== "stable") {
		console.log(`branch "${branch}" is not a release branch, skipping.`);
		writeOutputs({ release_created: false });
		return;
	}

	const repoSlug = process.env.GITHUB_REPOSITORY || getRepoSlug();
	if (!repoSlug) {
		console.error("could not determine repo slug from git remote");
		process.exit(1);
	}

	console.log(`release process for branch: ${branch}`);
	console.log(`repository: ${repoSlug}`);

	// detect if a release PR was merged by querying GitHub API.
	// the version is extracted from the PR title, and tag existence
	// is the idempotency guard (prevents re-processing).
	const mergedPR = findMergedReleasePR(repoSlug, branch);
	if (mergedPR) {
		const version = extractVersionFromTitle(mergedPR.title);
		if (version && !tagExists(`v${version}`)) {
			console.log(
				`found merged release PR #${mergedPR.number}: v${version}, creating tags and GitHub release...`,
			);
			handleTagRelease(branch, repoSlug, version);
			return;
		}
		if (version) {
			console.log(
				`merged release PR #${mergedPR.number} already tagged (v${version}), skipping.`,
			);
		}
	}

	// no unprocessed merge - create/update release PR
	handleReleasePR(branch, repoSlug);
}

// handle a regular push: analyze commits and create/update release PR.
function handleReleasePR(branch, repoSlug) {
	const lastTag = getLatestTag();
	const highestTag = getHighestTag();
	console.log(`latest tag on branch: ${lastTag || "(none)"}`);
	console.log(`highest tag in repo: ${highestTag || "(none)"}`);

	// use the highest tag across the repo for version computation to prevent regression
	const currentVersion = highestTag ? semver.clean(highestTag) : null;
	const manualVersion = process.env.RELEASE_AS;

	// parse commits since the last tag reachable from this branch (for changelog)
	const commits = parseCommitRange(lastTag, "HEAD");
	console.log(
		`found ${commits.length} conventional commits since ${lastTag || "beginning"}`,
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
				`promoting RC ${currentVersion} to stable ${nextVersion}`,
			);
		} else {
			console.log("no releasable commits found, skipping.");
			writeOutputs({ release_created: false });
			return;
		}
	} else if (manualVersion) {
		nextVersion = semver.clean(manualVersion);
		if (!nextVersion) {
			console.error(`invalid manual version: ${manualVersion}`);
			process.exit(1);
		}
		if (currentVersion && !semver.gt(nextVersion, currentVersion)) {
			console.error(
				`manual version ${nextVersion} must be greater than current ${currentVersion}`,
			);
			process.exit(1);
		}
		console.log(`using manual version override: ${nextVersion}`);
	} else {
		const bumpType = recommendBump(commits);
		if (!bumpType) {
			console.log("no version-bumping commits found, skipping.");
			writeOutputs({ release_created: false });
			return;
		}

		console.log(`recommended bump: ${bumpType}`);

		if (branch === "dev") {
			nextVersion = computeNextRC(currentVersion, bumpType);
		} else {
			nextVersion = computeNextStable(currentVersion, bumpType);
		}
	}

	const tagName = `v${nextVersion}`;
	console.log(`next version: ${nextVersion} (tag: ${tagName})`);

	// check if tag already exists
	if (tagExists(tagName)) {
		console.log(`tag ${tagName} already exists, skipping.`);
		writeOutputs({ release_created: false });
		return;
	}

	// generate changelog (budget for PR body header/footer)
	const changelog = renderChangelog(commits, repoSlug, {
		compareFrom: lastTag || "",
		compareTo: branch,
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
		`> **version** \`${nextVersion}\` ${isPrerelease ? "*(release candidate)*" : ""} | **${commits.length}** commits`,
		"",
		changelog,
		"",
		"---",
		`- 🤖 *this PR was created by the [release automation](${repoUrl}/actions)*`,
		`- merging will create tag [\`${tagName}\`](${repoUrl}/releases/tag/${tagName}) and a GitHub ${isPrerelease ? "pre-release" : "release"}`,
	].join("\n");

	// create the release head branch (no version file changes on global release)
	const headBranch = `release/${branch}`;
	try {
		try {
			git("branch", "-D", headBranch);
		} catch {
			// branch doesn't exist, that's fine
		}
		git("checkout", "-b", headBranch);

		// placeholder commit so the PR branch differs from base.
		// version is extracted from PR title on merge, not from this commit.
		git(
			"commit",
			"--allow-empty",
			"-m",
			`chore(release): prepare OS1 v${nextVersion}`,
			"--no-verify",
		);

		git("push", "origin", headBranch, "--force");
		git("checkout", branch);
	} catch (err) {
		console.error(`failed to create release branch: ${err.message}`);
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

	// create/update per-component PRs
	createComponentPRs(branch, repoSlug, nextVersion, tagName, isPrerelease);

	writeOutputs({
		release_created: false, // pr created, not release yet
		pr_created: true,
		tag_name: tagName,
		version: nextVersion,
	});
}

// create separate tracking PRs for each component.
function createComponentPRs(
	branch,
	repoSlug,
	nextVersion,
	tagName,
	isPrerelease,
) {
	const repoUrl = `https://github.com/${repoSlug}`;
	const componentPkgs = PACKAGES.filter((p) => p.componentTag);

	for (const pkg of componentPkgs) {
		const componentBranch = `release--${pkg.name}/${branch}`;
		const componentTag = `${pkg.name}-v${nextVersion}`;
		const componentLabels = [
			...(isPrerelease ? PRERELEASE_LABELS : RELEASE_LABELS),
			...(pkg.extraLabels || []),
		];
		const componentTitle = isPrerelease
			? `chore(release): prerelease ${pkg.name} v${nextVersion}`
			: `chore(release): release ${pkg.name} v${nextVersion}`;

		// generate component-scoped changelog using the component's own last tag
		const lastComponentTag = getLatestComponentTag(pkg.name);
		const componentCommits = parseCommitRange(lastComponentTag, "HEAD", [
			pkg.path,
		]);
		const componentChangelog = renderChangelog(componentCommits, repoSlug, {
			compareFrom: lastComponentTag || "",
			compareTo: branch,
			maxLength: 50000,
		});

		// link to previous release if one exists, otherwise note first release
		const prevReleaseLink = lastComponentTag
			? `- 📦 previous release: [\`${lastComponentTag}\`](${repoUrl}/releases/tag/${lastComponentTag})`
			: "- 📦 *first release for this component*";

		const componentBody = [
			isPrerelease ? "## 🚀 pre-release" : "## 🚀 release",
			"",
			`> **component** \`${pkg.name}\` **version** \`${nextVersion}\` | **${componentCommits.length}** commits`,
			"",
			componentChangelog,
			"",
			"---",
			prevReleaseLink,
			`- 🤖 *this PR was created by the [release automation](${repoUrl}/actions)*`,
		].join("\n");

		try {
			// create or reset the component branch
			try {
				git("branch", "-D", componentBranch);
			} catch {
				// ok
			}
			git("checkout", "-b", componentBranch);

			// bump this component's version file (if it has one)
			const versionFile = writeVersion(pkg, nextVersion);
			if (versionFile) {
				git("add", versionFile);
				// skip if version file didn't actually change
				try {
					git("diff", "--cached", "--quiet");
					console.log(
						`no version changes for ${pkg.name}, skipping component PR`,
					);
					git("checkout", branch);
					continue;
				} catch {
					// exit 1 = there are staged changes, proceed
				}
			}

			const commitArgs = versionFile
				? [
						"commit",
						"-m",
						`chore(release): bump ${pkg.name} version to ${nextVersion}`,
						"--no-verify",
					]
				: [
						"commit",
						"--allow-empty",
						"-m",
						`chore(release): ${pkg.name} ${nextVersion}`,
						"--no-verify",
					];
			git(...commitArgs);

			git("push", "origin", componentBranch, "--force");
			git("checkout", branch);

			upsertReleasePR(repoSlug, {
				branch,
				title: componentTitle,
				body: componentBody,
				labels: componentLabels,
				headBranch: componentBranch,
			});
		} catch (err) {
			console.error(
				`failed to create component PR for ${pkg.name}: ${err.message}`,
			);
			try {
				git("checkout", branch);
			} catch {
				// best effort
			}
		}
	}
}

// handle a merged release: create tags and GitHub release.
// version comes from the merged release PR title.
function handleTagRelease(branch, repoSlug, version) {
	const tagName = `v${version}`;
	const isPrerelease = branch === "dev";

	console.log(`creating release for version ${version} (tag: ${tagName})`);

	// check if a GitHub release already exists (defensive)
	if (releaseExists(repoSlug, tagName)) {
		console.log(`GitHub release ${tagName} already exists, skipping.`);
		writeOutputs({ release_created: false });
		return;
	}

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
		git("tag", "-a", tagName, "-m", `release ${tagName}`);
		console.log(`created tag: ${tagName}`);
	}

	// create component tags
	const componentTags = getComponentTags(version);
	for (const ct of componentTags) {
		if (!tagExists(ct)) {
			git("tag", "-a", ct, "-m", `release ${ct}`);
			console.log(`created component tag: ${ct}`);
		}
	}

	// push all tags
	git("push", "origin", "--tags");
	console.log("pushed tags to origin");

	// create GitHub release
	createRelease(repoSlug, tagName, changelog, {
		prerelease: isPrerelease,
	});
	console.log(
		`created GitHub ${isPrerelease ? "pre-release" : "release"}: ${tagName}`,
	);

	// close component tracking PRs with release comments
	const componentPkgs = PACKAGES.filter((p) => p.componentTag);
	const componentNames = componentPkgs.map((p) => p.name);
	const componentTagMap = {};
	for (const pkg of componentPkgs) {
		componentTagMap[pkg.name] = `${pkg.name}-v${version}`;
	}
	closeComponentPRs(repoSlug, branch, componentNames, componentTagMap);

	writeOutputs({
		release_created: true,
		tag_name: tagName,
		version,
		component_tags: JSON.stringify(getComponentTagMap(version)),
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
		console.log(`output: ${key}=${value}`);
	}
}

// only run main when executed directly (not when imported for tests).
const isDirectRun =
	process.argv[1] &&
	import.meta.url === pathToFileURL(resolve(process.argv[1])).href;
if (isDirectRun) {
	try {
		main();
	} catch (err) {
		console.error("release failed:", err);
		process.exit(1);
	}
}
