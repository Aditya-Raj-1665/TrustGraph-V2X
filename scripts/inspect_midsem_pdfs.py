"""Rasterize exported PDFs and verify expected page counts and text coverage."""
from pathlib import Path
import json
import pypdfium2 as pdfium
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    results = {}
    for kind, expected in [('Slides', 12), ('Report', 7)]:
        source = ROOT / 'midsem' / f'TrustGraph-V2X-Midsem-{kind}.pdf'
        reader = PdfReader(source)
        if len(reader.pages) != expected:
            raise ValueError(f'{kind}: expected {expected} pages, found {len(reader.pages)}')
        directory = ROOT / '.qa' / f'pdf-{kind.lower()}'
        directory.mkdir(parents=True, exist_ok=True)
        pdf = pdfium.PdfDocument(source)
        characters = []
        for index, page in enumerate(pdf):
            image = page.render(scale=1.6).to_pil()
            image.save(directory / f'page-{index + 1:02d}.png')
            text = reader.pages[index].extract_text()
            if not text or len(text.strip()) < 100:
                raise ValueError(f'{kind} page {index+1} has suspiciously little text')
            characters.append(len(text))
            page.close()
        pdf.close()
        results[kind] = {'pages': expected, 'text_characters': characters, 'render_directory': str(directory)}
    (ROOT / '.qa/pdf-checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
