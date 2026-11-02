"""Batch candidates and preliminary findings. No writes to the app's accumulated dataset."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from ocr_ingestion.models import FIELDS
from .checks import FINDING_FIELDS, check_records, load_reference
from .extraction import extract_for_review


def write_csv(path, rows, fields):
    with Path(path).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def run_batch(inputs, reference_path, output, *, use_ocr=False, project='Warren Towers', config=None):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output folder is not empty. Choose a fresh run folder to preserve prior results.')
    # A result directory must not be inside a source input directory: protect repeat discovery.
    for source in inputs:
        source = Path(source)
        if source.is_dir() and output.resolve().is_relative_to(source.resolve()):
            raise ValueError('Choose an output folder outside the input folder.')
    output.mkdir(parents=True, exist_ok=True)
    reference = load_reference(reference_path)
    config = config or {}
    paths = []
    for source in inputs:
        source = Path(source)
        if source.is_dir():
            paths.extend(p for p in source.rglob('*') if p.suffix.lower() == '.pdf' and p.is_file())
        elif source.is_file() and source.suffix.lower() == '.pdf':
            paths.append(source)
        else:
            raise ValueError(f'Input is not a PDF or directory: {source}')
    if not paths:
        raise ValueError('No PDF inputs found.')
    all_records, findings, documents, issues, pages, confirmations, table_log = [], [], [], [], [], [], []
    seen = set()
    for source in sorted(set(paths)):
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest in seen:
            documents.append({'source_file': source.name, 'document_id': digest,
                              'status': 'duplicate_identical_input_skipped', 'rows': 0})
            continue
        seen.add(digest)
        print(f'Processing {source.name}', flush=True)
        try:
            result, routing = extract_for_review(source, project=project, use_ocr=use_ocr)
        except Exception as exc:
            documents.append({'source_file': source.name, 'document_id': digest, 'status': 'failed',
                              'rows': 0, 'error': f'{type(exc).__name__}: {exc}'})
            continue
        required = {rid for table in result.tables if table.requires_review for rid in table.record_ids}
        evidence_name = digest + '-evidence.json'
        (output / evidence_name).write_text(result.as_json(), encoding='utf-8')
        row_findings = check_records(result.records, reference, review_required_ids=required,
                                    confirmations=config.get('record_confirmations', {}),
                                    role_confirmations=config.get('role_confirmations', {}))
        all_records.extend(result.records)
        findings.extend(row_findings)
        for issue in result.issues:
            issues.append({'source_file': source.name, 'document_id': digest, **issue})
        for page in result.pages:
            pages.append({'source_file': source.name, 'document_id': digest, **page})
        for table in result.tables:
            table_log.append({'source_file': source.name, 'document_id': digest, 'page': table.page,
                              'table_id': table.table_id, 'kind': table.kind, 'requires_review': table.requires_review,
                              'record_count': len(table.record_ids), 'method': table.method})
        documents.append({'source_file': source.name, 'document_id': digest, 'status': 'processed',
            'contractor': routing['contractor'], 'routing_status': routing['routing_status'],
            'supported_mentions': '; '.join(routing['supported_mentions']),
            'other_mentions': '; '.join(routing['other_mentions']), 'pages': routing['page_count'],
            'rows': len(result.records), 'tables': len(result.tables),
            'rows_missing_work_date': sum(not r['work_start'] for r in result.records),
            'rows_requiring_extraction_review': len(required),
            'unmapped_tables': sum(t.kind == 'unfamiliar' for t in result.tables),
            'evidence_file': evidence_name, 'review_status': 'unverified_submission',
            'coverage_note': 'No usable labor rows; inspect source/layout.' if not result.records else
                             'Partial labor extraction; totals/clauses/handwriting are not comprehensively checked.'})
        for row in result.records:
            confirmations.append({'record_id': row['record_id'], 'document_id': digest,
                'source_file': source.name, 'source_page': row['source_page'],
                'position_original': row['position_original'], 'work_start_as_extracted': row['work_start'],
                'rate_as_extracted': row['rate'], 'reviewed': 'false', 'evidence': '',
                'confirmed_work_start': '', 'confirmed_work_end': '', 'confirmed_billing_category': '',
                'extraction_confirmed': 'false'})
    write_csv(output / 'extracted_labor.csv', all_records, FIELDS)
    write_csv(output / 'findings.csv', findings, FINDING_FIELDS)
    doc_fields = ['source_file', 'document_id', 'status', 'contractor', 'routing_status',
        'supported_mentions', 'other_mentions', 'pages', 'rows', 'tables', 'rows_missing_work_date',
        'rows_requiring_extraction_review', 'unmapped_tables', 'review_status', 'coverage_note', 'evidence_file', 'error']
    write_csv(output / 'document_inventory.csv', documents, doc_fields)
    write_csv(output / 'page_inventory.csv', pages, ['source_file', 'document_id', 'page', 'status', 'table_count', 'method'])
    write_csv(output / 'table_inventory.csv', table_log,
              ['source_file', 'document_id', 'page', 'table_id', 'kind', 'requires_review', 'record_count', 'method'])
    confirmation_fields = ['record_id', 'document_id', 'source_file', 'source_page', 'position_original',
        'work_start_as_extracted', 'rate_as_extracted', 'reviewed', 'evidence', 'confirmed_work_start',
        'confirmed_work_end', 'confirmed_billing_category', 'extraction_confirmed']
    write_csv(output / 'review_worksheet.csv', confirmations, confirmation_fields)
    (output / 'extraction_issues.json').write_text(json.dumps(issues, indent=2), encoding='utf-8')
    report = {'input_pdf_count': len(set(paths)), 'unique_documents': len(seen),
        'processed_documents': sum(d['status'] == 'processed' for d in documents),
        'failed_documents': sum(d['status'] == 'failed' for d in documents),
        'pages': sum(d.get('pages', 0) for d in documents), 'labor_rows': len(all_records),
        'rows_missing_work_date': sum(not r['work_start'] for r in all_records),
        'finding_status_counts': dict(Counter(f['status'] for f in findings)),
        'rate_status_counts': dict(Counter(f['status'] for f in findings if f['check'] == 'rate_schedule')),
        'numeric_comparison_counts': dict(Counter(f['numeric_comparison'] for f in findings if f['numeric_comparison'])),
        'ocr_enabled': use_ocr, 'reference_sha256': hashlib.sha256(Path(reference_path).read_bytes()).hexdigest(),
        'scope': 'Unverified submissions. Preliminary field/arithmetic/rate checks, not approvals or full compliance.',
        'accuracy': 'Not measured: client-confirmed extraction and review labels are not available.',
        'existing_saved_dataset_modified': False}
    (output / 'run_summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', nargs='+', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--project', default='Warren Towers')
    parser.add_argument('--ocr', action='store_true', help='Enable local printed-table OCR; slower and requires Tesseract.')
    parser.add_argument('--config', type=Path, help='Reviewed role/date/billing confirmations as JSON.')
    args = parser.parse_args()
    # Keep client evidence in the existing private data directory by default and by CLI contract.
    private = Path(__file__).resolve().parents[1] / 'data'
    if not args.output.resolve().is_relative_to(private.resolve()):
        parser.error('--output must be inside the repository data/ directory.')
    config = json.loads(args.config.read_text()) if args.config else {}
    report = run_batch(args.inputs, args.reference, args.output, use_ocr=args.ocr, project=args.project, config=config)
    print(json.dumps(report, indent=2))
    if report['failed_documents']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
