"""Synthetic checks and additive-adapter regressions; no client records."""

import csv
import copy
from pathlib import Path

import pytest

from ocr_ingestion.models import normalize_record
from pci_review.checks import check_records, contractor_name, load_reference
from pci_review.batch import run_batch
from pci_review.extraction import extract_for_review
from tests.helpers import write_pdf, detail_lines


def reference(tmp_path, **updates):
    row = dict(source_csv_row_number='100', subcontractor='BrandSafway Services',
               position='Laborer Journey Person', effective_time_period_start='2025-01-01',
               effective_time_period_finish='2025-12-31', reg_rate='10.00', ot_rate='15.00',
               dt_rate='20.00', status='Approved')
    row.update(updates)
    p = tmp_path / 'reference.csv'
    with p.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(row)); w.writeheader(); w.writerow(row)
    return p, load_reference(p)


def record(**updates):
    row = dict(record_id='a' * 64, document_id='b' * 64, source_file='synthetic.pdf',
               source_page='1', row_index='1', table_id='p1', contractor='BrandSafway',
               row_type='labor', position_original='Laborer Journeyman',
               work_start='2025-06-01', work_end='2025-06-01', reg_hours='4',
               reg_rate='10.00', reg_amount='40.00')
    row.update(updates)
    return normalize_record(row)


def rate_result(row, refs, **kwargs):
    return next(f for f in check_records([row], refs, **kwargs) if f['check'] == 'rate_schedule')


@pytest.mark.parametrize('submitted,status', [('10.00', 'Match'), ('10.01', 'Rate difference'), ('11.00', 'Rate difference')])
def test_applicable_reference_and_real_mismatch(tmp_path, submitted, status):
    _, refs = reference(tmp_path)
    finding = rate_result(record(reg_rate=submitted), refs)
    assert finding['status'] == status
    assert finding['expected_value'] == '10.00'
    assert finding['reference_source_rows'] == '100'
    assert finding['request_review_status'] == 'unverified_submission'
    assert finding['contract_compliance'] == 'Not checked'


@pytest.mark.parametrize('changes,reason', [
    ({'work_start': '', 'work_end': '', 'unlabeled_date_raw': '2025-06-01'}, 'work date'),
    ({'work_start': '2024-01-01', 'work_end': '2024-01-01'}, 'No one schedule'),
    ({'work_start': '2025-12-31', 'work_end': '2026-01-01'}, 'full work period'),
    ({'position_original': 'Laborer'}, 'exact reference'),
    ({'position_original': 'Laborer Apprentice'}, 'exact reference'),
    ({'contractor': 'Boston Forge & Welding (ACME Waterproof)'}, 'Contractor unconfirmed'),
])
def test_missing_or_ambiguous_inputs_never_pass(tmp_path, changes, reason):
    _, refs = reference(tmp_path)
    f = rate_result(record(**changes), refs)
    assert f['status'] in {'Cannot check', 'Needs review'}
    assert reason in f['reason']


def test_pending_overlapping_and_named_qualifier_references(tmp_path):
    _, refs = reference(tmp_path, status='Pending Final Approval')
    assert rate_result(record(), refs)['status'] == 'Needs review'
    _, refs = reference(tmp_path)
    assert rate_result(record(), refs + copy.deepcopy(refs))['status'] == 'Needs review'
    _, refs = reference(tmp_path, position='Laborer Journey Person (Named worker)')
    assert rate_result(record(), refs)['status'] != 'Match'


def test_generic_rate_requires_explicit_reviewed_billing_basis(tmp_path):
    _, refs = reference(tmp_path)
    r = record(reg_hours='', reg_rate='', reg_amount='', hours='4', rate='10.00', extension_amount='40.00')
    assert rate_result(r, refs)['status'] == 'Needs review'
    confirmation = {r['record_id']: {'reviewed': True, 'evidence': 'Synthetic source explicitly labels ST',
                                   'billing_category': 'reg'}}
    assert rate_result(r, refs, confirmations=confirmation)['status'] == 'Match'
    confirmation[r['record_id']]['reviewed'] = False
    assert rate_result(r, refs, confirmations=confirmation)['status'] != 'Match'


def test_overlay_ocr_review_gate_preserves_numeric_information(tmp_path):
    _, refs = reference(tmp_path)
    r = record()
    f = rate_result(r, refs, review_required_ids=[r['record_id']])
    assert f['status'] == 'Needs review' and f['numeric_comparison'] == 'Match'
    c = {r['record_id']: {'reviewed': True, 'evidence': 'Synthetic source verified', 'extraction_confirmed': True}}
    assert rate_result(r, refs, review_required_ids=[r['record_id']], confirmations=c)['status'] == 'Match'


