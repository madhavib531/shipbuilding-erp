"""Create a user account from the command line (use it for the first admin).

    python scripts/create_user.py --username admin --name "Maya Chen" --role Admin

The password is asked for twice and never echoed or written anywhere except as an scrypt hash. The account is
created in the database named by DATABASE_URL (backend/.env), which must already be migrated (`alembic upgrade head`).
"""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.user import UserRole  # noqa: E402
from app.services import auth_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--username", required=True)
    parser.add_argument("--name", required=True, help="Display name recorded on every change")
    parser.add_argument("--role", required=True, choices=[r.value for r in UserRole])
    parser.add_argument("--email")
    args = parser.parse_args()

    password = getpass.getpass(f"Password for {args.username} (at least {auth_service.MIN_PASSWORD_LENGTH} characters): ")
    if password != getpass.getpass("Repeat the password: "):
        print("The passwords do not match; nothing was created.")
        return 1
    with SessionLocal() as db:
        try:
            user = auth_service.create_user(db, args.username, args.name, UserRole(args.role), password, args.email)
        except Exception as exc:  # noqa: BLE001 - report the reason (taken username, short password)
            print(f"Not created: {getattr(exc, 'detail', exc)}")
            return 1
    print(f"Created {user.role.value} {user.username!r} ({user.display_name}). Sign in with this username.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
