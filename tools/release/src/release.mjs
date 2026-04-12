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
	getComponentSemverTags,
	getHighestTag,
	getLatestComponentTag,
	getLatestTag,
	getRepoSlug,
	getSemverTags,
	tagExists,
} from "./git.mjs";
import {
	addPRComment,
	createRelease,
	deleteBranch,
	findPendingReleasePRs,
	releaseExists,
	removePRLabel,
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
// stableVersion: explicit stable version for escalation check (used by components).
//                when null, falls back to root tag lookup.
function computeNextRC(currentVersion, bumpType, stableVersion = null) {
	if (!currentVersion) {
		// no previous version at all, start at 0.0.1-rc.0
		return `0.0.1-${PRERELEASE_ID}.0`;
	}

	const pre = semver.prerelease(currentVersion);

	if (pre && pre[0] === PRERELEASE_ID) {
		// already in an RC series - check if bump level escalates the base
		const currentBase = `${semver.major(currentVersion)}.${semver.minor(currentVersion)}.${semver.patch(currentVersion)}`;

		// find the last stable version to compare against
		if (stableVersion === null) {
			const lastStable = getSemverTags().find(
				(t) => !semver.prerelease(t),
			);
			stableVersion = lastStable ? semver.clean(lastStable) : "0.0.0";
		}
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

// extract the version string and package name from a release PR title.
// supports titles like "chore(release): prerelease OS1 v0.1.0-rc.0"
// or "chore(release): release api v1.2.3".
// returns { name, version } if found, null otherwise.
export function extractReleaseFromTitle(title) {
	const match = title?.match(
		/\b(\S+)\s+v(\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?)\s*$/,
	);
	return match ? { name: match[1], version: match[2] } : null;
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

	// find merged release PRs that still have the release:pending label.
	// tag + release existence determines what work remains.
	// processes all pending PRs (root and component) in a single run.
	const pendingPRs = findPendingReleasePRs(repoSlug, branch);
	const componentTags = {};
	let anyReleased = false;

	for (const pr of pendingPRs) {
		const release = extractReleaseFromTitle(pr.title);
		if (!release) continue;

		const { name, version } = release;
		const pkg = PACKAGES.find((p) => p.name === name);
		const isRoot = !pkg || !pkg.componentTag;
		const tagName = isRoot ? `v${version}` : `${name}-v${version}`;

		const tagged = tagExists(tagName);
		const released = releaseExists(repoSlug, tagName);

		if (tagged && released) {
			console.log(
				`PR #${pr.number} (${tagName}) fully released, removing pending label.`,
			);
			removePRLabel(repoSlug, pr.number, "release:pending");
			continue;
		}

		console.log(
			`found pending release PR #${pr.number}: ${tagName} (tag: ${tagged ? "yes" : "no"}, release: ${released ? "yes" : "no"})`,
		);

		if (isRoot) {
			handleTagRelease(branch, repoSlug, version, pr.number);
		} else {
			const result = handleComponentTagRelease(
				branch,
				repoSlug,
				pkg,
				version,
				pr.number,
			);
			Object.assign(componentTags, result.componentTags);
		}
		anyReleased = true;
	}

	if (anyReleased) {
		writeOutputs({
			release_created: true,
			component_tags: JSON.stringify(componentTags),
		});
		return;
	}

	// no unprocessed merge - create/update release PRs
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
		`- 🔀 **merging** this PR will create tag [\`${tagName}\`](${repoUrl}/releases/tag/${tagName}) and publish a GitHub ${isPrerelease ? "pre-release" : "release"}`,
		`- 📦 components release independently via their own PRs`,
		`- 🤖 *created by [release automation](${repoUrl}/actions)*`,
	].join("\n");

	// create the release head branch
	const headBranch = `release/${branch}`;
	try {
		try {
			git("branch", "-D", headBranch);
		} catch {
			// branch doesn't exist, that's fine
		}
		git("checkout", "-b", headBranch);

		// write the root version file so the PR has a real diff
		const rootPkg = PACKAGES.find((p) => p.path === ".");
		const versionFile = writeVersion(rootPkg, nextVersion);
		if (versionFile) {
			git("add", versionFile);
			git(
				"commit",
				"-m",
				`chore(release): prepare OS1 v${nextVersion}`,
				"--no-verify",
			);
		} else {
			git(
				"commit",
				"--allow-empty",
				"-m",
				`chore(release): prepare OS1 v${nextVersion}`,
				"--no-verify",
			);
		}

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
	const rootPR = upsertReleasePR(repoSlug, {
		branch,
		title: prTitle,
		body: prBody,
		labels,
		headBranch,
	});

	// create/update per-component PRs (each with independent version)
	createComponentPRs(branch, repoSlug, isPrerelease, rootPR);

	writeOutputs({
		release_created: false, // pr created, not release yet
		pr_created: true,
		tag_name: tagName,
		version: nextVersion,
	});
}

// create independent release PRs for each component.
// each component computes its own version from its own commit history.
function createComponentPRs(branch, repoSlug, isPrerelease, rootPR) {
	const repoUrl = `https://github.com/${repoSlug}`;
	const componentPkgs = PACKAGES.filter((p) => p.componentTag);

	for (const pkg of componentPkgs) {
		// compute component version independently
		const prefix = `${pkg.name}-v`;
		const lastComponentTag = getLatestComponentTag(pkg.name);
		const componentTags = getComponentSemverTags(pkg.name);
		const highestComponentTag =
			componentTags.length > 0 ? componentTags[0] : null;
		const currentVersion = highestComponentTag
			? highestComponentTag.slice(prefix.length)
			: null;

		const componentCommits = parseCommitRange(lastComponentTag, "HEAD", [
			pkg.path,
		]);

		let nextVersion;
		if (componentCommits.length === 0) {
			// check promotion case: stable branch with prerelease component tag
			if (
				branch === "stable" &&
				currentVersion &&
				semver.prerelease(currentVersion)
			) {
				nextVersion = computeNextStable(currentVersion, "patch");
				console.log(
					`promoting ${pkg.name} RC ${currentVersion} to stable ${nextVersion}`,
				);
			} else {
				console.log(`no releasable commits for ${pkg.name}, skipping.`);
				continue;
			}
		} else {
			const bumpType = recommendBump(componentCommits);
			if (!bumpType) {
				console.log(
					`no version-bumping commits for ${pkg.name}, skipping.`,
				);
				continue;
			}

			if (branch === "dev") {
				// find last stable component version for RC escalation
				const lastStableComponentTag = componentTags.find((t) => {
					const ver = t.slice(prefix.length);
					return !semver.prerelease(ver);
				});
				const stableVersion = lastStableComponentTag
					? semver.clean(lastStableComponentTag.slice(prefix.length))
					: "0.0.0";
				nextVersion = computeNextRC(
					currentVersion,
					bumpType,
					stableVersion,
				);
			} else {
				nextVersion = computeNextStable(currentVersion, bumpType);
			}
		}

		const componentTag = `${pkg.name}-v${nextVersion}`;
		if (tagExists(componentTag)) {
			console.log(
				`component tag ${componentTag} already exists, skipping.`,
			);
			continue;
		}

		const componentBranch = `release--${pkg.name}/${branch}`;
		const componentLabels = [
			...(isPrerelease ? PRERELEASE_LABELS : RELEASE_LABELS),
			...(pkg.extraLabels || []),
		];
		const componentTitle = isPrerelease
			? `chore(release): prerelease ${pkg.name} v${nextVersion}`
			: `chore(release): release ${pkg.name} v${nextVersion}`;

		const componentChangelog = renderChangelog(componentCommits, repoSlug, {
			compareFrom: lastComponentTag || "",
			compareTo: branch,
			maxLength: 50000,
		});

		const prevReleaseLink = lastComponentTag
			? `- 📦 previous release: [\`${lastComponentTag}\`](${repoUrl}/releases/tag/${lastComponentTag})`
			: "- 📦 *first release for this component*";
		const rootPRLink = rootPR?.number
			? `- 🔗 root release PR #${rootPR.number}`
			: "";

		const componentBody = [
			isPrerelease ? "## 🚀 pre-release" : "## 🚀 release",
			"",
			`> **component** \`${pkg.name}\` **version** \`${nextVersion}\` | **${componentCommits.length}** commits`,
			"",
			componentChangelog,
			"",
			"---",
			`- 🔀 **merging** this PR will create tag [\`${componentTag}\`](${repoUrl}/releases/tag/${componentTag}) and publish a GitHub ${isPrerelease ? "pre-release" : "release"}`,
			prevReleaseLink,
			rootPRLink,
			`- 🤖 *created by [release automation](${repoUrl}/actions)*`,
		]
			.filter(Boolean)
			.join("\n");

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

// handle a merged root release PR: create root tag and GitHub release.
// components are released independently via their own PRs.
function handleTagRelease(branch, repoSlug, version, prNumber) {
	const tagName = `v${version}`;
	const isPrerelease = branch === "dev";

	console.log(
		`creating root release for version ${version} (tag: ${tagName})`,
	);

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

	// create root tag if missing
	if (!tagExists(tagName)) {
		git("tag", "-a", tagName, "-m", `release ${tagName}`);
		console.log(`created tag: ${tagName}`);
	} else {
		console.log(`tag ${tagName} already exists, skipping tag creation`);
	}

	// push tags
	git("push", "origin", "--tags");
	console.log("pushed tags to origin");

	// create GitHub release if missing
	if (!releaseExists(repoSlug, tagName)) {
		const repoUrl = `https://github.com/${repoSlug}`;
		const footer = `\n\n---\n🤖 *released by [release automation](${repoUrl}/actions)*`;
		createRelease(repoSlug, tagName, `v${version}`, changelog + footer, {
			prerelease: isPrerelease,
			latest: !isPrerelease,
		});
		console.log(
			`created GitHub ${isPrerelease ? "pre-release" : "release"}: ${tagName}`,
		);
	} else {
		console.log(
			`GitHub release ${tagName} already exists, skipping release creation`,
		);
	}

	// remove release:pending label now that processing is complete
	if (prNumber) {
		removePRLabel(repoSlug, prNumber, "release:pending");
		console.log(`removed release:pending label from PR #${prNumber}`);

		// leave a comment on the merged PR
		const repoUrl = `https://github.com/${repoSlug}`;
		addPRComment(
			repoSlug,
			prNumber,
			`🏷️ released as [\`${tagName}\`](${repoUrl}/releases/tag/${tagName})`,
		);

		// delete the release branch
		deleteBranch(repoSlug, `release/${branch}`);
	}

	writeOutputs({
		release_created: true,
		tag_name: tagName,
		version,
	});
}

// handle a merged component release PR: create component tag and GitHub release.
function handleComponentTagRelease(branch, repoSlug, pkg, version, prNumber) {
	const tagName = `${pkg.name}-v${version}`;
	const isPrerelease = branch === "dev";

	console.log(
		`creating ${pkg.name} release for version ${version} (tag: ${tagName})`,
	);

	// generate changelog from component-scoped commits
	const lastComponentTag = getLatestComponentTag(pkg.name);
	const commits = parseCommitRange(lastComponentTag, "HEAD", [pkg.path]);
	const changelog = renderChangelog(commits, repoSlug, {
		compareFrom: lastComponentTag || "",
		compareTo: tagName,
	});

	// create component tag if missing
	if (!tagExists(tagName)) {
		git("tag", "-a", tagName, "-m", `release ${tagName}`);
		console.log(`created component tag: ${tagName}`);
	} else {
		console.log(`tag ${tagName} already exists, skipping tag creation`);
	}

	// push tags
	git("push", "origin", "--tags");
	console.log("pushed tags to origin");

	// create GitHub release if missing
	if (!releaseExists(repoSlug, tagName)) {
		const repoUrl = `https://github.com/${repoSlug}`;
		const footer = `\n\n---\n\u{1F916} *released by [release automation](${repoUrl}/actions)*`;
		createRelease(
			repoSlug,
			tagName,
			`${pkg.name}: v${version}`,
			changelog + footer,
			{
				prerelease: isPrerelease,
				latest: false,
			},
		);
		console.log(
			`created GitHub ${isPrerelease ? "pre-release" : "release"}: ${tagName}`,
		);
	} else {
		console.log(
			`GitHub release ${tagName} already exists, skipping release creation`,
		);
	}

	// remove release:pending label now that processing is complete
	if (prNumber) {
		removePRLabel(repoSlug, prNumber, "release:pending");
		console.log(`removed release:pending label from PR #${prNumber}`);

		// leave a comment on the merged PR
		const repoUrl = `https://github.com/${repoSlug}`;
		addPRComment(
			repoSlug,
			prNumber,
			`🏷️ released as [\`${tagName}\`](${repoUrl}/releases/tag/${tagName})`,
		);

		// delete the component release branch
		deleteBranch(repoSlug, `release--${pkg.name}/${branch}`);
	}

	return {
		tag_name: tagName,
		version,
		componentTags: { [pkg.name]: version },
	};
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
