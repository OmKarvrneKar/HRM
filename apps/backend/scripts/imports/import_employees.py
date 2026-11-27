import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.database.connection import DatabaseManager
from backend.services.employee_import_service import EmployeeImportService

def main():
    parser = argparse.ArgumentParser(description="AISAMRAT HRMS Employee Data Importer")
    parser.add_argument("--preview", action="store_true", help="Generate validation preview without modifying database")
    parser.add_argument("--execute", action="store_true", help="Execute the import into the persistent database")
    parser.add_argument("--auto-sanitize", action="store_true", help="Automatically sanitize benign whitespace in emails (e.g. SNo 13)")
    parser.add_argument("--file", type=str, default="data/Intern-Full-Details(1).xlsx", help="Path to Excel spreadsheet")
    args = parser.parse_args()

    print("=" * 80)
    print("AISAMRAT HRMS — ORIGINAL EMPLOYEE DATA INTEGRATION")
    print("=" * 80)

    if not args.execute and not args.preview:
        args.preview = True

    if args.preview:
        print(f"\n[MODE: PREVIEW ONLY] Inspecting {args.file}...")
        preview = EmployeeImportService.generate_preview(args.file)
        print(f"\nTotal Excel Records: {preview['total_records']}")
        print(f"Ready for Import:     {preview['ready_count']}")
        print(f"Existing Matches:     {preview['existing_match_count']}")
        print(f"Duplicates:           {preview['duplicate_count']}")
        print(f"Invalid Records:      {preview['invalid_count']}")
        print(f"Pending Review:       {preview['pending_review_count']}")

        print("\n" + "-" * 80)
        print("RECORDS PREVIEW:")
        print("-" * 80)
        for r in preview["records"]:
            print(f"[{r['status']:^15}] SNo {r['sno']:2d} | {r['name']:<25} | {r['phone_display']:<14} | {r['email_clean']:<35} | DOB: {r['dob_clean'] or 'INVALID'}")
            if r["issues"]:
                for iss in r["issues"]:
                    print(f"                -> ISSUE: {iss}")
            if r["db_match"]:
                print(f"                -> DB MATCH: {r['db_match']}")

        if preview["pending_review_count"] > 0:
            print("\n[NOTE] Records requiring review detected. You can run with '--execute' to import clean records (leaving pending ones skipped), or '--execute --auto-sanitize' to clean benign spaces.")
        return

    if args.execute:
        print(f"\n[MODE: EXECUTE IMPORT] Reading {args.file} (auto_sanitize={args.auto_sanitize})...")
        actor = {
            "employee_id": "ADM-1001",
            "full_name": "System Administrator",
            "role": "manager"
        }
        res = EmployeeImportService.execute_import(actor=actor, file_path=args.file, auto_sanitize_whitespace=args.auto_sanitize)

        print("\n" + "=" * 80)
        print("IMPORT EXECUTION COMPLETED")
        print("=" * 80)
        print(f"Database Backup:         {res['backup_path']}")
        print(f"Total Spreadsheet Rows:  {res['total_excel_records']}")
        print(f"Successfully Imported:   {res['imported_count']}")
        print(f"Skipped / Matches:       {res['skipped_count']}")
        print(f"Duplicate Entries:       {res['duplicate_count']}")
        print(f"Invalid Records:         {res['invalid_count']}")
        print(f"Pending Review Records:  {res['pending_review_count']}")

        print("\n--- Imported Employee Records ---")
        for rec in res["imported_records"]:
            print(f"SNo {rec['sno']:2d} -> {rec['employee_id']} | {rec['name']:<25} | {rec['email']:<35} | {rec['phone']} | DOB: {rec['date_of_birth']} | Role: {rec['role']}")

        if res["pending_review_records"]:
            print("\n--- Records Pending Manual Review ---")
            for rec in res["pending_review_records"]:
                print(f"SNo {rec['sno']:2d} -> {rec['name']} | Issues: {rec['issues']} | Raw: {rec['raw_email']}")

if __name__ == "__main__":
    main()
