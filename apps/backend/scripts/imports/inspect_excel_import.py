import openpyxl
import re
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime
from backend.database.connection import DatabaseManager
from backend.utils.validators import validate_email, validate_phone

def inspect_excel():
    db = DatabaseManager.get_db()
    existing_users = list(db.users.find({}))
    existing_emails = {u.get('email', '').strip().lower(): u for u in existing_users if u.get('email')}
    existing_phones = {re.sub(r'[^0-9]', '', str(u.get('phone_number', ''))): u for u in existing_users if u.get('phone_number')}
    existing_names = {u.get('full_name', '').strip().lower(): u for u in existing_users if u.get('full_name')}

    wb = openpyxl.load_workbook('data/Intern-Full-Details(1).xlsx')
    ws = wb.active

    records = []
    for r in range(3, ws.max_row + 1):
        sno = ws.cell(r, 1).value
        name = ws.cell(r, 2).value
        contact = ws.cell(r, 3).value
        email = ws.cell(r, 4).value
        dob = ws.cell(r, 5).value
        if any([sno, name, contact, email, dob]):
            records.append({
                'row_num': r,
                'sno': int(sno) if isinstance(sno, (int, float)) else sno,
                'name': name,
                'contact_raw': contact,
                'email_raw': email,
                'dob_raw': dob
            })

    seen_emails = {}
    seen_phones = {}

    for rec in records:
        name_clean = str(rec['name']).strip() if rec['name'] else ''
        
        # Phone
        phone_digits = ''
        if rec['contact_raw'] is not None:
            if isinstance(rec['contact_raw'], float):
                phone_digits = str(int(rec['contact_raw'])).strip()
            else:
                phone_digits = re.sub(r'[^0-9]', '', str(rec['contact_raw'])).strip()
        
        # Email
        email_clean = str(rec['email_raw']).strip() if rec['email_raw'] else ''
        
        # DOB
        dob_clean = None
        dob_err = None
        if isinstance(rec['dob_raw'], datetime):
            dob_clean = rec['dob_raw'].strftime('%Y-%m-%d')
        elif isinstance(rec['dob_raw'], str):
            s = rec['dob_raw'].strip()
            m = re.match(r'^(\d{1,2})-(\d{1,2})-(\d{4})$', s)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                try:
                    dt = datetime(y, mo, d)
                    dob_clean = dt.strftime('%Y-%m-%d')
                except ValueError:
                    dob_err = f'Invalid calendar date: {s}'
            else:
                try:
                    dt = datetime.strptime(s, '%Y-%m-%d')
                    dob_clean = dt.strftime('%Y-%m-%d')
                except Exception:
                    dob_err = f'Unrecognized date format: {s}'
        else:
            dob_err = 'Missing date of birth'

        rec['name_clean'] = name_clean
        rec['phone_digits'] = phone_digits
        rec['phone_display'] = f'+91 {phone_digits}' if len(phone_digits) == 10 else phone_digits
        rec['email_clean'] = email_clean
        rec['dob_clean'] = dob_clean
        rec['dob_err'] = dob_err
        
        # Validations
        issues = []
        if not name_clean:
            issues.append('Missing employee name')
        if not phone_digits or len(phone_digits) != 10:
            issues.append(f'Invalid 10-digit Indian mobile number: {phone_digits}')
        
        # Check email validity
        if ' ' in email_clean:
            issues.append(f'Whitespace in email address: {repr(email_clean)}')
        elif not validate_email(email_clean):
            issues.append(f'Malformed email address: {repr(email_clean)}')
            
        if dob_err:
            issues.append(dob_err)
            
        # Duplicate within Excel
        email_key = email_clean.lower().replace(' ', '')
        if email_key in seen_emails:
            issues.append(f'Duplicate email in Excel sheet (matches row {seen_emails[email_key]})')
        else:
            seen_emails[email_key] = rec['row_num']
            
        if phone_digits in seen_phones:
            issues.append(f'Duplicate phone in Excel sheet (matches row {seen_phones[phone_digits]})')
        else:
            seen_phones[phone_digits] = rec['row_num']
            
        # Check against existing DB
        db_match = None
        if email_key in existing_emails:
            match_u = existing_emails[email_key]
            db_match = f"Email matches existing DB employee {match_u.get('employee_id')} ({match_u.get('full_name')})"
        elif phone_digits in existing_phones:
            match_u = existing_phones[phone_digits]
            db_match = f"Phone matches existing DB employee {match_u.get('employee_id')} ({match_u.get('full_name')})"
            
        rec['issues'] = issues
        rec['db_match'] = db_match

    invalid_recs = [r for r in records if r['issues']]
    db_matched_recs = [r for r in records if r['db_match']]
    clean_recs = [r for r in records if not r['issues'] and not r['db_match']]

    print(f'Total Excel records: {len(records)}')
    print(f'Ready for import (Clean): {len(clean_recs)}')
    print(f'Matching existing DB records: {len(db_matched_recs)}')
    print(f'Records requiring review / issues: {len(invalid_recs)}')

    print('\n' + '=' * 80)
    print('DETAILED PREVIEW OF ALL 34 RECORDS:')
    print('=' * 80)
    for r in records:
        status = 'READY'
        if r['db_match']:
            status = 'EXISTING_MATCH'
        elif r['issues']:
            status = 'REVIEW_REQUIRED'
            
        print(f"[{status:^15}] SNo: {r['sno']:2d} | Name: {r['name_clean']:<25} | Phone: {r['phone_display']:<14} | Email: {r['email_clean']:<35} | DOB: {r['dob_clean'] or 'INVALID'}")
        if r['issues']:
            for issue in r['issues']:
                print(f"                -> ISSUE: {issue}")
        if r['db_match']:
            print(f"                -> DB MATCH: {r['db_match']}")

if __name__ == '__main__':
    inspect_excel()
