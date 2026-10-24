"""Operational commands: python -m app.cli create-admin | check-config | generate-keys"""
from __future__ import annotations

import argparse
import getpass
import sys


def create_admin(email: str, name: str | None, org: str | None) -> int:
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.exceptions import ValidationFailure
    from app.db.session import session_scope
    from app.models.auth import User
    from app.services.auth.service import create_user_with_org

    password = getpass.getpass("Password (min 8 chars, mixed case, a digit): ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1
    with session_scope() as db:
        if db.scalar(select(User.id).where(User.email == email.lower())):
            print("A user with that email already exists.", file=sys.stderr)
            return 1
        try:
            create_user_with_org(db, email=email, password=password, display_name=name, org_name=org or get_settings().initial_org_name)
        except ValidationFailure as e:
            print(f"Cannot create user: {e.message}", file=sys.stderr)
            return 1
    print(f"Administrator {email.lower()} created.")
    return 0


def purge_unrelated(confirm: bool) -> int:
    """Delete stored copies of mail that is not recruitment-related and not linked to any requirement. Gmail itself is never touched."""
    from sqlalchemy import delete, exists, func, select

    from app.db.session import session_scope
    from app.models.email import EmailMessage
    from app.models.requirements import RequirementSource

    with session_scope() as db:
        cond = (~exists().where(RequirementSource.email_message_id == EmailMessage.id), EmailMessage.processing_status.in_(["no_requirement", "ignored"]))
        n = db.scalar(select(func.count()).select_from(EmailMessage).where(*cond)) or 0
        if not confirm:
            print(f"{n} unrelated stored message(s) would be deleted. Re-run with --yes to delete them.")
            return 0
        db.execute(delete(EmailMessage).where(*cond))
        print(f"Deleted {n} unrelated stored message(s).")
    return 0


def cleanup_own_exports_cmd(confirm: bool, delete: bool = False) -> int:
    from app.db.session import session_scope
    from app.services.gmail.cleanup import cleanup_own_exports

    with session_scope() as db:
        r = cleanup_own_exports(db, apply=confirm)
    for d in r.details:
        print("  own export/digest:", d)
    from app.services.gmail.cleanup import delete_flagged_copies

    with session_scope() as db:
        flagged = delete_flagged_copies(db, apply=confirm and delete)
    for f in flagged:
        print("  flagged copy:", f)
    print(f"{'Deleted' if confirm and delete else 'Would delete with --delete'}: {len(flagged)} previously flagged requirement copy(ies).")
    verb = "Removed" if confirm else "Would remove"
    print(f"{verb}: {r.messages} message(s), {r.sources_removed} source link(s); archive {r.requirements_archived} requirement(s) that existed only because of them; dismiss {r.candidates_dismissed} duplicate review(s).")
    if not confirm:
        print("Dry run. Re-run with --yes to apply.")
    return 0


def demo_candidates_cmd(confirm: bool, org_name: str | None) -> int:
    """DEMO ONLY: create 3-5 clearly marked dummy candidates for every active requirement."""
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.models.auth import Organization, OrganizationMembership
    from app.models.requirements import JobRequirement
    from app.services.candidates import demo

    with session_scope() as db:
        orgs = list(db.scalars(select(Organization)))
        if org_name:
            orgs = [o for o in orgs if o.name == org_name]
        for org in orgs:
            if not db.scalar(select(JobRequirement.id).where(JobRequirement.organization_id == org.id).limit(1)):
                continue
            owner = db.scalar(select(OrganizationMembership.user_id).where(OrganizationMembership.organization_id == org.id).order_by(OrganizationMembership.created_at))
            r = demo.seed(db, org.id, owner, apply=confirm)
            print(f"{org.name}: {r['requirements']} requirement(s) -> {'created' if confirm else 'would create'} {r['created']} demo candidate(s), {r['skipped_existing']} already present, {r['pipeline_entries']} pipeline entries")
        if not confirm:
            print("Dry run. Re-run with --yes to create them. Remove later with: python -m app.cli purge-demo-candidates --yes")
    return 0


def purge_demo_candidates_cmd(confirm: bool) -> int:
    from app.db.session import session_scope
    from app.services.candidates import demo

    with session_scope() as db:
        n = demo.purge(db, apply=confirm)
    print(f"{'Deleted' if confirm else 'Would delete'} {n} demo candidate(s) (source=demo, @{demo.DEMO_DOMAIN}).{'' if confirm else ' Re-run with --yes.'}")
    return 0


def send_digest_now() -> int:
    """Run the scheduled-email check once (what the scheduler does every 10 minutes) and print the outcome per organization."""
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.models.ops import AppSetting
    from app.services.app_settings import DigestSettings
    from app.services.delivery.digest import digest_schedule

    with session_scope() as db:
        rows = list(db.scalars(select(AppSetting).where(AppSetting.section == "digest")))
        if not rows:
            print("Scheduled email is not configured (Settings > Scheduled email).")
        for row in rows:
            for sched in DigestSettings.model_validate(row.value).schedules:
                print(f"{sched.name} ({sched.id}): {digest_schedule(db, row.organization_id, sched)}")
    return 0


def check_config() -> int:
    from app.core.config import get_settings

    s = get_settings()
    problems = s.configuration_problems()
    print(f"environment={s.app_env} ai_provider={s.ai_provider} ai_configured={s.ai_configured} google_configured={s.google_configured}")
    for p in problems:
        print(f"PROBLEM: {p}")
    return 1 if problems else 0


def generate_keys() -> int:
    import secrets

    from cryptography.fernet import Fernet

    print(f"SECRET_KEY={secrets.token_urlsafe(48)}")
    print(f"ENCRYPTION_KEY={Fernet.generate_key().decode()}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--name")
    a.add_argument("--org")
    pu = sub.add_parser("purge-unrelated")
    pu.add_argument("--yes", action="store_true", help="actually delete (otherwise only counts)")
    co = sub.add_parser("cleanup-own-exports")
    co.add_argument("--yes", action="store_true")
    co.add_argument("--delete", action="store_true", help="also permanently delete requirement copies flagged by an earlier cleanup")
    dc = sub.add_parser("seed-demo-candidates")
    dc.add_argument("--yes", action="store_true")
    dc.add_argument("--org")
    pdc = sub.add_parser("purge-demo-candidates")
    pdc.add_argument("--yes", action="store_true")
    sub.add_parser("send-digest-now")
    sub.add_parser("check-config")
    sub.add_parser("generate-keys")
    args = p.parse_args()
    if args.cmd == "send-digest-now":
        return send_digest_now()
    if args.cmd == "create-admin":
        return create_admin(args.email, args.name, args.org)
    if args.cmd == "seed-demo-candidates":
        return demo_candidates_cmd(args.yes, args.org)
    if args.cmd == "purge-demo-candidates":
        return purge_demo_candidates_cmd(args.yes)
    if args.cmd == "cleanup-own-exports":
        return cleanup_own_exports_cmd(args.yes, args.delete)
    if args.cmd == "purge-unrelated":
        return purge_unrelated(args.yes)
    return check_config() if args.cmd == "check-config" else generate_keys()


if __name__ == "__main__":
    raise SystemExit(main())
