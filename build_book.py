"""Build a book that displays numbers 1 to 50,000 using collected number images."""
from pathlib import Path
import argparse
import pypdf
import re


def get_image_for_number(number: int, numbers_dir: Path) -> tuple[Path, int]:
    """Get the first available PNG for a number and extract its height from filename.

    Returns:
        Tuple of (image_path, height_in_pixels)
    """
    number_dir = numbers_dir / str(number)
    png_files = list(number_dir.glob('*.png'))
    if not png_files:
        raise FileNotFoundError(f"No PNG files found for number {number} in {number_dir}")

    image_path = png_files[0]

    # Extract height from filename pattern: *_h{height}.png
    match = re.search(r'_h(\d+)\.png$', image_path.name)
    if not match:
        raise ValueError(f"Image filename does not contain height: {image_path}")

    height = int(match.group(1))
    return image_path, height


GRID_COLUMNS = 5

# Letter page: 8.5in × 11in, with 2in margins = 4.5in × 7in content area
# At 96 DPI: 7 * 96 = 672px height available per column
COLUMN_TARGET_HEIGHT_PX = 672


def distribute_numbers_to_columns(
    numbers_with_heights: list[tuple[int, int, Path]], num_columns: int, target_height: int
) -> tuple[list[list[tuple[int, Path]]], int]:
    """Distribute numbers across columns sequentially, filling each column to target height.

    Numbers are added in order down the first column until target height is reached,
    then down the second column, etc. Stops when all columns are filled.

    Args:
        numbers_with_heights: List of (number, height, image_path) tuples in sequential order
        num_columns: Number of columns to distribute across
        target_height: Target height in pixels for each column

    Returns:
        Tuple of (columns, numbers_used) where columns is a list of columns and
        numbers_used is the count of numbers actually placed
    """
    columns: list[list[tuple[int, Path]]] = [[] for _ in range(num_columns)]
    current_column_idx = 0
    current_height = 0
    numbers_used = 0

    for number, height, image_path in numbers_with_heights:
        # If adding this number would exceed target, try to move to next column
        if current_height + height > target_height:
            # Stop if we're already on the last column and it would exceed target
            if current_column_idx >= num_columns - 1:
                break
            # Otherwise move to next column
            current_column_idx += 1
            current_height = 0

        # Add to current column
        columns[current_column_idx].append((number, image_path))
        current_height += height
        numbers_used += 1

    return columns, numbers_used


def get_html_style() -> list[str]:
    """Get the HTML style section used for all pages."""
    return [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '    <meta charset="UTF-8">',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '    <title>The Numbers</title>',
        '    <style>',
        '        @page {',
        '            margin: 2in;',
        '        }',
        '        html, body {',
        '            height: 100%;',
        '        }',
        '        body {',
        '            font-family: Georgia, serif;',
        '            margin: 0;',
        '            padding: 0;',
        '            display: flex;',
        '            min-height: 100%;',
        '        }',
        '        .container {',
        '            flex: 1;',
        '            display: flex;',
        '            gap: 10px;',
        '            box-sizing: border-box;',
        '            height: 100%;',
        '        }',
        '        .column {',
        '            display: flex;',
        '            flex-direction: column;',
        '            flex: 1 1 0;',
        '        }',
        '        .number-item {',
        '            display: flex;',
        '            align-items: flex-start;',
        '            justify-content: center;',
        '        }',
        '        .number-image {',
        '            width: auto;',
        '            height: auto;',
        '            max-width: 100%;',
        '        }',
        '    </style>',
        '</head>',
        '<body>',
    ]


