#!/bin/bash
# checks.sh: every check CI runs on a pull request (.github/workflows/checks.yml), in pinned
# containers, so it runs the same locally and in CI. Needs only Docker (and network for the
# external links of the link check; LINKS=offline skips those).
#
#   tools/checks.sh                     the pull-request checks
#   tools/checks.sh audit               trivy over the hash-pinned requirements files
#   tools/checks.sh image-audit IMAGE   trivy over a built image (images.yml), through Docker's socket
#
# The two audits fail on fixable HIGH and CRITICAL advisories; CI reports them without blocking
# (continue-on-error), and runs them weekly too, for new advisories in unchanged pins.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT=$(pwd)

SHELLCHECK_IMAGE=koalaman/shellcheck:v0.11.0@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d
BASH32_IMAGE=bash:3.2@sha256:2556c2da19c32c1614d318645c73a7bf64d38be21cf69e98e3ca51f053983719
BASH5_IMAGE=bash:5.2@sha256:2cf7ddaf5f6369c16a0359e3bd48e54ada211a2e4e90d87532ad2958d642bdd5
NODE_IMAGE=node:22-alpine@sha256:0e1754758c2df4cfa3e68d59e2e1b7374bb7fd9ea6328eaaacf15cc934af8202
PY_IMAGE=python:3.13-alpine@sha256:1e1f6334529d1fb26a2ef619d7cffb30a7c7d7cc1cc7338ebee283a58d1aeaca
LYCHEE_IMAGE=lycheeverse/lychee:0.24.2-alpine@sha256:2255c0b916cc8fc4193f59a4549358a6bae0f7d4ea16b5e1dd4c3b2733c35504
ACTIONLINT_IMAGE=rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667
ZIZMOR_IMAGE=ghcr.io/zizmorcore/zizmor:1.31.1@sha256:42d409dbb851d4c5d35a058cf042b828bea1e3f2884378c526eb0974780e18d9
GITLEAKS_IMAGE=zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
TRIVY_IMAGE=aquasec/trivy:0.76.2@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb
# yamllint and its dependencies: tools/requirements-yamllint.txt (versions and wheel hashes).

failed=0
# Addresses that only exist while the lab runs (loopback, the emulator, a devcontainer).
LOCAL_URLS=(--exclude '^https?://(127\.0\.0\.1|localhost|10\.0\.2\.2|host\.docker\.internal)')
run() { # run <name> <command...>
  printf '== %s\n' "$1"; shift
  if "$@"; then echo "   ok"; else echo "   FAILED"; failed=$((failed + 1)); fi
}
d() { docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$ROOT:/r:ro" -w /r "$@"; }

# trivy <fs|image> <docker run options...> -- <target>: fixable HIGH and CRITICAL advisories only.
# The vulnerability database is cached outside the repository (never /tmp, which may be RAM).
TRIVY_CACHE=${TRIVY_CACHE:-${RUNNER_TEMP:-$HOME/.cache/ha-companion-lab}/trivy}
trivy() {
  local mode=$1 opts=()
  shift
  while [ "$1" != -- ]; do opts+=("$1"); shift; done
  shift
  mkdir -p "$TRIVY_CACHE"
  d --cpus 2 --memory 4g -v "$TRIVY_CACHE:/cache" "${opts[@]}" "$TRIVY_IMAGE" "$mode" --cache-dir /cache --quiet \
    --scanners vuln --ignore-unfixed --severity HIGH,CRITICAL --exit-code 1 "$@"
}
case "${1:-}" in
  audit)
    # Trivy reads pip requirements only from files named requirements.txt, so each one is
    # mounted under that name (tools/requirements-yamllint.txt is not found under its own).
    trivy fs -v "$ROOT/stack/requirements.txt:/scan/stack/requirements.txt:ro" \
      -v "$ROOT/tools/cdp/requirements.txt:/scan/tools/cdp/requirements.txt:ro" \
      -v "$ROOT/tools/requirements-yamllint.txt:/scan/tools/yamllint/requirements.txt:ro" -- /scan
    exit
    ;;
  image-audit)
    [ -n "${2:-}" ] || { echo "usage: tools/checks.sh image-audit IMAGE"; exit 2; }
    trivy image -v /var/run/docker.sock:/var/run/docker.sock \
      --group-add "$(stat -c %g /var/run/docker.sock)" -- "$2"
    exit
    ;;
  "") ;;
  *) echo "usage: tools/checks.sh [audit | image-audit IMAGE]"; exit 2 ;;
