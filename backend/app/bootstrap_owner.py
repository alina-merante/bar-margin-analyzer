import getpass
import re
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Bar, MembershipRole, User, UserBarMembership
from app.security import hash_password

LEGACY_BAR_ID = -1
LEGACY_BAR_NAME = "Bar Legacy"


class BootstrapError(RuntimeError):
    pass


def bootstrap_owner(
    db: Session,
    email: str,
    password: str,
    bar_name: str,
) -> tuple[int, int]:
    normalized_email = email.strip().lower()
    normalized_bar_name = bar_name.strip()
    if (
        not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized_email)
        or not normalized_bar_name
    ):
        raise BootstrapError("Email and bar name are required.")
    if len(normalized_bar_name) > 255:
        raise BootstrapError("Bar name must contain at most 255 characters.")

    if db.scalar(select(User.id).limit(1)) is not None:
        raise BootstrapError("Bootstrap refused: users already exist.")

    legacy_bar = db.get(Bar, LEGACY_BAR_ID)
    if legacy_bar is not None:
        if legacy_bar.name != LEGACY_BAR_NAME:
            raise BootstrapError(
                f"Bootstrap refused: reserved bar id {LEGACY_BAR_ID} "
                "belongs to an unexpected bar."
            )
        if db.scalar(
            select(Bar.id).where(Bar.id != LEGACY_BAR_ID).limit(1)
        ) is not None:
            raise BootstrapError(
                "Bootstrap refused: additional bars exist alongside the legacy "
                "bar; review the data before bootstrapping."
            )
        bar = legacy_bar
    else:
        if db.scalar(select(Bar.id).limit(1)) is not None:
            raise BootstrapError(
                "Bootstrap refused: bars already exist without the expected "
                "legacy bar; review the data before bootstrapping."
            )
        bar = Bar(name=normalized_bar_name)
        db.add(bar)
        db.flush()

    user = User(email=normalized_email, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    db.add(
        UserBarMembership(
            user_id=user.id,
            bar_id=bar.id,
            role=MembershipRole.owner,
        )
    )
    db.flush()
    return user.id, bar.id


def main() -> int:
    email = input("Owner email: ")
    password = getpass.getpass("Owner password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        print("Bootstrap refused: passwords do not match.", file=sys.stderr)
        return 1
    bar_name = input("Bar name: ")

    connection = engine.connect()
    try:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        elif connection.dialect.name == "postgresql":
            connection.exec_driver_sql(
                "LOCK TABLE users, bars IN EXCLUSIVE MODE"
            )
        with Session(bind=connection) as db:
            try:
                user_id, bar_id = bootstrap_owner(db, email, password, bar_name)
                db.flush()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        print(f"Bootstrap complete. Owner id: {user_id}; bar id: {bar_id}.")
        if bar_id == LEGACY_BAR_ID:
            print(
                f"Existing {LEGACY_BAR_NAME} was reused without changing its name; "
                "the supplied bar name was not used."
            )
        return 0
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("Bootstrap failed; no data was committed.", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
