#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Fetches the SIGFM sources of libfprint MR !530 at the commit the published
# results were produced with. They are LGPL-2.1-or-later; see the MR.
set -e
cd "$(dirname "$0")"
PIN=bc986621b906546836cb008355c1e8d5cd88a0db
REPO=https://gitlab.freedesktop.org/libfprint/libfprint.git
rm -rf src .git-tmp
git init -q .git-tmp
git -C .git-tmp fetch -q "$REPO" refs/merge-requests/530/head
if git -C .git-tmp cat-file -e "$PIN^{commit}" 2>/dev/null; then
  REV=$PIN
else
  echo "warning: pinned commit $PIN is no longer in !530, using its current head" >&2
  REV=FETCH_HEAD
fi
mkdir -p src
for f in sigfm.cpp sigfm.h binary.hpp img-info.hpp; do
  git -C .git-tmp show "$REV:libfprint/sigfm/$f" > "src/$f"
done
echo "fetched !530 SIGFM at $(git -C .git-tmp rev-parse "$REV")"
rm -rf .git-tmp
