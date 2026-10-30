#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Fetches the two C SIFT implementations at pinned commits into csift/src:
# VLFeat (BSD-2-Clause) and the FocalTech FT9366 matcher of a libfprint fork
# (LGPL-2.1-or-later).
set -e
cd "$(dirname "$0")"
mkdir -p src
get() {
  [ -d "src/$1" ] || git clone -q "$2" "src/$1"
  git -C "src/$1" checkout -q "$3"
  echo "fetched $1 at $3"
}
get vlfeat https://github.com/vlfeat/vlfeat.git 1b9075fc42fe54b42f0e937f8b9a230d8e2c7701
get ft9366 https://github.com/MillerRabin/libfprint.git 31491dfd7746926b89c4749afc7c5d052fa8ea08
