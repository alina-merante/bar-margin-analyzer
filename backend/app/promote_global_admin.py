import argparse
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine
from app.models import User


def promote_global_admin(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None or not user.is_active:
        raise ValueError("The user does not exist or is inactive.")
    if user.is_global_admin:
        raise ValueError("The user is already a global administrator.")
    user.is_global_admin = True
    db.flush()
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote an existing active user.")
    parser.add_argument("user_id", type=int)
    args = parser.parse_args()
    if args.user_id < 1:
        parser.error("user_id must be positive")
    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL must explicitly identify the target database.", file=sys.stderr)
        return 1

    with Session(engine) as db:
        user = db.get(User, args.user_id)
        if user is None or not user.is_active or user.is_global_admin:
            print("User not found, inactive, or already a global administrator.", file=sys.stderr)
            return 1
        email = user.email
        print(
            f"Target database: driver={engine.url.drivername}, "
            f"host={engine.url.host}, port={engine.url.port}, database={engine.url.database}"
        )
        print(f"Promote user {user.id} ({email}) to global administrator.")
        if input(f"Type PROMOTE {user.id} to confirm: ") != f"PROMOTE {user.id}":
            print("Promotion cancelled.", file=sys.stderr)
            return 1
        db.expire_all()
        try:
            user = promote_global_admin(db, args.user_id)
            if user.email != email:
                raise ValueError("The user changed during confirmation.")
            db.commit()
        except ValueError as exc:
            db.rollback()
            print(str(exc), file=sys.stderr)
            return 1
    print("Global administrator promoted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
