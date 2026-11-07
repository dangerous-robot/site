#!/usr/bin/env bash
# The scheduled recheck job: `dr recheck --due`, then `dr findings`, then every change
# under research/ (pending drafts, new sources, findings) committed and pushed to an
# Actions branch that a person fetches and reviews with `dr review`. Nothing here signs
# off or touches main. Called by .github/workflows/recheck.yml; runs by hand the same way.
#
# Environment, all optional:
#   RECHECK_BRANCH   branch that carries the batch (default actions/recheck)
#   RECHECK_REMOTE   remote name (default origin)
#   RECHECK_BASE     branch the batch is drafted from (default main)
#   DR               the dr command, run from pipeline/ (default "uv run dr");
#                    a stub here makes the job testable without a paid run
#   RECHECK_PUSH     1 pushes (default); 0 stops after the local commit
#   GITHUB_TOKEN     when set, authenticates the fetch and push (Actions)
#   GITHUB_STEP_SUMMARY  when set, the command outputs are appended there
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
BRANCH="${RECHECK_BRANCH:-actions/recheck}"
REMOTE="${RECHECK_REMOTE:-origin}"
BASE="${RECHECK_BASE:-main}"
DR="${DR:-uv run dr}"
PUSH="${RECHECK_PUSH:-1}"

summary() {
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then printf '%s\n' "$@" >> "$GITHUB_STEP_SUMMARY"; fi
}

# actions/checkout keeps no credentials (persist-credentials: false), so the token
# goes on each git call that talks to GitHub, the way checkout itself sends it.
auth=()
if [ -n "${GITHUB_TOKEN:-}" ]; then
  basic="$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 | tr -d '\n')"
  auth=(-c "http.https://github.com/.extraheader=AUTHORIZATION: basic $basic")
fi

# Skip while the last batch is unreviewed: the branch exists and has commits main lacks.
git "${auth[@]}" fetch --quiet "$REMOTE" "$BASE"
base_sha="$(git rev-parse FETCH_HEAD)"
if git "${auth[@]}" fetch --quiet "$REMOTE" "$BRANCH" 2>/dev/null; then
  old_sha="$(git rev-parse FETCH_HEAD)"
  if ! git merge-base --is-ancestor "$old_sha" "$base_sha"; then
    echo "skip: $REMOTE/$BRANCH has commits not in $BASE; review and merge it first"
    summary "Skipped: \`$BRANCH\` still carries an unreviewed batch."
    exit 0
  fi
fi

out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

# dr recheck exits 0 unless it failed to start, so the summary lines, not the exit
# code, say which claims ran and which were abandoned. The step summary shows both.
echo "+ dr recheck --due"
(cd pipeline && $DR recheck --due) 2>&1 | tee "$out/recheck.txt"
echo "+ dr findings"
(cd pipeline && $DR findings) 2>&1 | tee "$out/findings.txt"
summary "## dr recheck --due" '```' "$(cat "$out/recheck.txt")" '```' "## dr findings" '```' "$(cat "$out/findings.txt")" '```'

git add -- research
if git diff --cached --quiet; then
  echo "nothing to push: research/ is unchanged"
  summary "Nothing to review: no claim was due, or every due run was abandoned (see the findings)."
  exit 0
fi

git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit --quiet -m "chore(research): scheduled recheck $(date -u +%Y-%m-%d)"
git --no-pager show --stat --format='%h %s' HEAD

if [ "$PUSH" != "1" ]; then
  echo "RECHECK_PUSH=$PUSH: committed locally, not pushed"
  exit 0
fi
# Always a fast-forward: the branch was either absent or already merged into main.
git "${auth[@]}" push --quiet "$REMOTE" "HEAD:refs/heads/$BRANCH"
echo "pushed to $REMOTE/$BRANCH; fetch it and review with dr review"
summary "Pushed a batch to \`$BRANCH\`. Fetch it and review with \`dr review\` (runbook § Scheduled rechecks)."
