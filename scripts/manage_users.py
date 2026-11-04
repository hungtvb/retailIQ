"""Create local Analyst/Manager accounts without exposing credentials.

Usage: python -m scripts.manage_users create --username analyst01 --role analyst
"""
from __future__ import annotations

import argparse
from getpass import getpass

from retailiq.infrastructure.auth import create_local_user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision a local RetailIQ user")
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create", help="Create a local operator-provisioned account")
    create.add_argument("--username", required=True)
    create.add_argument("--role", required=True, choices=("analyst", "manager"))
    args = parser.parse_args(argv)
    if args.action == "create":
        password = getpass("New password: ")
        confirmed = getpass("Repeat password: ")
        if not password or password != confirmed:
            parser.error("Passwords do not match")
        try:
            user_id = create_local_user(args.username, args.role, password)
        except ValueError as exc:
            parser.error(str(exc))
        print(f"Created local {args.role} account: {args.username} (id {user_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
