"""Additive adapter around the teammate extractor; its stored schema is unchanged."""

from pathlib import Path
import re

import pymupdf

from ocr_ingestion import extract_document
from ocr_ingestion.extraction import _lines, _native_words, _split, _text
from ocr_ingestion.models import Table, normalize_record, row_id
from .checks import contractor_name, decimal


def identify_document(path):
    """Provisional document routing only, never a verified assignment in mixed packages."""
    with pymupdf.open(path) as document:
        text = '\n'.join(page.get_text() for page in document)
        supported = []
        if re.search(r'brand\s*[>›]?\s*safway', text, re.I):
            supported.append('BrandSafway')
        if re.search(r'\bacme\s+(?:waterproof|bulletin)', text, re.I):
            supported.append('ACME Waterproofing')
        # Explicit known other suppliers in these packages; not a universal contractor detector.
        others = sorted({label for pattern, label in [
            (r'JK\s*(?:Glass|/\s*Lymo)', 'JK Glass/Lymo'), (r'\bLYMO\b', 'Lymo'),
            (r'\bNew\s*Bama\b', 'NewBama'), (r'\bTGG\b', 'TGG'),
            (r'\bStarlite\b', 'Starlite'), (r'\bGrande\b', 'Grande'),
        ] if re.search(pattern, text, re.I)})
        single = len(supported) == 1 and not others
        return {'contractor': supported[0] if single else '', 'supported_mentions': supported,
                'other_mentions': others, 'routing_status': 'provisional_single_contractor' if single else
                'mixed_or_unsupported_review_required', 'page_count': len(document)}


def add_trade_tables(result, path, contractor, project):
    """Read explicit Trade/Hrs/Rate/Cost rows; keep CF/LF/LJ and unknown dates/basis."""
    if contractor_name(contractor) != 'BrandSafway':
        return
    with pymupdf.open(path) as document:
        for page_index, page in enumerate(document, 1):
            words, removed = _native_words(page)
            lines = _lines(words)
            for index, line in enumerate(lines):
                keys = [w.text.casefold() for w in line]
                if not {'trade', 'hrs', 'rate', 'cost'}.issubset(keys):
                    continue
                selected = [(w.x, {'trade': 'position_original', 'hrs': 'hours',
                                    'rate': 'rate', 'cost': 'extension_amount'}[w.text.casefold()])
                            for w in line if w.text.casefold() in {'trade', 'hrs', 'rate', 'cost'}]
                selected.sort()
                table_id = f'pci-p{page_index}-trade-y{round(line[0].y)}'
                table = Table(table_id, page_index, 'labor', [f for _, f in selected], [],
                              [min(w.x0 for w in line), min(w.y0 for w in line),
                               max(w.x1 for w in line), max(w.y1 for w in line)],
                              'native_trade_geometry', True)
                for source_row, body in enumerate(lines[index + 1:], 1):
                    if re.match(r'^(?:total|subtotal|trade|freight|hardcosts|rental)\b', _text(body), re.I):
                        break
                    values = dict(zip([f for _, f in selected], _split(body, selected)))
                    if not values.get('position_original') or decimal(values.get('rate')) is None:
                        break
                    if decimal(values.get('hours')) is None or decimal(values.get('extension_amount')) is None:
                        continue
                    record = normalize_record({**values, 'row_type': 'labor', 'contractor': contractor,
                        'project': project, 'source_file': Path(path).name, 'source_page': str(page_index),
                        'document_id': result.document_id, 'table_id': table_id, 'row_index': str(source_row),
                        'record_id': row_id(result.document_id, table_id, source_row),
                        'extraction_method': 'native_trade_geometry'})
                    table.rows.append([values[f] for _, f in selected])
                    table.record_ids.append(record['record_id'])
                    table.bbox[3] = max(w.y1 for w in body)
                    result.records.append(record)
                if table.record_ids:
                    result.tables.append(table)
                    for page_status in result.pages:
                        if page_status['page'] == page_index:
                            page_status.update(status='tables_found',
                                               table_count=sum(t.page == page_index for t in result.tables),
                                               method='native_with_trade_adapter')
                    result.issue(page_index, 'trade_table_review_required',
                                 'New printed Trade/Hrs/Rate/Cost layout. Confirm abbreviations, work dates and billing basis.',
                                 table_id=table_id, filtered_spans=removed)


def extract_for_review(path, *, project='Warren Towers', use_ocr=False):
    routing = identify_document(path)
    result = extract_document(path, contractor=routing['contractor'], project=project, use_ocr=use_ocr)
    add_trade_tables(result, path, routing['contractor'], project)
    return result, routing
