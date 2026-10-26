"""
Generates a multi-resolution Windows .ico file (16x16, 32x32, 48x48)
using standard library struct and math (Zero external dependencies).
"""

import os
import struct
import math


def create_icon_bmp(size: int) -> bytes:
    """Creates a 32-bit RGBA BITMAPINFOHEADER image for an ICO file."""
    width = size
    height = size * 2  # In ICO BMP, height is doubled (image + mask)

    # 40-byte BITMAPINFOHEADER
    header = struct.pack(
        "<IiiHHIIiiII",
        40,          # biSize
        width,       # biWidth
        height,      # biHeight (positive)
        1,           # biPlanes
        32,          # biBitCount
        0,           # biCompression (BI_RGB)
        width * size * 4,  # biSizeImage
        0, 0, 0, 0
    )

    # Pixel data (bottom-up BGRA)
    pixels = bytearray()
    center = (size - 1) / 2.0
    radius = size * 0.44

    for y in range(size - 1, -1, -1):
        for x in range(size):
            dx = x - center
            dy = y - center
            dist = math.sqrt(dx * dx + dy * dy)

            if dist <= radius:
                # Inside rounded icon: Vibrant Fluent Blue-Cyan gradient with lightning center
                t = (x + y) / (2.0 * size)
                r = int(0 + t * 0)
                g = int(120 + t * 90)
                b = int(212 + t * 40)
                a = 255

                # Inner lightning bolt shape
                nx = (x - center) / radius
                ny = (y - center) / radius
                # lightning polygon approximation
                if (-0.3 <= nx <= 0.3 and -0.6 <= ny <= 0.6) and (nx * 1.5 - ny > -0.2 and nx * 1.5 - ny < 0.5):
                    r, g, b = 255, 255, 255

                pixels.extend([b, g, r, a])
            else:
                # Transparent
                pixels.extend([0, 0, 0, 0])

    # 1-bit AND mask (all 0 for 32-bit alpha)
    mask_stride = ((width + 31) // 32) * 4
    mask = bytes(mask_stride * size)

    return header + bytes(pixels) + mask


def build_ico(sizes=[16, 32, 48]) -> bytes:
    count = len(sizes)
    # 6-byte ICONDIR
    ico_data = bytearray(struct.pack("<HHH", 0, 1, count))

    images = [create_icon_bmp(s) for s in sizes]
    offset = 6 + count * 16

    # ICONDIRENTRY for each size
    for s, img in zip(sizes, images):
        entry = struct.pack(
            "<BBBBHHII",
            s if s < 256 else 0,
            s if s < 256 else 0,
            0,  # color count
            0,  # reserved
            1,  # planes
            32, # bpp
            len(img),
            offset
        )
        ico_data.extend(entry)
        offset += len(img)

    for img in images:
        ico_data.extend(img)

    return bytes(ico_data)


if __name__ == "__main__":
    os.makedirs("assets", exist_ok=True)
    ico_bytes = build_ico([16, 32, 48])
    with open("assets/OmniToys.ico", "wb") as f:
        f.write(ico_bytes)
    print(f"Generated assets/OmniToys.ico ({len(ico_bytes)} bytes)")
