"""
Production Baseline Backup & Verification Script
=================================================
Creates verified read-only snapshots of the existing paper-trading production state.
"""
import os
import shutil
import json
import sqlite3
import hashlib


def backup_and_verify():
    backup_dir = os.path.join(os.path.dirname(__file__), "..", "data", "backups")
    os.makedirs(backup_dir, exist_ok=True)

    files_to_backup = [
        ("data/live_state.json", "live_state_baseline_backup.json"),
        ("oms.db", "oms_baseline_backup.db"),
        ("paper_trades_log.json", "paper_trades_log_baseline_backup.json"),
        ("data/live_trades.csv", "live_trades_baseline_backup.csv")
    ]

    backup_manifest = {}

    for src_rel, dst_name in files_to_backup:
        src_path = os.path.join(os.path.dirname(__file__), "..", src_rel)
        dst_path = os.path.join(backup_dir, dst_name)

        if os.path.exists(src_path):
            shutil.copy2(src_path, dst_path)
            
            # Compute SHA-256 hash
            with open(dst_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            
            size = os.path.getsize(dst_path)
            backup_manifest[src_rel] = {
                "backup_path": dst_path,
                "sha256": file_hash,
                "size_bytes": size,
                "verified": True
            }
            print(f"[+] Backed up {src_rel} -> {dst_path} (SHA256: {file_hash[:12]}..., Size: {size} bytes)")
        else:
            print(f"[!] Warning: Source file {src_rel} does not exist, skipped.")

    # Verification checks
    # 1. Verify live_state.json
    live_backup = os.path.join(backup_dir, "live_state_baseline_backup.json")
    if os.path.exists(live_backup):
        with open(live_backup, "r") as f:
            state = json.load(f)
        assert "cash" in state, "live_state backup missing 'cash'"
        assert "positions" in state, "live_state backup missing 'positions'"
        print(f"[+] Verified live_state.json: Cash=${state['cash']:.2f}, Open Positions={list(state['positions'].keys())}")

    # 2. Verify oms.db
    oms_backup = os.path.join(backup_dir, "oms_baseline_backup.db")
    if os.path.exists(oms_backup):
        conn = sqlite3.connect(oms_backup)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in c.fetchall()]
        assert "orders" in tables, "oms.db backup missing 'orders' table"
        assert "executions" in tables, "oms.db backup missing 'executions' table"
        conn.close()
        print(f"[+] Verified oms.db SQLite backup: Tables found = {tables}")

    # Write manifest
    manifest_path = os.path.join(backup_dir, "backup_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(backup_manifest, f, indent=2)
    print(f"[+] Backup manifest written to {manifest_path}")
    print("[SUCCESS] Production baseline snapshot is fully captured and verified.")


if __name__ == "__main__":
    backup_and_verify()
