import sys
import hashlib

from pathlib import Path
from datetime import date
from decimal import Decimal
from getpass import getpass

from sqlalchemy import text, select
from sqlalchemy.orm import Session

from test_database import get_test_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models import (
    Bar,
    User,
    UserBarMembership,
    MembershipRole,
    Document,
    DailyCashClosure,
    CashClosureIntake,
)

from app.models.membership_permission import MembershipPermission
from app.security import hash_password
from app.permissions import DelegablePermission


engine = get_test_engine()

emails = [
    "at-staff@barmanager.test",
    "at-admin@barmanager.test",
    "at-owner@barmanager.test",
]

permission = DelegablePermission("cash_closures.view_all").value

password = getpass("Password per i tre nuovi account di test: ")

assert len(password) >= 12, "Usare almeno 12 caratteri"

password_hash = hash_password(password)

with Session(engine) as db:
    with db.begin():

        assert db.execute(
            text("SELECT current_database()")
        ).scalar_one() == "bar_margin_analyzer_pwa_test"

        primary = db.scalars(
            select(Bar).where(
                Bar.name == "Bar Demo PWA",
                Bar.is_active.is_(True)
            )
        ).one()

        assert primary.id == 4

        existing_bar = db.scalar(
            select(Bar).where(
                Bar.name == "AT-Bar Secondario"
            )
        )

        assert existing_bar is None, "Secondo bar gia presente"

        existing_users = db.scalars(
            select(User).where(User.email.in_(emails))
        ).all()

        assert not existing_users, "Account test gia presenti"

        secondary = Bar(
            name="AT-Bar Secondario",
            is_active=True
        )

        staff = User(
            email=emails[0],
            password_hash=password_hash,
            is_global_admin=False
        )

        admin = User(
            email=emails[1],
            password_hash=password_hash,
            is_global_admin=True
        )

        owner = User(
            email=emails[2],
            password_hash=password_hash,
            is_global_admin=False
        )

        db.add_all([secondary, staff, admin, owner])
        db.flush()

        staff_membership = UserBarMembership(
            user_id=staff.id,
            bar_id=primary.id,
            role=MembershipRole.staff
        )

        db.add_all([
            staff_membership,
            UserBarMembership(
                user_id=owner.id,
                bar_id=primary.id,
                role=MembershipRole.owner
            ),
            UserBarMembership(
                user_id=owner.id,
                bar_id=secondary.id,
                role=MembershipRole.owner
            )
        ])

        db.flush()

        db.add(
            MembershipPermission(
                membership_id=staff_membership.id,
                permission=permission
            )
        )

        filename = "AT-CASH-D.png"

        document = Document(
            bar_id=secondary.id,
            month="2026-11",
            original_filename=filename,
            stored_filename=filename,
            section="cash",
            document_type="PNG",
            category="Immagine",
            result="Acceptance test isolamento",
            file_url=f"/uploads/documents/{filename}",
            preview_url=f"/uploads/documents/{filename}",
            status="Elaborato"
        )

        db.add(document)
        db.flush()

        closure = DailyCashClosure(
            bar_id=secondary.id,
            document_id=document.id,
            date=date(2026, 11, 24),
            closure_number="AT-CASH-D",
            total_amount=Decimal("940.00"),
            cash_amount=Decimal("340.00"),
            card_amount=Decimal("600.00"),
            receipts_count=100
        )

        db.add(closure)
        db.flush()

        intake = CashClosureIntake(
            bar_id=secondary.id,
            document_id=document.id,
            closure_id=closure.id,
            source_sha256=hashlib.sha256(
                b"AT-CASH-D"
            ).hexdigest(),
            classification="SAVE_FOR_REVIEW",
            status="approved",
            date=date(2026, 11, 24),
            closure_number="AT-CASH-D",
            total_amount=Decimal("940.00"),
            cash_amount=Decimal("340.00"),
            card_amount=Decimal("600.00"),
            ocr_values={},
            anomalies=[]
        )

        db.add(intake)
        db.flush()

        print("BAR PRINCIPALE:", primary.id)
        print("BAR SECONDARIO:", secondary.id)
        print("STAFF:", staff.id)
        print("ADMIN:", admin.id)
        print("OWNER MULTIBAR:", owner.id)
        print("DOCUMENTO D:", document.id)
        print("CHIUSURA D:", closure.id)
        print("INTAKE D:", intake.id)

print("FIXTURE ACCESS CONTROL CREATE")
