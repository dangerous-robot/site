#!/usr/bin/env bash
# Refuse to deploy a commit that is not a tagged release, or a site push
# (four-part version) that carries research changes. The deploy workflow runs
# this against the pushed commit (docs/runbook.md § Releasing).
# Usage: scripts/check-release-tag.sh [commit]   (default: HEAD)
set -euo pipefail

sha="${1:-$(git rev-parse HEAD)}"
version="$(head -n 1 VERSION.md | tr -d '[:space:]')"
tag="v$version"
roadmap="$(sed -n 's/^Active release: *//p' VERSION.md | tr -d '[:space:]')"

hint_tag="$tag"
fail() {
  echo "::error::$1"
  echo "To release: bump the first line of VERSION.md, add the Releases row in $roadmap, commit, then:"
  echo "  git tag -a $hint_tag -m \"$hint_tag\" && git push --atomic origin main $hint_tag"
  exit 1
}

[ -n "$version" ] || fail "VERSION.md has no version on its first line."
[ -f "$roadmap" ] || fail "VERSION.md names an active release roadmap that does not exist: $roadmap"

# The runner's checkout is shallow and has no tags; fetch just this one. A miss
# is reported below, not here.
if ! git rev-parse -q --verify "refs/tags/$tag^{commit}" >/dev/null 2>&1; then
  git fetch -q --no-tags --depth 1 origin "refs/tags/$tag:refs/tags/$tag" 2>/dev/null || true
fi
tagged="$(git rev-parse -q --verify "refs/tags/$tag^{commit}" 2>/dev/null || true)"

[ -n "$tagged" ] || fail "No tag $tag exists for the version in VERSION.md ($version)."
[ "$tagged" = "$sha" ] || { hint_tag="v<new version>"; fail "Tag $tag points at ${tagged:0:7}, not at the commit being deployed (${sha:0:7}): VERSION.md was not bumped for this push."; }
grep -qF "| \`$version\` |" "$roadmap" || fail "$roadmap has no Releases row for $version."

# A four-part version (beta.N.M) is a site push, which may not carry research
# changes (docs/runbook.md § Releasing). Compare against the tag it follows:
# beta.N.(M-1), or beta.N when M is 1. Comparing two trees needs no history, so
# the shallow CI checkout only fetches that tag.
kind="beta release"
if [[ "$version" =~ ^(.+\.)([0-9]+)\.([0-9]+)$ ]] && [[ "$version" == *-* ]]; then
  kind="site push"
  minor="${BASH_REMATCH[3]}"
  if [ "$minor" -gt 1 ]; then
    prev="v${BASH_REMATCH[1]}${BASH_REMATCH[2]}.$((minor - 1))"
  else
    prev="v${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
  fi
  if ! git rev-parse -q --verify "refs/tags/$prev^{commit}" >/dev/null 2>&1; then
    git fetch -q --no-tags --depth 1 origin "refs/tags/$prev:refs/tags/$prev" 2>/dev/null || true
  fi
  prev_sha="$(git rev-parse -q --verify "refs/tags/$prev^{commit}" 2>/dev/null || true)"
  hint_tag="v<next beta>"
  [ -n "$prev_sha" ] || fail "$version is a site push, but the tag it follows ($prev) does not exist."
  research="$(git diff --name-only "$prev_sha" "$sha" -- research pipeline src/pages/research \
    scripts/scheduled-recheck.sh .github/workflows/recheck.yml)"
  if [ -n "$research" ]; then
    echo "Research files changed since $prev:"
    echo "$research" | head -n 20 | sed 's/^/  /'
    n="$(echo "$research" | wc -l | tr -d ' ')"
    [ "$n" -le 20 ] || echo "  ... and $((n - 20)) more"
    fail "$version is a site push (four-part version), but $n research file(s) changed since $prev. Release it as the next beta instead."
  fi
fi

echo "release check: $tag is at ${sha:0:7} ($kind) and $roadmap has its Releases row"
