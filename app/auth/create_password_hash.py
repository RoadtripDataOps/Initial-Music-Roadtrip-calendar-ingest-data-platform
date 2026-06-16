from __future__ import annotations

import argparse

from app.auth.passwords import create_password_hash


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an ADMIN_PASSWORD_HASH value.",
    )
    parser.add_argument("password", help="Admin password to hash.")
    args = parser.parse_args()
    print(create_password_hash(args.password))


if __name__ == "__main__":
    main()
