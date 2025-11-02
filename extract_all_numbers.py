"""Extract number images from hOCR files and JP2 images."""
import re
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from selectolax.parser import HTMLParser
from PIL import Image
from word2number import w2n


def extract_number_from_text(text: str) -> int | None:
    """Extract a number from text if it's between 0-50,000."""
    text = text.strip().lower()

    # Handle "zero" explicitly
    if text == "zero":
        return 0

    # Try direct numeric parsing - but only accept properly formatted numbers
    # (no leading zeros except for "0" itself)
    if text.isdigit():
        # Reject strings like "00" or "000" - only accept "0"
        if text.startswith('0') and len(text) > 1:
            return None
        num = int(text)
        if 0 <= num <= 50_000:
            return num

    # Try word to number conversion (e.g., "twenty-three" -> 23)
    # Skip if result would be 0 (word2number incorrectly converts "point" and other words to 0)
    try:
        num = w2n.word_to_num(text)
        if isinstance(num, int) and 1 <= num <= 50_000:
            return num
    except (ValueError, IndexError):
        pass

    return None


def parse_bbox(title: str) -> tuple[int, int, int, int] | None:
    """Extract bounding box coordinates from hOCR title attribute."""
    if match := re.search(r'bbox (\d+) (\d+) (\d+) (\d+)', title):
        x0, y0, x1, y1 = map(int, match.groups())
        return (x0, y0, x1, y1)
    return None


def parse_ppageno(title: str) -> int | None:
    """Extract physical page number from hOCR title attribute."""
    if match := re.search(r'ppageno (\d+)', title):
        return int(match.group(1))
    return None


def parse_confidence(title: str) -> float | None:
    """Extract OCR confidence from hOCR title attribute (x_wconf)."""
    if match := re.search(r'x_wconf (\d+(?:\.\d+)?)', title):
        return float(match.group(1))
    return None


def parse_image_path(title: str) -> str | None:
    """Extract image path from hOCR title attribute."""
    if match := re.search(r'image "([^"]+)"', title):
        # Extract just the filename from the path
        return Path(match.group(1)).name
    return None


def extract_numbers_from_hocr(hocr_path: Path) -> dict[str, list[tuple[int, int, int, int, int]]]:
    """
    Parse hOCR file and extract all numbers with their bounding boxes.
    Only capture the first occurrence of each number per book.

    Returns:
        Dict mapping image filename to list of (number, x0, y0, x1, y1) tuples
    """
    html = HTMLParser(hocr_path.read_text())
    numbers_by_image = {}
    seen_numbers = set()

    # Find all pages
    for page in html.css('div.ocr_page'):
        if not (page_title := page.attributes.get('title')):
            continue
        if (image_name := parse_image_path(page_title)) is None:
            continue

        # Find all words on this page
        for word in page.css('span.ocrx_word'):
            if not (text := word.text()):
                continue

            if (number := extract_number_from_text(text)) is None:
                continue

            # Skip if we've already captured this number in this book
            if number in seen_numbers:
                continue

            if not (word_title := word.attributes.get('title')):
                continue

            # Only include numbers with confidence > 90
            if (confidence := parse_confidence(word_title)) is None or confidence <= 90:
                continue

            if (bbox := parse_bbox(word_title)) is None:
                continue

            if image_name not in numbers_by_image:
                numbers_by_image[image_name] = []

            numbers_by_image[image_name].append((number, *bbox))
            seen_numbers.add(number)

    return numbers_by_image


def extract_and_save_numbers(hocr_path: Path, jp2_dir: Path, output_dir: Path, book_name: str):
    """
    Extract all numbers from hOCR file and save corresponding image regions.

    Args:
        hocr_path: Path to hOCR HTML file
        jp2_dir: Directory containing JP2 page images
        output_dir: Directory to save extracted number PNGs
        book_name: Name of the book being processed
    """
    print(f"Processing {book_name}...")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse hOCR to get numbers and bounding boxes
    numbers_by_image = extract_numbers_from_hocr(hocr_path)

    count = 0
    skipped = 0
    # Extract each number from corresponding JP2
    for image_name, numbers in numbers_by_image.items():
        # Find JP2 file by exact name
        jp2_path = jp2_dir / image_name

        if not jp2_path.exists():
            print(f"Warning: JP2 not found: {jp2_path}")
            continue

        # Open JP2 image once for this page
        with Image.open(jp2_path) as img:
            # Process all numbers on this page
            for number, x0, y0, x1, y1 in numbers:
                # Check if output already exists
                number_dir = output_dir / str(number)
                output_path = number_dir / f"{number}_{book_name}_{image_name.replace('.jp2', '.png')}"

                if output_path.exists():
                    skipped += 1
                    continue

                # Crop region
                region = img.crop((x0, y0, x1, y1))

                # Save as PNG - create numbered subdirectories for organization
                number_dir.mkdir(exist_ok=True)
                region.save(output_path, 'PNG')
                count += 1

    print(f"Completed {book_name}: extracted {count} numbers, skipped {skipped} existing")
    return count


def process_book(book_dir: Path, output_dir: Path) -> int:
    """Process a single book directory."""
    # Find hOCR file
    hocr_files = list(book_dir.glob('*_hocr.html'))
    if not hocr_files:
        print(f"No hOCR file found in {book_dir}")
        return 0

    hocr_path = hocr_files[0]

    # Find JP2 directory
    jp2_dirs = list(book_dir.glob('*_jp2'))
    if not jp2_dirs:
        print(f"No JP2 directory found in {book_dir}")
        return 0

    jp2_dir = jp2_dirs[0]

    return extract_and_save_numbers(hocr_path, jp2_dir, output_dir, book_dir.name)


def main():
    """Process all downloaded books in parallel."""
    raw_dir = Path('data/raw')
    output_dir = Path('data/numbers')

    # Collect all book directories
    book_dirs = [d for d in raw_dir.iterdir() if d.is_dir()]

    print(f"Found {len(book_dirs)} books to process")

    # Process books in parallel
    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(process_book, book_dir, output_dir): book_dir for book_dir in book_dirs}
        results = []
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                print(f"Error processing {futures[future]}: {e}")
                results.append(0)

    total = sum(results)
    print(f"Total numbers extracted: {total}")


if __name__ == '__main__':
    main()