esac

mapfile -t SH < <(git ls-files -co --exclude-standard '*.sh' 2>/dev/null || find . -name '*.sh' -not -path './.git/*')
mapfile -t PY < <(git ls-files -co --exclude-standard '*.py' 2>/dev/null || find . -name '*.py' -not -path './.git/*')
mapfile -t JS < <(git ls-files -co --exclude-standard '*.js' 2>/dev/null || find . -name '*.js' -not -path './.git/*')
mapfile -t YML < <(git ls-files -co --exclude-standard '*.yml' '*.yaml' 2>/dev/null || find . \( -name '*.yml' -o -name '*.yaml' \) -not -path './.git/*')

run "shellcheck" d "$SHELLCHECK_IMAGE" --severity=warning -x "${SH[@]}"
run "bash -n (bash 5)" d --entrypoint bash "$BASH5_IMAGE" -c 'for f in "$@"; do bash -n "$f" || exit 1; done' _ "${SH[@]}"
run "bash -n (bash 3.2, macOS)" d --entrypoint bash "$BASH32_IMAGE" -c 'for f in "$@"; do bash -n "$f" || exit 1; done' _ "${SH[@]}"
run "python compile" d "$PY_IMAGE" python -c 'import sys,ast; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]' "${PY[@]}"
run "python self-tests" d "$PY_IMAGE" sh -c 'python -I video/advanced-camera-card/tools/bg_summary.py --self-test >/dev/null && python -I video/advanced-camera-card/tools/rate_frames.py --self-test && python -I video/tools/go2rtc-consumers.py --self-test && python -I stack/sim_talk.py --self-test'
run "node --check" d "$NODE_IMAGE" sh -c 'for f in "$@"; do node --check "$f" || exit 1; done' _ "${JS[@]}"
run "yamllint" d "$PY_IMAGE" sh -c "pip install -q --no-cache-dir --require-hashes --no-deps --target /tmp/yl -r tools/requirements-yamllint.txt >/dev/null 2>&1 && PYTHONPATH=/tmp/yl python -m yamllint -d '{extends: relaxed, rules: {line-length: {max: 130}}}' \"\$@\"" _ "${YML[@]}"
run "house data" d "$PY_IMAGE" python -I tools/check-house-data.py /r
run "actionlint" d "$ACTIONLINT_IMAGE" -color
# GH_TOKEN (CI: the job's read-only token) enables zizmor's online audits; without it they are skipped.
run "zizmor" d -e GH_TOKEN "$ZIZMOR_IMAGE" ${GITHUB_ACTIONS:+--format=github} .
# gitleaks over the full history (CI checks out with fetch-depth: 0). In a git worktree, .git is a
# file pointing into the main checkout's .git, so that is mounted too, at the same path.
git_common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || git_common=
leaks_mount=()
[ -n "$git_common" ] && [ "$git_common" != "$ROOT/.git" ] && leaks_mount=(-v "$git_common:$git_common:ro")
run "gitleaks" d ${leaks_mount[@]+"${leaks_mount[@]}"} "$GITLEAKS_IMAGE" git /r --redact --no-banner
# AGENTS.md (other agents) and the Claude Code skill must carry the same hard rules.
hard_rules() { awk '/^## Hard rules$/{on=1} on && /^## / && !/^## Hard rules$/{exit} on' "$1"; }
same_hard_rules() {
  local a b
  a=$(hard_rules AGENTS.md); b=$(hard_rules .claude/skills/ha-companion-lab/SKILL.md)
  [ -n "$a" ] && [ "$a" = "$b" ] || { echo "   the Hard rules in AGENTS.md and SKILL.md differ"; return 1; }
}
run "hard rules in step" same_hard_rules
if [ "${LINKS:-}" = offline ]; then
  run "links (offline)" d "$LYCHEE_IMAGE" --offline --no-progress --include-fragments "${LOCAL_URLS[@]}" '*.md' '**/*.md'
else
  run "links" d "$LYCHEE_IMAGE" --no-progress --max-concurrency 4 --include-fragments "${LOCAL_URLS[@]}" '*.md' '**/*.md'
fi

echo
[ "$failed" -eq 0 ] && echo "all checks passed" || { echo "$failed check(s) failed"; exit 1; }
