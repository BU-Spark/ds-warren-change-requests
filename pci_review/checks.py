"""Conservative, source-preserving checks independent of Streamlit and PDF parsing."""

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import re


TOLERANCE = Decimal('0.02')
RATE_TOLERANCE = Decimal('0.00')
FINDING_FIELDS = [
    'record_id', 'document_id', 'source_file', 'source_page', 'table_id',
    'contractor', 'position_original', 'work_start', 'work_end', 'check',
    'billing_category', 'status', 'reason', 'submitted_value', 'expected_value',
    'difference', 'numeric_comparison', 'reference_source_rows', 'reference_candidates',
    'extraction_review_required', 'request_review_status', 'contract_compliance',
]


def decimal(value):
    text = ('' if value is None else str(value)).strip().replace('$', '').replace(',', '')
    if not text or text in {'-', '—', '–'}:
        return None
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    try:
        result = Decimal(text)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def date(value):
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(str(value or ''), fmt).date()
        except ValueError:
            pass
    return None


def normalized(value):
    # Keep qualifications, parentheses, names, levels and trade-specific wording.
    text = re.sub(r'\s+', ' ', str(value or '').strip().casefold())
    text = re.sub(r'\bforeman\b', 'foreperson', text)
    return re.sub(r'\b(?:journeyman|journeyperson|journey person)\b', 'journey person', text)


def contractor_name(value):
    # Exact aliases only: a name merely mentioning ACME is not ACME itself.
    return {
        'brandsafway': 'BrandSafway', 'brandsafway services': 'BrandSafway',
        'brandsafway, inc.': 'BrandSafway', 'brandsafway inc.': 'BrandSafway',
        'acme': 'ACME Waterproofing', 'acme waterproofing': 'ACME Waterproofing',
        'acme waterproofing co., inc.': 'ACME Waterproofing',
    }.get(normalized(value), '')


def load_reference(path):
    with open(path, newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        required = {'subcontractor', 'position', 'effective_time_period_start',
                    'effective_time_period_finish', 'reg_rate', 'ot_rate', 'dt_rate', 'status'}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError('Reference CSV missing columns: ' + ', '.join(sorted(missing)))
        rows = []
        for line, row in enumerate(reader, 2):
            if not contractor_name(row['subcontractor']) or not row['position'].strip():
                continue
            rows.append({**row, '_source_row': row.get('source_csv_row_number') or str(line),
                         '_contractor': contractor_name(row['subcontractor']),
                         '_role': normalized(row['position'])})
    return rows


def _finding(row, check, *, extraction_review=False, **values):
    result = {key: str(row.get(key, '')) for key in FINDING_FIELDS[:9]}
    result.update(check=check, billing_category='', status='Cannot check', reason='',
                  submitted_value='', expected_value='', difference='', numeric_comparison='',
                  reference_source_rows='', reference_candidates='',
                  extraction_review_required=str(bool(extraction_review)).lower(),
                  request_review_status='unverified_submission', contract_compliance='Not checked')
    result.update(values)
    return result


def _amount(value):
    return format(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP), 'f')


def _comparison(row, label, observed, calculated, extraction_review):
    if observed is None or calculated is None:
        return _finding(row, label, extraction_review=extraction_review,
                        reason='Required printed numeric fields missing or unresolved.')
    calculated = calculated.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    difference = observed - calculated
    match = abs(difference) <= TOLERANCE
    return _finding(row, label, extraction_review=extraction_review,
                    submitted_value=str(observed), expected_value=_amount(calculated),
                    difference=_amount(difference), numeric_comparison='Match' if match else 'Difference',
                    status='Needs review' if extraction_review else 'Match' if match else 'Difference',
                    reason=('Confirm extraction against original printed cells. ' if extraction_review else '')
                    + 'Arithmetic comparison only; does not establish contract compliance.')