def build_page_html(numbers_dir: Path, start_number: int, max_count: int) -> tuple[str, int]:
    """Build HTML for a single page with numbers starting from start_number.

    Numbers are distributed across columns to fill each column to approximately
    the target height based on actual image heights encoded in filenames.

    Returns:
        Tuple of (html_content, numbers_used)
    """
    html_parts = get_html_style()
    html_parts.append('    <div class="container">')

    # Collect numbers with their heights (up to max_count available)
    numbers_with_heights = []
    for number in range(start_number, start_number + max_count):
        image_path, height = get_image_for_number(number, numbers_dir)
        numbers_with_heights.append((number, height, image_path))

    # Distribute numbers across columns based on heights
    columns, numbers_used = distribute_numbers_to_columns(
        numbers_with_heights, GRID_COLUMNS, COLUMN_TARGET_HEIGHT_PX
    )

    # Build HTML for each column
    for column in columns:
        if not column:
            continue

        html_parts.append('        <div class="column">')

        for number, image_path in column:
            html_parts.append('            <div class="number-item">')
            html_parts.append(f'                <img src="file://{image_path.absolute()}" alt="{number}" class="number-image">')
            html_parts.append('            </div>')

        html_parts.append('        </div>')

    html_parts.extend([
        '    </div>',
        '</body>',
        '</html>'
    ])

    return '\n'.join(html_parts), numbers_used


def html_to_pdf(html_path: Path, pdf_path: Path):
    """Convert HTML to PDF using playwright."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        page.goto(
            f"file://{html_path.absolute()}",
            wait_until="load",
            timeout=120_000
        )

        page.pdf(path=str(pdf_path), format="Letter", print_background=True)
        browser.close()


def merge_pdfs(pdf_paths: list[Path], output_path: Path):
    """Merge multiple PDFs into a single PDF."""
    merger = pypdf.PdfWriter()

    for pdf_path in pdf_paths:
        merger.append(str(pdf_path))

    merger.write(str(output_path))
    merger.close()


def main():
    """Generate PDF book with numbers 1 to max_number."""
    parser = argparse.ArgumentParser(description='Build a book of numbers 1 to 50,000')
    parser.add_argument('--max-number', type=int, default=50_000, help='Maximum number to include (default: 50,000)')
    parser.add_argument('--numbers-per-page', type=int, default=200,
                        help='Maximum number of images to try per page (default: 200)')
    args = parser.parse_args()

    numbers_dir = Path('data/numbers')
    output_dir = Path('output')
    output_dir.mkdir(exist_ok=True)
    temp_dir = output_dir / 'temp_pages'
    temp_dir.mkdir(exist_ok=True)

    print(f"Generating pages (trying up to {args.numbers_per_page} numbers per page, actual count varies by image height)...")

    page_pdfs = []
    current_number = 1
    page_num = 0

    while current_number <= args.max_number:
        # Calculate how many numbers we could try to fit on this page
        remaining = args.max_number - current_number + 1
        max_count = min(args.numbers_per_page, remaining)

        # Generate HTML for this page and see how many numbers actually fit
        html_content, numbers_used = build_page_html(numbers_dir, current_number, max_count)

        if numbers_used == 0:
            print(f"Warning: No numbers fit on page starting at {current_number}")
            break

        end_number = current_number + numbers_used - 1
        print(f"Page {page_num + 1} (numbers {current_number}-{end_number})...")

        html_path = temp_dir / f'page_{page_num:04d}.html'
        html_path.write_text(html_content, encoding='utf-8')

        # Convert to PDF
        pdf_path = temp_dir / f'page_{page_num:04d}.pdf'
        html_to_pdf(html_path, pdf_path)
        page_pdfs.append(pdf_path)

        # Move to next page
        current_number += numbers_used
        page_num += 1

    print(f"\nMerging {len(page_pdfs)} pages...")
    final_pdf = output_dir / 'the_numbers.pdf'
    merge_pdfs(page_pdfs, final_pdf)

    print("\nCleaning up temporary PDFs...")
    for pdf_file in temp_dir.glob('*.pdf'):
        pdf_file.unlink()

    print(f"\nPDF created: {final_pdf}")
    print(f"HTML pages kept in: {temp_dir}")


if __name__ == '__main__':
    main()
