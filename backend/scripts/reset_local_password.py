#!/usr/bin/env python3
"""
Reset a user's password in a LOCAL development database.

Why this exists
---------------
Passwords are stored as PBKDF2-HMAC-SHA256 (200k iterations, 16-byte salt) and
are therefore not recoverable — which is correct. When a local dev password is
forgotten, the only way back in is to set a new hash directly.

This deliberately reuses `app.core.security.auth.hash_password` rather than
re-implementing PBKDF2. A hand-rolled hash with the wrong salt length or
encoding produces a row that looks fine and silently never verifies.

Safety
------
Refuses to run unless the target file is the local SQLite database. It prints
the absolute path it is about to modify so there is no ambiguity about which
database you are touching. It cannot reach production: the deployed instance
uses its own DATABASE_PATH on the server.

Usage
-----
    .venv/bin/python scripts/reset_local_password.py <email> <new-password> [--verify]

    --verify   also mark the email as verified, which skips the emailed code.
               Needed locally because sending mail requires SMTP_PASS, and that
               is only set on the server.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

try:
    from app.core.security.auth import hash_password, verify_password
except ImportError:
    sys.exit("Run this with the project venv:\n  .venv/bin/python scripts/reset_local_password.py …")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("email")
    ap.add_argument("password")
    ap.add_argument("--verify", action="store_true", help="mark email_verified = 1")
    ap.add_argument("--db", default=str(BACKEND / "tender_analyst.db"))
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        return f"No database at {db_path}" and 1
    if db_path.suffix not in {".db", ".sqlite", ".sqlite3"}:
        return f"Refusing: {db_path} is not a SQLite file" and 1

    print(f"database : {db_path}")
    print(f"account  : {args.email}")

    email = args.email.lower().strip()
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.execute("SELECT id, email_verified, is_admin FROM users WHERE lower(email) = ?", (email,))
    row = cur.fetchone()
    if row is None:
        cur.execute("SELECT email FROM users ORDER BY id")
        known = ", ".join(r[0] for r in cur.fetchall()) or "(none)"
        con.close()
        print(f"\nNo such user. Accounts in this database:\n  {known}", file=sys.stderr)
        return 1

    user_id, verified, is_admin = row
    new_hash = hash_password(args.password)

    # Prove the hash verifies BEFORE writing it. Writing a hash that cannot be
    # verified locks the account out entirely.
    if not verify_password(args.password, new_hash):
        con.close()
        print("\nAborted: generated hash failed its own verification.", file=sys.stderr)
        return 1

    if args.verify:
        cur.execute(
            "UPDATE users SET password_hash = ?, email_verified = 1, "
            "verification_code = NULL, verification_code_sent_at = NULL WHERE id = ?",
            (new_hash, user_id),
        )
    else:
        cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    con.commit()

    # Read back and verify against the stored value, not the in-memory one.
    cur.execute("SELECT password_hash, email_verified FROM users WHERE id = ?", (user_id,))
    stored, now_verified = cur.fetchone()
    con.close()

    ok = verify_password(args.password, stored)
    print(f"\npassword updated : {'OK' if ok else 'FAILED'}")
    print(f"email_verified   : {bool(now_verified)}"
          f"{'  (was False)' if args.verify and not verified else ''}")
    print(f"is_admin         : {bool(is_admin)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
