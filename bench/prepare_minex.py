#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Converts the MINEX III validation imagery (raw 8-bit .gray files, sizes
listed in minexiii_validation_data.h) to PNG for public_sets.py.

Usage: prepare_minex.py DATA_DIR
  expects DATA_DIR/minex/minexiii (a checkout of github.com/usnistgov/minex),
  writes DATA_DIR/minex/png/<name>.png
"""
import os
import re
import sys

import cv2
import numpy as np


def main():
    root = os.path.join(sys.argv[1], "minex")
    val = os.path.join(root, "minexiii", "validation")
    # fingerprints only, not the synthetic test images (black.gray etc.)
    sizes = re.findall(r'\{"([ab]\d+_\d+)\.gray", \{(\d+), (\d+),',
                       open(os.path.join(val, "minexiii_validation_data.h")).read())
    os.makedirs(os.path.join(root, "png"), exist_ok=True)
    for name, w, h in sizes:
        raw = np.fromfile(os.path.join(val, "validation_imagery_raw", name + ".gray"), dtype=np.uint8)
        w, h = int(w), int(h)
        assert raw.size == w * h, (name, raw.size, w, h)
        cv2.imwrite(os.path.join(root, "png", name + ".png"), raw.reshape(h, w))
    print(f"wrote {len(sizes)} images to {os.path.join(root, 'png')}")


if __name__ == "__main__":
    main()