def arithmetic_checks(row, extraction_review=False):
    out = []
    hours, rate = decimal(row.get('hours')), decimal(row.get('rate'))
    if hours is not None or rate is not None:
        out.append(_comparison(row, 'hours_times_rate', decimal(row.get('extension_amount')),
                               hours * rate if hours is not None and rate is not None else None,
                               extraction_review))
    parts = []
    used = False
    complete = True
    for category in ('reg', 'ot', 'dt'):
        h, r = decimal(row.get(category + '_hours')), decimal(row.get(category + '_rate'))
        if h is not None and h != 0:
            used = True
            if r is None:
                complete = False
                out.append(_finding(row, 'hours_times_rate', billing_category=category,
                                    extraction_review=extraction_review, reason='Billed category has no usable rate.'))
            else:
                parts.append(h * r)
                if decimal(row.get(category + '_amount')) is not None:
                    finding = _comparison(row, 'hours_times_rate', decimal(row.get(category + '_amount')),
                                          h * r, extraction_review)
                    finding['billing_category'] = category
                    out.append(finding)
        elif h is None and str(row.get(category + '_hours') or '').strip() not in {'', '-', '—', '–'}:
            complete = False
    if used and complete:
        # Missing inactive columns are not fabricated into source zero values.
        total = decimal(row.get('total_amount'))
        if total is not None:
            out.append(_comparison(row, 'labor_amount_sum', total, sum(parts, Decimal(0)), extraction_review))
    extension, markup, total = (decimal(row.get(k)) for k in
                                ('extension_amount', 'overhead_profit_amount', 'total_amount'))
    if extension is not None and markup is not None and total is not None:
        out.append(_comparison(row, 'extension_plus_markup', total, extension + markup, extraction_review))
    # Explicit description arithmetic only. No assumption about worker seniority or billing type.
    description = str(row.get('description', ''))
    match = re.match(r'^\s*(\d+(?:\.\d+)?)\s+.+?\s+at\s+(\d+(?:\.\d+)?)\s+hours?\b', description, re.I)
    if match and hours is not None:
        out.append(_comparison(row, 'description_hours', hours,
                               Decimal(match[1]) * Decimal(match[2]), extraction_review))
    for key in ('hours', 'reg_hours', 'ot_hours', 'dt_hours', 'rate', 'reg_rate', 'ot_rate', 'dt_rate'):
        number = decimal(row.get(key))
        if number is not None and number < 0:
            out.append(_finding(row, 'negative_value', extraction_review=extraction_review,
                                status='Needs review', submitted_value=str(number),
                                reason=f'Negative {key}; may be an adjustment. Confirm its meaning.'))
    return out


