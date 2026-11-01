#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Builds build/libnbis.so for the nbis matcher of bench/matchers.py: nbis.c
# with libfprint's copy of NIST's mindtct and bozorth3 (public domain, the
# notices stay in the sources), from the libfprint tree LIBFPRINT, with the
# warning flags libfprint builds them with.
# ./build.sh check also builds build/check_libfprint against a configured
# libfprint build (LIBFPRINT_BUILD, default $LIBFPRINT/_b, after ninja), see
# check_libfprint.c.
set -e
cd "$(dirname "$0")"
LIBFPRINT=${LIBFPRINT:-$HOME/Repo/FingerPrintReader/libfprint-upstream}
L=$LIBFPRINT/libfprint
mkdir -p build
INC="-I$L -I$L/nbis/include -I$L/nbis/libfprint-include"
WARN="-Wno-redundant-decls -Wno-discarded-qualifiers -Wno-array-bounds -Wno-array-parameter -Wno-unused-but-set-variable"
# no fused multiply-add, as in akaze/build.sh
gcc -O2 -std=gnu99 -fPIC -shared -ffp-contract=off $WARN $INC -o build/libnbis.so nbis.c \
  "$L"/nbis/mindtct/*.c "$L"/nbis/bozorth3/*.c $(pkg-config --cflags --libs glib-2.0) -lm
[ "$1" = check ] || { echo "built: build/libnbis.so"; exit 0; }
B=${LIBFPRINT_BUILD:-$LIBFPRINT/_b}
gcc -O2 -std=gnu99 $INC -I"$B/libfprint" -o build/check_libfprint check_libfprint.c \
  "$B/libfprint/libfprint-private.a" "$B/libfprint/libnbis.a" "$B/libfprint/libfprint-2.so" \
  -Wl,-rpath,"$B/libfprint" $(pkg-config --cflags --libs gio-2.0 gmodule-2.0 gusb) -lm
echo "built: build/libnbis.so build/check_libfprint"
