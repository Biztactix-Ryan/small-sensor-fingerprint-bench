#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Builds build/libpairtime.so, the per-pair C timing of bench/big_eval.py
# (see pairtime.c). bench/matchers.py runs this itself when it is missing.
set -e
cd "$(dirname "$0")"
mkdir -p build
# to a temporary name first: parallel workers may run this at once
gcc -O2 -std=gnu99 -fPIC -shared -Wall -o build/libpairtime.so.$$ pairtime.c
mv -f build/libpairtime.so.$$ build/libpairtime.so
echo "built: build/libpairtime.so"