def rate_checks(row, reference, *, extraction_review=False, role_confirmations=None, confirmation=None):
    """Only compare unambiguous applicable schedules; never infer a role from a matching rate."""
    confirmation = confirmation or {}
    confirmed = confirmation.get('reviewed') is True and bool(str(confirmation.get('evidence', '')).strip())
    contractor = contractor_name(row.get('contractor'))
    role = row.get('position_original', '')
    mapping = (role_confirmations or {}).get(contractor + '|' + role)
    if mapping and mapping.get('reviewed') is True and mapping.get('evidence'):
        role = mapping.get('reference_position', role)
    candidates = [r for r in reference if r['_contractor'] == contractor and r['_role'] == normalized(role)]
    start = date(row.get('work_start'))
    end = date(row.get('work_end')) or start
    # Confirmations fill absent dates only; they do not silently replace printed dates.
    if start is None and not str(row.get('work_start') or '').strip() and confirmed:
        start = date(confirmation.get('work_start'))
        end = date(confirmation.get('work_end')) or start
    dated = [r for r in candidates if date(r['effective_time_period_start']) and
             date(r['effective_time_period_finish']) and start and end and
             date(r['effective_time_period_start']) <= start <= end <= date(r['effective_time_period_finish'])]
    categories = [(key, decimal(row.get(key + '_rate'))) for key in ('reg', 'ot', 'dt')
                  if decimal(row.get(key + '_hours')) not in (None, Decimal(0))]
    if str(row.get('rate') or '').strip():
        categories.append(('generic', decimal(row.get('rate'))))
    if not categories:
        categories = [('unresolved', None)]
    results = []
    for category, submitted in categories:
        basis = confirmation.get('billing_category') if confirmed and category == 'generic' else category
        finding = _finding(row, 'rate_schedule', extraction_review=extraction_review,
                           billing_category=category, submitted_value=str(submitted) if submitted is not None else '')
        finding['reference_source_rows'] = ';'.join(r['_source_row'] for r in dated)
        finding['reference_candidates'] = json.dumps([
            {k: r.get(k, '') for k in ('_source_row', 'position', 'effective_time_period_start',
                                      'effective_time_period_finish', 'reg_rate', 'ot_rate', 'dt_rate', 'status')}
            for r in (dated or candidates)], ensure_ascii=False)
        reasons = []
        if not contractor:
            reasons.append('Contractor unconfirmed, unsupported, or mixed; no schedule assigned.')
        if not role or not candidates:
            reasons.append('Worker role needs an exact reference match or a documented reviewed mapping; qualifiers retained.')
        if not start or not end or (row.get('work_end') and date(row['work_end']) is None):
            reasons.append('Actual printed/confirmed work date required; request and rate-expiry dates are not substitutes.')
        elif end < start:
            reasons.append('Work period ends before it starts.')
        elif not dated:
            reasons.append('No one schedule covers the full work period; verify dates, reference coverage, and possible rate changes.')
        elif len(dated) > 1:
            reasons.append('Overlapping applicable reference schedules require review.')
        if basis not in ('reg', 'ot', 'dt', 'premium_ot', 'premium_dt'):
            reasons.append('Generic/premium billing category not confirmed; no ST/OT/DT category inferred from rate value.')
        if category != 'generic' and row.get('rate_basis_raw') and re.search(r'premium', row['rate_basis_raw'], re.I):
            reasons.append('Premium wording conflicts with an assumed full-rate comparison; confirm the billing basis.')
        if submitted is None:
            reasons.append('Submitted rate missing or unresolved.')
        if reasons:
            finding.update(status='Needs review' if contractor and start else 'Cannot check', reason=' '.join(reasons))
        else:
            schedule = dated[0]
            if normalized(schedule.get('status')) != 'approved':
                finding.update(status='Needs review', reason='Applicable schedule is not explicitly Approved.')
            else:
                if basis.startswith('premium_'):
                    premium_field = 'ot_premium_only' if basis == 'premium_ot' else 'dt_premium_only'
                    expected = decimal(schedule.get(premium_field))
                else:
                    expected = decimal(schedule.get(basis + '_rate'))
                if expected is None:
                    finding.update(reason='Applicable reference rate/premium missing or not a single usable value.')
                else:
                    difference = submitted - expected
                    match = abs(difference) <= RATE_TOLERANCE
                    finding.update(expected_value=str(expected), difference=_amount(difference),
                                   numeric_comparison='Match' if match else 'Difference',
                                   status='Needs review' if extraction_review else 'Match' if match else 'Rate difference',
                                   reason=('Confirm extraction first. ' if extraction_review else '') +
                                   'Compared with the explicitly Approved schedule for the work period; full compliance not checked.')
        results.append(finding)
    return results


def check_records(records, reference, *, review_required_ids=(), confirmations=None, role_confirmations=None):
    """Pure API for a future UI; does not mutate records, files, references or approval state."""
    findings = []
    for row in records:
        confirmation = (confirmations or {}).get(row['record_id'], {})
        extraction_review = row['record_id'] in review_required_ids
        if (confirmation.get('reviewed') is True and confirmation.get('evidence') and
                confirmation.get('extraction_confirmed') is True):
            extraction_review = False
        findings.extend(arithmetic_checks(row, extraction_review))
        findings.extend(rate_checks(row, reference, extraction_review=extraction_review,
                                    role_confirmations=role_confirmations, confirmation=confirmation))
    return findings
