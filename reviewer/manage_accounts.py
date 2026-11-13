"""Operator-only account management. Run inside the app's environment."""

import argparse
import os
from pathlib import Path

from .accounts import Accounts
from .auth import AuthConfig, invitation_link, normalize_email
from .database import Database


def main():
    parser = argparse.ArgumentParser(
        description="Manage invite-only reviewer accounts. Links are secrets: share privately after verifying identity."
    )
    parser.add_argument("action", choices=["invite", "reset", "disable", "promote"])
    parser.add_argument("email")
    parser.add_argument(
        "--admin",
        action="store_true",
        help="Give a newly invited account app-admin permissions.",
    )
    args = parser.parse_args()
    try:
        config = AuthConfig.from_env()
        if config is None:
            parser.error("Configure WARREN_PUBLIC_URL before managing accounts.")
        email = normalize_email(args.email)
        data = (
            Path(
                os.getenv(
                    "WARREN_DATA_DIR", Path(__file__).resolve().parents[1] / "data"
                )
            )
            / "reviewer"
        )
        data.mkdir(parents=True, exist_ok=True)
        accounts = Accounts(Database(data / "reviewer.sqlite3"))
        if args.action == "promote":
            accounts.promote(email)
            print("App-admin permissions granted.")
        elif args.action == "disable":
            accounts.disable(email)
            print("Account disabled and all access links/sessions revoked.")
        else:
            token = (
                accounts.invite(email, admin=args.admin)
                if args.action == "invite"
                else accounts.recovery(email)
            )
            if not token:
                parser.error("No active account is eligible for recovery.")
            print("Private single-use link (do not paste in tickets or public logs):")
            print(
                invitation_link(
                    config, token, "invite" if args.action == "invite" else "recovery"
                )
            )
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
