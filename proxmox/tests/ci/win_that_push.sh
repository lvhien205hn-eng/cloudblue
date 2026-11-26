#!/usr/bin/env bash
# Day ket qua (anh man hinh + file ket qua) len nhanh win-shots-<tag> (nhanh mo coi, ghi de; kem vercel.json tat deploy). Can GH_TOKEN + GITHUB_REPOSITORY.
#   win_that_push.sh <tag> <thu muc kq> <loi nhan>
set -uo pipefail
TAG=${1:?tag}; KQ=${2:?kq}; MSG=${3:-ket qua}
[ -n "${GH_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ] || { echo "khong co GH_TOKEN / GITHUB_REPOSITORY - bo qua"; exit 0; }
D=$(mktemp -d)
mkdir -p "$D/shots" "$D/blueroblox-site"
cp -r "$KQ"/. "$D/shots/" 2>/dev/null
echo '{"git":{"deploymentEnabled":false}}' > "$D/blueroblox-site/vercel.json"
cd "$D" || exit 1
git init -q . && git config user.name "github-actions[bot]" && git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git checkout -q --orphan kq
git add -A >/dev/null 2>&1
git commit -q -m "Thu that Windows tu cai $TAG: $MSG (${GITHUB_SHA:-?})" >/dev/null 2>&1
out=$(git -c credential.helper= push -q -f "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" "HEAD:refs/heads/win-shots-$TAG" 2>&1); rc=$?
[ $rc -eq 0 ] || echo "${out//$GH_TOKEN/***}" | tail -3
cd / && rm -rf "$D"
exit $rc