def test_description_arithmetic_is_separate_from_rate_truth(tmp_path):
    _, refs = reference(tmp_path)
    r = record(description='2 Workers at 4 hours each', reg_hours='', reg_rate='', reg_amount='',
               hours='6', rate='10.00', extension_amount='60.00',
               overhead_profit_amount='9.00', total_amount='69.00')
    before = copy.deepcopy(r)
    findings = check_records([r], refs)
    assert next(f for f in findings if f['check'] == 'description_hours')['status'] == 'Difference'
    assert next(f for f in findings if f['check'] == 'hours_times_rate')['status'] == 'Match'
    assert next(f for f in findings if f['check'] == 'extension_plus_markup')['status'] == 'Match'
    assert r == before


def test_premium_no_subtraction_or_category_guess(tmp_path):
    _, refs = reference(tmp_path)
    r = record(reg_hours='', reg_rate='', reg_amount='', hours='4', rate='5.00', rate_basis_raw='Premium')
    c = {r['record_id']: {'reviewed': True, 'evidence': 'Synthetic premium confirmed', 'billing_category': 'premium_ot'}}
    f = rate_result(r, refs, confirmations=c)
    assert f['status'] == 'Cannot check' and 'premium missing' in f['reason']


def test_role_mapping_requires_evidence(tmp_path):
    _, refs = reference(tmp_path)
    r = record(position_original='LJ')
    mappings = {'BrandSafway|LJ': {'reference_position': 'Laborer Journey Person', 'reviewed': True,
                                  'evidence': 'Synthetic printed abbreviation key'}}
    assert rate_result(r, refs, role_confirmations=mappings)['status'] == 'Match'
    mappings['BrandSafway|LJ']['evidence'] = ''
    assert rate_result(r, refs, role_confirmations=mappings)['status'] != 'Match'


def test_new_trade_layout_extracts_values_without_inventing_meaning(tmp_path):
    lines = [(40, [(20, 'BrandSafway')]),
             (100, [(20, 'Trade'), (150, 'Hrs'), (260, 'Rate'), (380, 'Cost')]),
             (120, [(20, 'CF'), (150, '4'), (260, '10.00'), (380, '40.00')]),
             (140, [(20, 'Total'), (150, '4'), (380, '40.00')])]
    source = write_pdf(tmp_path / 'synthetic.pdf', lines)
    result, routing = extract_for_review(source)
    assert routing['contractor'] == 'BrandSafway'
    assert len(result.records) == 1
    r = result.records[0]
    assert r['position_original'] == 'CF' and r['rate'] == '10.00'
    assert r['work_start'] == '' and r['reg_rate'] == ''
    assert result.tables[-1].requires_review
    assert result.pages[0]['status'] == 'tables_found'
    assert result.pages[0]['table_count'] == 1


def test_mixed_package_never_assigns_all_rows_to_brandsafway(tmp_path):
    source = write_pdf(tmp_path / 'mixed.pdf', [(40, [(20, 'BrandSafway and JK Glass')])] + detail_lines())
    result, routing = extract_for_review(source)
    assert routing['contractor'] == ''
    assert all(not r['contractor'] for r in result.records)


def test_batch_deduplicates_inputs_preserves_prior_runs_and_app_dataset(tmp_path):
    source = write_pdf(tmp_path / 'source.pdf', [(40, [(20, 'BrandSafway')])] + detail_lines())
    renamed = tmp_path / 'renamed.pdf'; renamed.write_bytes(source.read_bytes())
    reference_path, _ = reference(tmp_path, position='Carpenter')
    app_data = tmp_path / 'document_line_items.csv'; app_data.write_text('untouched')
    output = tmp_path / 'run'
    report = run_batch([source, renamed], reference_path, output)
    assert report['unique_documents'] == 1
    assert report['processed_documents'] == 1
    assert app_data.read_text() == 'untouched'
    with pytest.raises(ValueError, match='not empty'):
        run_batch([source], reference_path, output)
    with pytest.raises(ValueError, match='outside the input'):
        run_batch([tmp_path], reference_path, tmp_path / 'nested_output')


def test_contractor_alias_is_not_substring_matching():
    assert contractor_name('ACME Waterproofing') == 'ACME Waterproofing'
    assert contractor_name('Boston Forge & Welding (ACME Waterproof)') == ''
