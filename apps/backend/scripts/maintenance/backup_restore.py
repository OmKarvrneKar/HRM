"""
AI SAMRAT HRMS — DATABASE BACKUP & RESTORATION CLI UTILITY

Usage:
    python scripts/maintenance/backup_restore.py --backup
    python scripts/maintenance/backup_restore.py --list
    python scripts/maintenance/backup_restore.py --restore latest
    python scripts/maintenance/backup_restore.py --restore <path_to_backup_folder>
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import Config
from backend.database.connection import DatabaseManager


def create_backup():
    print("[BACKUP] Starting database snapshot...")
    backup_path = DatabaseManager.backup_database()
    if backup_path:
        print(f"[SUCCESS] Database snapshot created successfully at:\n  {backup_path}")
        return backup_path
    else:
        print("[ERROR] Database backup failed!")
        sys.exit(1)


def list_backups():
    backup_dir = Path(Config.DATA_DIR) / "backups"
    if not backup_dir.exists():
        print("[INFO] No backups directory found.")
        return []

    snapshots = sorted([d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith("backup_")], reverse=True)
    if not snapshots:
        print("[INFO] No existing backup snapshots found.")
        return []

    print(f"\nAvailable Database Snapshots ({len(snapshots)} found):")
    print("-" * 75)
    print(f"{'Snapshot Name':<42} {'Files':<8} {'Total Size':<12}")
    print("-" * 75)
    for s in snapshots:
        files = list(s.glob("*.json"))
        size_bytes = sum(f.stat().st_size for f in files)
        size_kb = size_bytes / 1024
        print(f"{s.name:<42} {len(files):<8} {size_kb:>8.1f} KB")
    print("-" * 75)
    return snapshots


def restore_backup(target):
    snapshots = list_backups()
    if not snapshots:
        print("[ERROR] No snapshots available to restore.")
        sys.exit(1)

    restore_path = None
    if target.lower() == "latest":
        restore_path = snapshots[0]
    else:
        cand = Path(target)
        if cand.exists() and cand.is_dir():
            restore_path = cand
        else:
            # check inside backups dir
            backup_dir = Path(Config.DATA_DIR) / "backups" / target
            if backup_dir.exists() and backup_dir.is_dir():
                restore_path = backup_dir

    if not restore_path:
        print(f"[ERROR] Could not resolve backup path: '{target}'")
        sys.exit(1)

    print(f"\n[RESTORE] Restoring database from: {restore_path} ...")
    success = DatabaseManager.restore_database(restore_path)
    if success:
        db = DatabaseManager.get_db()
        users_count = db.users.count_documents({})
        print(f"[SUCCESS] Database restored successfully!")
        print(f"[VERIFY] Restored database '{db.name}' contains {users_count} user accounts.")
    else:
        print("[ERROR] Database restoration failed!")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="AI Samrat HRMS Database Backup and Recovery Utility")
    parser.add_argument("--backup", action="store_true", help="Create a timestamped database backup")
    parser.add_argument("--list", action="store_true", help="List all available database snapshots")
    parser.add_argument("--restore", type=str, metavar="PATH", help="Restore database from snapshot folder or 'latest'")

    args = parser.parse_args()

    if args.backup:
        create_backup()
    elif args.list:
        list_backups()
    elif args.restore:
        restore_backup(args.restore)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
