#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Builds build/<name>/virtual_check (see virtual_check.c) against the objects
# of a configured and built libfprint tree, linked like libfprint-2.so is but
# into the executable, plus --wrap=fpi_image_device_image_captured.
#   ./build.sh NAME LIBFPRINT_BUILD_DIR
# e.g. ./build.sh nbis ~/Repo/FingerPrintReader/libfprint-upstream/_b
# Run ninja in the build directory first: the objects are used as they are.
# The build needs the virtual_image driver (meson -Ddrivers=all). Builds for
# bench/virtual_check.py run --matcher NAME:
#   nbis       any libfprint tree
#   sigfm      !530 (bc986621; sigfm-normalize-fix gives the same with virtual_image)
#   sigfm_fix  the same with sigfm/patches/ssubbotin-ordering-and-cap.patch
#              applied to libfprint/sigfm/sigfm.cpp
#   akaze_c    the sift-matcher branch (KEYPOINT prints); export the harness
#              scores with FPBENCH_AKAZE_LIB built from the same tree (akaze/
#              build.sh lib with LIBFPRINT=...), so both run the same code
set -e
cd "$(dirname "$0")"
NAME=$1
B=$(realpath "$2")
[ -n "$NAME" ] && [ -f "$B/build.ninja" ] || { echo "usage: $0 NAME LIBFPRINT_BUILD_DIR" >&2; exit 2; }
OUT=$PWD/build/$NAME
mkdir -p "$OUT"
# compile flags of the image device core, link inputs and flags of the library
python3 - "$B" "$OUT" <<'EOF'
import json, shlex, sys, re
b, out = sys.argv[1:]
cc = [e for e in json.load(open(f"{b}/compile_commands.json")) if e["file"].endswith("libfprint/fp-image-device.c")][0]
args = shlex.split(cc["command"])
keep = [a for a in args[1:] if a.startswith(("-I", "-D", "-std", "-O", "-f", "-pthread")) and not a.startswith("-fdiagnostics")]
src = open(f"{b}/build.ninja").read()
m = re.search(r"^build libfprint/libfprint-2\.so\.[0-9.]+: c(?:pp)?_LINKER (.*?)(?: \||$)\n LINK_ARGS = (.*)$", src, re.M)
objs = [o for o in m.group(1).split() if o.endswith(".o")]
link = [a for a in shlex.split(m.group(2))
        if a not in ("-shared", "-fPIC", "-Wl,--no-undefined") and not a.startswith(("-Wl,-soname", "-Wl,--version-script"))]
cpp = re.search(r"^build libfprint/libfprint-2\.so\.[0-9.]+: cpp_LINKER", src, re.M) is not None
open(f"{out}/flags", "w").write("\n".join([shlex.join(keep), shlex.join(objs), shlex.join(link), "g++" if cpp else "cc"]) + "\n")
EOF
CFLAGS=$(sed -n 1p "$OUT/flags")
OBJS=$(sed -n 2p "$OUT/flags")
LINK=$(sed -n 3p "$OUT/flags")
LD=$(sed -n 4p "$OUT/flags")
SRC=$(python3 -c "import json, sys; print(json.load(open(sys.argv[1]))['directories']['source'])" \
  "$B/meson-info/meson-info.json")/libfprint
DEFS=""
[ -f "$SRC/sigfm/sigfm.h" ] && DEFS="$DEFS -DHAVE_SIGFM"
grep -q fpi_image_device_set_score_threshold "$SRC/fpi-image-device.h" && DEFS="$DEFS -DHAVE_SCORE_THRESHOLD"
grep -q FPI_DEVICE_ALGO_KEYPOINT "$SRC/fpi-image-device.h" && DEFS="$DEFS -DHAVE_KEYPOINT"
# relative include paths and inputs are relative to the build directory
(cd "$B" && eval cc -c $CFLAGS $DEFS -Wno-missing-prototypes -Wno-missing-declarations \
   -o "$OUT/virtual_check.o" "$OLDPWD/virtual_check.c")
(cd "$B" && eval $LD -o "$OUT/virtual_check" "$OUT/virtual_check.o" $OBJS \
   -Wl,--wrap=fpi_image_device_image_captured $LINK)
echo "$B" > "$OUT/libfprint_build"
git -C "$SRC" describe --always --dirty > "$OUT/libfprint_rev" 2>/dev/null || true
echo "built: $OUT/virtual_check (libfprint $(cat "$OUT/libfprint_rev" 2>/dev/null) at $B,$DEFS )"
