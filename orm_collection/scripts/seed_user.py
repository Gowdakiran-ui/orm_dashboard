"""Create (or update) a login user and grant them access to one or more
clients (TASK_AUTH.md fix #1/#4). Standalone script, not an API endpoint --
there's no self-service signup by design (out of scope: see TASK_AUTH.md's
"Out of scope" list), so provisioning a user is an operator action.

Also the intended way to seed the 3 real super_admin accounts (TASK_ROLES.md)
once their real emails/passwords are supplied -- this script deliberately
does not invent placeholder people or fake emails itself; run it manually
with --role super_admin when those credentials are actually provided.

Usage:
    python scripts/seed_user.py --email you@example.com --password 'S3cret!' --all-clients
    python scripts/seed_user.py --email you@example.com --password 'S3cret!' --client-id <uuid> [--client-id <uuid> ...]
    python scripts/seed_user.py --email admin@example.com --password 'S3cret!' --role super_admin
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.user import ROLE_CLIENT_USER, ROLE_SUPER_ADMIN, User, UserClientAccess  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", choices=[ROLE_SUPER_ADMIN, ROLE_CLIENT_USER], default=ROLE_CLIENT_USER)
    parser.add_argument("--client-id", action="append", default=[], help="Grant access to this client_id (repeatable)")
    parser.add_argument("--all-clients", action="store_true", help="Grant access to every existing client")
    args = parser.parse_args()

    email = args.email.strip().lower()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.password_hash = hash_password(args.password)
            user.role = args.role
            user.is_active = True
            print(f"[seed_user] Updated password/role ({args.role}) for existing user {email} ({user.id})")
        else:
            user = User(email=email, password_hash=hash_password(args.password), role=args.role, is_active=True)
            db.add(user)
            db.flush()
            print(f"[seed_user] Created {args.role} user {email} ({user.id})")

        if args.role == ROLE_SUPER_ADMIN:
            # super_admin sees every client by design (require_client_access's
            # bypass) -- explicit user_client_access grants are meaningless
            # for this role, so skip creating any even if --client-id/--all-clients
            # were passed alongside --role super_admin.
            db.commit()
            print("[seed_user] role=super_admin sees every client automatically -- no client grants created.")
            return 0

        if args.all_clients:
            client_ids = [c.id for c in db.query(Client.id).all()]
        else:
            client_ids = [c for c in args.client_id]

        granted = 0
        for client_id in client_ids:
            exists = db.query(UserClientAccess).filter(
                UserClientAccess.user_id == user.id,
                UserClientAccess.client_id == client_id,
            ).first()
            if not exists:
                db.add(UserClientAccess(user_id=user.id, client_id=client_id))
                granted += 1

        db.commit()
        print(f"[seed_user] Granted access to {granted} new client(s) (total requested: {len(client_ids)})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
