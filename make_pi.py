"""Compose pi digits from existing number images.

Given a count of pi digits, find which image files from data/numbers/
can be used to compose that string, preferring longer sequences first.
"""

import argparse
from pathlib import Path

from mpmath import mp
from rich.progress import track

from compose_missing_numbers import (
    find_largest_string_decomposition,
    get_available_numbers,
    get_image_for_number,
)

# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mpmath",
#     "rich",
#     "pillow",
# ]
# ///


def main():
    parser = argparse.ArgumentParser(
        description="Find image files to compose pi digits"
    )
    parser.add_argument(
        "count",
        type=int,
        nargs="?",
        default=50000,
        help="How many digits of pi to compose (default: 50000)",
    )
    parser.add_argument(
        "--numbers-dir",
        type=Path,
        default=Path("data/numbers"),
        help="Directory containing number images (default: data/numbers)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("π.html"),
        help="Output HTML file (default: π.html)",
    )
    args = parser.parse_args()

    # Generate pi digits using mpmath
    mp.dps = args.count + 10  # Extra precision to be safe
    pi_str = mp.nstr(mp.pi, args.count + 1, strip_zeros=False)
    # Remove the decimal point and get exactly the requested digits
    digits = pi_str.replace(".", "")[: args.count]

    print(f"Composing {len(digits)} digits of pi...")
    print(f"Pi digits: {digits[:20]}{'...' if len(digits) > 20 else ''}")

    # Get available numbers
    available = get_available_numbers(args.numbers_dir)
    print(f"Found {len(available)} numbers with images")

    # Find decomposition - start with "3", then "14", then decompose the rest
    # This gives us "3.14..." on the first line
    first_digit = int(digits[0])  # 3
    second_part = int(digits[1:3])  # 14

    remaining_components = find_largest_string_decomposition(digits[3:], available)
    if remaining_components is None:
        components = None
    else:
        components = [first_digit, second_part] + remaining_components

    if components is None:
        print("Error: Cannot compose the given digits from available numbers")
        return 1

    print(f"\nDecomposition uses {len(components):,} images:")
    print(f"Numbers: {components[:20]}{'...' if len(components) > 20 else ''}")

    # Write output to file
    with open(args.output, "w") as f:
        f.write("<html>\n<head>\n")
        f.write("<title>π</title>\n")
        f.write('<link rel="stylesheet" href="style.css">\n')
        f.write("</head>\n<body>\n")

        # Write "3.14" on the first line
        # First the "3"
        first_img = get_image_for_number(components[0], args.numbers_dir)
        if first_img:
            f.write(f'<img src="{first_img}" alt="{components[0]}">\n')
        else:
            raise ValueError(f"No image found for {components[0]}")

        # Then the decimal point
        f.write('<span class="decimal">⬤</span>\n')

        # Then the "14"
        second_img = get_image_for_number(components[1], args.numbers_dir)
        if second_img:
            f.write(f'<img src="{second_img}" alt="{components[1]}">\n')
        else:
            raise ValueError(f"No image found for {components[1]}")

        f.write("<br>\n")

        # Write the remaining digits
        for num in track(
            components[2:],
            description="Generating output...",
        ):
            img_path = get_image_for_number(num, args.numbers_dir)
            if img_path:
                f.write(f'<img src="{img_path}" alt="{num}">\n')
            else:
                raise ValueError(f"No image found for {num}")
        f.write("</body>\n</html>\n")

    print(f"\nOutput written to {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
