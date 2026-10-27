"""End-to-end backend workflow with fake Gmail + mock AI: sync -> classify -> extract -> dedup -> review."""
from sqlalchemy import func, select

from app.integrations.gmail_client import GmailAuthError, GmailTransient
from app.models.email import EmailAttachment, EmailMessage
from app.models.ops import ExtractionRun, ProcessingJob
from app.models.requirements import DuplicateCandidate, JobRequirement, RequirementSource
from app.services.extraction.providers import AIAuthError, AITransientError
from tests.fakes import JD_BODY, gmail_message
from tests.helpers import globex_requirement, jd_message, sync, use_ai

API = "/api/v1"


def count(db, model):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model))


def test_full_vertical_slice_and_idempotent_resync(api, db, connected_account, mailbox):
    a = connected_account("acct1@gmail.com")
    box = mailbox.for_email("acct1@gmail.com")
    box.add(jd_message("aaaa0001"))
    box.add(gmail_message("aaaa0002", "Weekly newsletter", "Unsubscribe from our newsletter, 50% off sale", sender="Shop <no-reply@shop.com>"))
    use_ai(globex_requirement())

    job = sync(api, a.id)
    assert job["status"] == "queued" and not job["already_running"]

    db.expire_all()
    j = db.scalar(select(ProcessingJob))
    assert j.status == "completed" and j.stats["stored"] == 1 and j.stats["skipped_unrelated"] == 1 and j.progress == 1.0
    msgs = {m.gmail_message_id: m for m in db.scalars(select(EmailMessage))}
    assert msgs["aaaa0001"].processing_status == "processed" and msgs["aaaa0001"].classification == "new_requirement"
    assert "aaaa0002" not in msgs  # clearly unrelated mail (a newsletter) is never stored
    req = db.scalar(select(JobRequirement))
    assert (req.client_name, req.job_title, req.job_reference_id) == ("Globex Corporation", "Senior Python Developer", "GX-1042")
    assert req.required_skills == ["AWS", "Django", "PostgreSQL", "Python"] and req.preferred_skills == ["Kubernetes", "Terraform"]
    assert req.review_status == "needs_review" and req.location == "Bangalore, India"
    assert [s.email_message_id for s in req.sources] == [msgs["aaaa0001"].id]
    assert db.get(type(a), a.id).last_synced_at is not None and a.sync_state.gmail_history_id

    # Re-running sync (and reprocessing) must not create duplicates
    sync(api, a.id)
    sync(api, a.id, mode="full")
    from app.tasks.runner import process_email_impl

    process_email_impl(str(msgs["aaaa0001"].id), True)  # reprocess with the current configuration
    assert count(db, EmailMessage) == 1 and count(db, JobRequirement) == 1 and count(db, RequirementSource) == 1


def test_pagination_checkpoint_resume_after_transient_failure(api, db, connected_account, mailbox):
    a = connected_account("acct1@gmail.com")
    box = mailbox.for_email("acct1@gmail.com")
    box.page_size = 2
    for i in range(5):
        box.add(jd_message(f"bbbb000{i}", subject=f"Job {i} requirement", body=JD_BODY.replace("GX-1042", f"GX-{i}00")))
    use_ai()  # canned empty result: only sync behaviour matters
    box.fail_get["bbbb0003"] = GmailTransient("503")  # page 2 fails after page 1 was checkpointed
    sync(api, a.id)
    db.expire_all()
    j = db.scalar(select(ProcessingJob))
    assert j.status == "queued" and j.checkpoint["page_token"] == "2" and "Temporary error" in j.error_summary
    assert count(db, EmailMessage) == 2  # page 1 persisted
    # worker retry (what Celery does): the job resumes from its checkpoint
    del box.fail_get["bbbb0003"]
    from app.tasks.runner import sync_account_impl

    box.calls.clear()
    sync_account_impl(str(j.id))
    db.expire_all()
    assert db.get(ProcessingJob, j.id).status == "completed" and count(db, EmailMessage) == 5
    assert "get:bbbb0000" not in box.calls  # already stored messages were not refetched


def test_retries_are_bounded_then_job_fails_visibly(api, db, connected_account, mailbox):
    from app.services.gmail.sync import RetryableSyncError, run_sync_job

    a = connected_account("acct1@gmail.com")
    box = mailbox.for_email("acct1@gmail.com")
    box.fail_list = GmailTransient("503")
    j = sync(api, a.id)
    from app.tasks.runner import sync_account_impl

    for _ in range(4):
        try:
            sync_account_impl(j["job_id"])
        except RetryableSyncError:
            pass
    db.expire_all()
    job = db.scalar(select(ProcessingJob))
    assert job.status == "failed" and job.attempts == job.max_attempts and "Gave up" in job.error_summary
    notif = api.get(f"{API}/notifications").json()
    assert any(n["kind"] == "sync_failed" for n in notif["items"])


def test_revoked_authorization_marks_account_expired_and_blocks_sync(api, db, connected_account, mailbox):
    a = connected_account("acct1@gmail.com")
    mailbox.for_email("acct1@gmail.com").fail_list = GmailAuthError("401")
    sync(api, a.id)
    db.expire_all()
    from app.models.email import EmailAccount

    acct = db.get(EmailAccount, a.id)
    assert acct.connection_status == "expired" and db.scalar(select(ProcessingJob)).status == "failed"
    r = api.post(f"{API}/email-accounts/{a.id}/sync")
    assert r.status_code == 409 and r.json()["error"]["code"] == "account_needs_reauth"


def test_history_cursor_expiry_falls_back_to_windowed_reconcile(api, db, connected_account, mailbox):
    a = connected_account("acct1@gmail.com")
    box = mailbox.for_email("acct1@gmail.com")
    box.add(jd_message("cccc0001"))
    use_ai()
    sync(api, a.id)
    box.add(jd_message("cccc0002", subject="Another requirement"))
    box.history_expired = True
    sync(api, a.id)  # incremental attempt -> expired -> full window
    db.expire_all()
    assert count(db, EmailMessage) == 2
    last = db.scalars(select(ProcessingJob).order_by(ProcessingJob.created_at.desc())).first()
    assert last.stats.get("history_expired") == 1 and last.status == "completed"


def test_incremental_sync_only_fetches_new_messages(api, db, connected_account, mailbox):
    a = connected_account("acct1@gmail.com")
    box = mailbox.for_email("acct1@gmail.com")
    box.add(jd_message("dddd0001"))
    use_ai()
    sync(api, a.id)
    box.add(jd_message("dddd0002", subject="Second req"))
    box.calls.clear()
    sync(api, a.id)
    assert "list" not in box.calls and box.calls == ["get:dddd0002"]
    assert count(db, EmailMessage) == 2


def test_cross_account_duplicate_emails_are_linked_not_reextracted(api, db, connected_account, mailbox):
    a1, a2 = connected_account("one@gmail.com"), connected_account("two@gmail.com")
    ai = use_ai(globex_requirement())
    mailbox.for_email("one@gmail.com").add(jd_message("eeee0001"))
    sync(api, a1.id)
    mailbox.for_email("two@gmail.com").add(jd_message("ffff0002"))  # same content, different mailbox + Gmail id
    sync(api, a2.id)
    db.expire_all()
    first, second = db.scalars(select(EmailMessage).order_by(EmailMessage.created_at)).all()
    assert second.duplicate_of_message_id == first.id and second.processing_status == "duplicate"
    assert ai.calls == 1  # no second AI call
    assert count(db, JobRequirement) == 1
    req = db.scalar(select(JobRequirement))
    assert {s.email_message_id for s in req.sources} == {first.id, second.id}
    r = api.get(f"{API}/requirements/{req.id}").json()
    assert sorted(r["source_accounts"]) == ["one@gmail.com", "two@gmail.com"] and r["source_count"] == 2


def test_reworded_duplicate_requirement_from_other_account_attaches_without_new_record(api, db, connected_account, mailbox):
    a1, a2 = connected_account("one@gmail.com"), connected_account("two@gmail.com")
    use_ai(globex_requirement())
    mailbox.for_email("one@gmail.com").add(jd_message("1111aaaa"))
    sync(api, a1.id)
    reworded = JD_BODY.replace("We have an urgent requirement.", "Forwarding an opening from our partner.").replace("jane@staffing.com", "bob@other-agency.com")
    use_ai(globex_requirement(recruiter_email="bob@other-agency.com", recruiter_name="Bob", salary_min=30, salary_max=40))
    mailbox.for_email("two@gmail.com").add(jd_message("2222bbbb", subject="Fwd: Opening - Sr Python Dev", body=reworded, sender="Bob <bob@other-agency.com>"))
    sync(api, a2.id)
    db.expire_all()
    assert count(db, JobRequirement) == 1 and count(db, RequirementSource) == 2 and count(db, DuplicateCandidate) == 0
    req = db.scalar(select(JobRequirement))
    # conflicting values are flagged for review, never silently overwritten
    assert req.salary_min == 25 and req.recruiter_email == "jane@staffing.com"
    assert any(w.startswith("conflict:") for w in req.validation_warnings)
    assert req.version_number >= 1


def test_probable_duplicate_creates_review_item_and_merge_preserves_sources(api, db, connected_account, mailbox):
    a1, a2 = connected_account("one@gmail.com"), connected_account("two@gmail.com")
    use_ai(globex_requirement(job_reference_id=None))
    mailbox.for_email("one@gmail.com").add(jd_message("3333aaaa", body=JD_BODY.replace("Job ID: GX-1042\n", "")))
    sync(api, a1.id)
    # second email: same client+title but a different location => same fingerprint is impossible, similarity decides
    body2 = JD_BODY.replace("Job ID: GX-1042\n", "").replace("Bangalore, India (Hybrid)", "Bangalore, India (Hybrid) / Pune").replace("urgent", "hot")
    use_ai(globex_requirement(job_reference_id=None, city="Bangalore / Pune", salary_max=36))
    mailbox.for_email("two@gmail.com").add(jd_message("4444bbbb", subject="Opening again", body=body2))
    sync(api, a2.id)
    db.expire_all()
    assert count(db, JobRequirement) == 2
    cand = db.scalar(select(DuplicateCandidate))
    assert cand is not None and cand.review_status == "pending" and cand.matching_score >= 0.72

    listing = api.get(f"{API}/duplicates").json()
    assert listing["total"] == 1
    detail = api.get(f"{API}/duplicates/{cand.id}").json()
    assert len(detail["sources_a"]) == 1 and len(detail["sources_b"]) == 1 and detail["matching_reasons"]

    survivor = detail["requirement_a"]["id"]
    r = api.post(f"{API}/duplicates/{cand.id}/merge", json={"survivor_id": survivor})
    assert r.status_code == 200 and r.json()["review_status"] == "merged"
    merged = api.get(f"{API}/requirements/{survivor}").json()
    assert merged["source_count"] == 2 and sorted(merged["source_accounts"]) == ["one@gmail.com", "two@gmail.com"]
    loser = detail["requirement_b"]["id"]
    lr = api.get(f"{API}/requirements/{loser}").json()
    assert lr["lifecycle_status"] == "merged" and lr["merged_into_id"] == survivor  # nothing is deleted
    assert api.get(f"{API}/requirements").json()["total"] == 1  # merged records leave the working list
    assert api.post(f"{API}/duplicates/{cand.id}/merge", json={"survivor_id": survivor}).status_code == 409
    assert api.post(f"{API}/duplicates/{cand.id}/reopen").status_code == 409
    versions = api.get(f"{API}/requirements/{survivor}/versions").json()
    assert any(v["change_source"] == "merge" for v in versions)
    assert any(x["action"] == "duplicate.merged" for x in api.get(f"{API}/audit-logs").json()["items"])


def test_duplicate_review_actions_keep_both_related_dismiss_reopen(api, db, connected_account, mailbox):
    a1 = connected_account("one@gmail.com")
    use_ai(globex_requirement(job_reference_id=None))
    box = mailbox.for_email("one@gmail.com")
    box.add(jd_message("5555aaaa", body=JD_BODY.replace("Job ID: GX-1042\n", "")))
    sync(api, a1.id)
    use_ai(globex_requirement(job_reference_id=None, city="Bangalore / Pune", salary_max=36))
    box.add(jd_message("6666bbbb", subject="Resend", body=JD_BODY.replace("Job ID: GX-1042\n", "").replace("Regards", "Thanks").replace("(Hybrid)", "(Hybrid) / Pune")))
    sync(api, a1.id)
    cand = db.scalar(select(DuplicateCandidate))
    assert cand is not None
    for action, status in (("keep-both", "kept_both"), ("mark-related", "related"), ("dismiss", "dismissed")):
        assert api.post(f"{API}/duplicates/{cand.id}/{action}").json()["review_status"] == status
    assert api.post(f"{API}/duplicates/{cand.id}/reopen").json()["review_status"] == "pending"
    assert api.post(f"{API}/duplicates/{cand.id}/merge", json={"survivor_id": "00000000-0000-0000-0000-000000000000"}).status_code == 422


def test_different_job_ids_stay_separate_records(api, db, connected_account, mailbox):
    a = connected_account("one@gmail.com")
    box = mailbox.for_email("one@gmail.com")
    use_ai(globex_requirement())
    box.add(jd_message("7777aaaa"))
    sync(api, a.id)
    use_ai(globex_requirement(job_reference_id="GX-2000"))
    box.add(jd_message("8888bbbb", subject="Another opening", body=JD_BODY.replace("GX-1042", "GX-2000")))
    sync(api, a.id)
    db.expire_all()
    assert count(db, JobRequirement) == 2
    cand = db.scalar(select(DuplicateCandidate))
    assert cand is None or cand.review_status == "related"  # never a pending merge suggestion


def test_ai_not_configured_awaits_then_processes_when_available(api, db, connected_account, mailbox):
    a = connected_account("one@gmail.com")
    mailbox.for_email("one@gmail.com").add(jd_message("9999aaaa"))
    sync(api, a.id)
    db.expire_all()
    m = db.scalar(select(EmailMessage))
    assert m.processing_status == "awaiting_ai" and m.classification == "new_requirement" and "not configured" in m.error_summary
    assert count(db, JobRequirement) == 0
    # existing records remain usable without AI
    assert api.post(f"{API}/requirements", json={"job_title": "Manual role"}).status_code == 201
    use_ai(globex_requirement())
    assert api.post(f"{API}/emails/retry-failed").json()["queued"] == 1
    db.expire_all()
    assert db.scalar(select(EmailMessage)).processing_status == "processed" and count(db, JobRequirement) == 2


def test_permanent_ai_error_fails_without_retry_and_transient_is_retryable(api, db, connected_account, mailbox):
    a = connected_account("one@gmail.com")
    mailbox.for_email("one@gmail.com").add(jd_message("aaaa1111"))
    p = use_ai(error=AIAuthError("AI provider rejected the credentials"))
    sync(api, a.id)
    db.expire_all()
    m = db.scalar(select(EmailMessage))
    assert m.processing_status == "failed" and "credentials" in m.error_summary and p.calls == 1
    run = db.scalar(select(ExtractionRun))
    assert run.status == "failed" and run.error_code == "ai_auth"
    p2 = use_ai(error=AITransientError("503"))
    from app.tasks.runner import process_email_impl

    try:
        process_email_impl(str(m.id), True)
    except Exception:  # noqa: BLE001 - transient errors are re-raised so the queue can retry; state is persisted
        pass
    db.expire_all()
    assert db.scalar(select(EmailMessage)).processing_status == "failed" and "Temporary" in db.scalar(select(EmailMessage)).error_summary
    use_ai(globex_requirement())
    process_email_impl(str(m.id), True)
    db.expire_all()
    assert db.scalar(select(EmailMessage)).processing_status == "processed" and count(db, JobRequirement) == 1


def test_attachment_text_is_extracted_and_unsafe_files_are_quarantined(api, db, connected_account, mailbox):
    import io

    import docx

    d = docx.Document()
    d.add_paragraph("Client: Initech\nJob Title: Data Engineer\nJob ID: IN-77\nRequired Skills: Spark, Python")
    buf = io.BytesIO()
    d.save(buf)
    a = connected_account("one@gmail.com")
    box = mailbox.for_email("one@gmail.com")
    box.add(gmail_message("bbbb2222", "JD attached - hiring Data Engineer", "Hi, please find the job description attached. Send profiles.",
                          attachments=[("jd.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buf.getvalue()),
                                       ("resume.pdf", "application/pdf", b"MZ\x90\x00 not a pdf")]))
    from app.services.extraction.schema import ExtractedRequirement

    use_ai(ExtractedRequirement(client_name="Initech", job_title="Data Engineer", job_reference_id="IN-77", required_skills=["Spark", "Python"]))
    sync(api, a.id)
    db.expire_all()
    atts = {x.filename: x for x in db.scalars(select(EmailAttachment))}
    assert atts["jd.docx"].extraction_status == "extracted" and atts["jd.docx"].extracted_text_reference
    assert atts["resume.pdf"].extraction_status == "quarantined"
    req = db.scalar(select(JobRequirement))
    assert req.client_name == "Initech" and {s.source_type for s in req.sources} == {"email_body", "attachment"}


def test_only_recruitment_mail_is_kept_and_gmail_search_is_narrowed(api, db, connected_account, mailbox):
    from app.models.email import EmailAccount
    from app.services.gmail.sync import RECRUITMENT_TERMS, build_query

    q = build_query(30, "label:x")
    assert RECRUITMENT_TERMS in q and q.endswith("label:x") and "hiring" in q
    assert RECRUITMENT_TERMS not in build_query(30, None, recruitment_only=False)
    a = connected_account("one@gmail.com")
    box = mailbox.for_email("one@gmail.com")
    box.add(jd_message("cccc3333"))
    box.add(gmail_message("dddd4444", "Weekly newsletter", "Unsubscribe from our newsletter, 50% off sale", sender="Shop <no-reply@shop.com>"))
    box.add(gmail_message("eeee4444", "Invoice 123", "Your receipt for the purchase. Unsubscribe anytime.", sender="Billing <no-reply@store.com>"))
    use_ai(globex_requirement())
    sync(api, a.id)
    db.expire_all()
    stored = {m.gmail_message_id for m in db.scalars(select(EmailMessage))}
    assert stored == {"cccc3333"}  # nothing unrelated was persisted
    job = db.scalar(select(ProcessingJob))
    assert job.stats["skipped_unrelated"] == 2
    # the owner can opt out and keep everything (setting is per organization)
    assert api.put(f"{API}/settings/gmail", json={"values": {"only_recruitment_emails": False}}).status_code == 200
    sync(api, a.id, mode="full")
    db.expire_all()
    assert {m.gmail_message_id for m in db.scalars(select(EmailMessage))} >= {"cccc3333", "dddd4444", "eeee4444"}


def test_multi_job_email_and_closure_notice(api, db, connected_account, mailbox):
    a = connected_account("one@gmail.com")
    box = mailbox.for_email("one@gmail.com")
    two = JD_BODY + "\nClient: Initech\nJob Title: Data Engineer\nJob ID: IN-9\nRequired Skills: Python, Spark\n"
    box.add(jd_message("eeee5555", body=two))
    from app.services.extraction.schema import ExtractedRequirement

    use_ai(globex_requirement(), ExtractedRequirement(client_name="Initech", job_title="Data Engineer", job_reference_id="IN-9", required_skills=["Python", "Spark"]))
    sync(api, a.id)
    db.expire_all()
    assert count(db, JobRequirement) == 2
    box.add(gmail_message("ffff6666", "Update on GX-1042", "Hi, the position has been filled. Job ID: GX-1042 Client: Globex Corporation. Please ignore this requirement."))
    use_ai(globex_requirement(job_title=None, required_skills=[], preferred_skills=[], recruiter_email=None, recruiter_name=None, salary_min=None, salary_max=None,
                              salary_currency=None, salary_period=None, minimum_experience=None, maximum_experience=None, city=None, country=None, work_mode="unknown"),
           classification="job_closure")
    sync(api, a.id)
    db.expire_all()
    assert count(db, JobRequirement) == 2  # closure never creates a requirement
    gx = db.scalar(select(JobRequirement).where(JobRequirement.job_reference_id == "GX-1042"))
    assert "closure_notice_received" in gx.validation_warnings and gx.lifecycle_status == "active"  # flagged, not auto-closed


XLSX = ("requirements.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK fake workbook")


def test_own_exports_and_digests_are_never_extracted_again(api, db, connected_account, mailbox):
    """Regression: a digest of already-extracted jobs (with an Excel attachment) sent between your own accounts re-created every job."""
    from app.models.ops import EmailDelivery
    from app.services.delivery.service import build_mime

    a = connected_account("recv@gmail.com")
    connected_account("mine@gmail.com")  # another connected account of the same organization
    box = mailbox.for_email("recv@gmail.com")
    digest_body = JD_BODY + "\nClient: Initech\nJob Title: Data Engineer\nJob ID: IN-9\nRequired Skills: Python, Spark\n"
    # 1. a real requirement mail sent FROM one of your own accounts without a spreadsheet is still processed (legitimate use)
    box.add(jd_message("0a000001", sender="Me <mine@gmail.com>"))
    # 2. the same account's digest with an Excel attachment is skipped
    box.add(gmail_message("0a000002", "Open requirements: 10 positions", digest_body, sender="Me <mine@gmail.com>", attachments=[XLSX]))
    # 3. our own export is recognised by its header, even from an unknown sender address
    box.add(gmail_message("0a000003", "Weekly report", digest_body, sender="Other <someone@else.com>", extra_headers={"X-RecruitmentDesk-Export": "1"}))
    # 4. ... or by the Message-ID of a delivery we sent
    org_id = a.organization_id
    from app.models.ops import ExportJob

    exp = ExportJob(organization_id=org_id, filename="x.xlsx", options={}, filters={}, selected_record_ids=[], status="completed")
    db.add(exp)
    db.flush()
    db.add(EmailDelivery(organization_id=org_id, export_job_id=exp.id, recipient_addresses=["a@b.com"], cc_addresses=[], subject="s", rfc_message_id="<ours-123@x>", status="accepted_by_gmail"))
    db.commit()
    box.add(gmail_message("0a000004", "Fwd: Weekly report", digest_body, sender="Other <someone@else.com>", message_id="<ours-123@x>"))
    # 5. pure outgoing mail (SENT, never in INBOX) is not a requirement; self-forwarded mail (SENT+INBOX) still is
    box.add(gmail_message("0a000005", "Requirement follow-up sent by me", JD_BODY, labels=["SENT"], sender="Me <recv@gmail.com>"))
    box.add(gmail_message("0a000006", "Fwd: Hiring Python developer opening", JD_BODY.replace("GX-1042", "GX-77"), labels=["SENT", "INBOX"], sender="Me <recv@gmail.com>"))
    use_ai()
    sync(api, a.id)
    db.expire_all()
    stored = {m.gmail_message_id for m in db.scalars(select(EmailMessage))}
    assert stored == {"0a000001", "0a000006"}
    stats = db.scalar(select(ProcessingJob)).stats
    assert stats["skipped_own_digest_spreadsheet"] == 1 and stats["skipped_recruitmentdesk_export"] == 2 and stats["skipped_own_sent_only"] == 1


def test_our_outgoing_mail_carries_the_export_marker():
    from app.services.delivery.service import build_mime
    from app.services.gmail.mime import parse_gmail_message

    msg, _ = build_mime(sender="me@gmail.com", to=["a@example.com"], cc=[], subject="s", body="b", filename="r.xlsx", xlsx=b"PK")
    assert msg["X-RecruitmentDesk-Export"] == "1"
    raw = gmail_message("0b000001", "s", "b", extra_headers={"X-RecruitmentDesk-Export": "1"})
    assert parse_gmail_message(raw, 1000).exported_by_app is True and parse_gmail_message(gmail_message("0b000002", "s", "b"), 1000).exported_by_app is False


def test_cleanup_archives_requirements_created_only_from_own_digests(api, db, connected_account, mailbox):
    from app.models.email import EmailMessage as M
    from app.services.gmail.cleanup import cleanup_own_exports

    a = connected_account("recv@gmail.com")
    org_id, acct_id = a.organization_id, a.id
    connected_account("mine@gmail.com")
    box = mailbox.for_email("recv@gmail.com")
    box.add(jd_message("0c000001", sender="Recruiter <jane@staffing.com>"))
    use_ai(globex_requirement())
    sync(api, acct_id)
    db.rollback()  # end any read snapshot before writing from this session
    # simulate the old behaviour: a digest was stored and produced a duplicate-looking requirement before the rules existed
    from app.services.requirements import service as svc

    digest = M(organization_id=org_id, email_account_id=acct_id, gmail_message_id="0c000009", sender_email="mine@gmail.com", subject="Digest", recipients=[], labels=["SENT"],
               source_metadata={}, processing_status="processed")
    db.add(digest)
    db.flush()
    digest_id = digest.id
    bad = svc.create_requirement(db, org_id, {"job_title": "Copy", "client_name": "X"}, user_id=None, source="extraction")
    bad_id = bad.id
    svc.link_source(db, bad, digest_id, "email_body")
    db.commit()
    dry = cleanup_own_exports(db, apply=False)
    assert dry.messages == 1 and dry.requirements_archived == 1
    db.expire_all()
    assert db.get(M, digest_id) is not None  # dry run changes nothing
    rep = cleanup_own_exports(db, apply=True)
    db.commit()
    db.expire_all()
    assert rep.requirements_archived == 1 and db.get(M, digest_id) is None
    real = db.scalar(select(JobRequirement).where(JobRequirement.job_reference_id == "GX-1042"))
    assert real.lifecycle_status == "active"  # the genuine requirement is untouched
    assert db.get(JobRequirement, bad_id).lifecycle_status == "archived"


def test_messages_deleted_in_gmail_are_skipped_not_errors_and_real_failures_leave_samples(api, db, connected_account, mailbox, monkeypatch):
    from app.integrations.gmail_client import GmailNotFound
    from app.services.gmail import sync as sync_mod

    a = connected_account("one@gmail.com")
    box = mailbox.for_email("one@gmail.com")
    box.add(jd_message("0d000001"))
    box.add(jd_message("0d000002", subject="Opening 2", body=JD_BODY.replace("GX-1042", "GX-2")))
    box.add(jd_message("0d000003", subject="Opening 3", body=JD_BODY.replace("GX-1042", "GX-3")))
    box.fail_get["0d000002"] = GmailNotFound("gone")  # deleted between list and fetch
    real_store = sync_mod.store_message

    def flaky_store(db_, acct, parsed):
        if parsed.gmail_id == "0d000003":
            raise ValueError("boom while storing\nsecond line")
        return real_store(db_, acct, parsed)

    monkeypatch.setattr(sync_mod, "store_message", flaky_store)
    use_ai()
    sync(api, a.id)
    db.expire_all()
    job = db.scalar(select(ProcessingJob))
    assert job.status == "completed_with_errors" and job.stats["stored"] == 1
    assert job.stats["skipped_missing"] == 1 and job.stats["message_errors"] == 1  # only the real failure counts as an error
    assert job.checkpoint["error_samples"] == ["0d000003: ValueError: boom while storing"] and "could not be stored" in job.error_summary



def test_gmail_rate_limit_pauses_the_sync_and_resumes_later_without_failing(api, db, connected_account, mailbox):
    from datetime import timedelta

    from app.db.types import utcnow
    from app.integrations.gmail_client import GmailRateLimited
    from app.tasks.runner import resume_stuck_jobs_impl, sync_account_impl

    a = connected_account("acct1@gmail.com")
    box = mailbox.for_email("acct1@gmail.com")
    box.page_size = 2
    for i in range(5):
        box.add(jd_message(f"cccc000{i}", subject=f"Job {i} requirement", body=JD_BODY.replace("GX-1042", f"GX-{i}00")))
    use_ai()
    box.fail_get["cccc0003"] = GmailRateLimited("rate limit")  # Gmail says slow down on page 2
    j = sync(api, a.id)
    db.expire_all()
    import uuid

    job = db.get(ProcessingJob, uuid.UUID(j["job_id"]))
    assert job.status == "queued" and job.attempts == 0  # a rate limit never uses up the attempt budget
    assert job.checkpoint["rate_limit_hits"] == 1 and "resume_after" in job.checkpoint and "slow down" in job.error_summary
    assert count(db, EmailMessage) == 2  # page 1 is kept
    # while cooling down, re-running does nothing (no Gmail calls), and the 'stuck job' recovery leaves it alone
    del box.fail_get["cccc0003"]
    box.calls.clear()
    sync_account_impl(str(job.id))
    assert box.calls == []
    job.updated_at = utcnow() - timedelta(minutes=30)
    db.commit()
    assert resume_stuck_jobs_impl() == 0 and db.get(ProcessingJob, job.id).status == "queued"
    # once the cooldown has passed it carries on from the checkpoint and finishes
    job = db.get(ProcessingJob, job.id)
    ck = dict(job.checkpoint)
    ck["resume_after"] = (utcnow() - timedelta(minutes=1)).isoformat()
    job.checkpoint = ck
    db.commit()
    sync_account_impl(str(job.id))
    db.expire_all()
    done = db.get(ProcessingJob, job.id)
    assert done.status == "completed" and count(db, EmailMessage) == 5 and "resume_after" not in done.checkpoint


def test_gmail_gateway_paces_calls_backs_off_and_honours_retry_after(monkeypatch):
    import httplib2
    from googleapiclient.errors import HttpError

    from app.integrations import gmail_client as gc

    sleeps: list[float] = []
    monkeypatch.setattr(gc, "_sleep", sleeps.append)
    monkeypatch.setattr(gc, "_governor", None)
    gw = gc.GoogleGmailGateway.__new__(gc.GoogleGmailGateway)

    class Req:
        def __init__(self, outcomes):
            self.outcomes = list(outcomes)

        def execute(self, num_retries=0):
            o = self.outcomes.pop(0)
            if isinstance(o, Exception):
                raise o
            return o

    def http_error(status, retry_after=None, reason=""):
        headers = {"status": str(status), **({"retry-after": str(retry_after)} if retry_after else {})}
        return HttpError(httplib2.Response(headers), b"{}", uri="u")

    # two 429s then success: retried with growing waits, the penalty slows later calls
    assert gw._exec(Req([http_error(429), http_error(429, retry_after=30), {"ok": 1}])) == {"ok": 1}
    waits = [s for s in sleeps if s >= 2]
    assert len(waits) == 2 and waits[1] >= 30  # Retry-After from Gmail is honoured
    assert gc.governor().penalty > 1.0
    # a permanent error is not retried
    n = len([x for x in sleeps if x >= 2])
    try:
        gw._exec(Req([http_error(404)]))
        raise AssertionError("expected GmailNotFound")
    except gc.GmailNotFound:
        pass
    assert len([x for x in sleeps if x >= 2]) == n  # no backoff wait for a permanent error
    # retries are bounded: after GMAIL_MAX_RETRIES the rate-limit error is raised for the sync job to pause on
    from app.core.config import get_settings

    over = [http_error(429)] * (get_settings().gmail_max_retries + 1)
    try:
        gw._exec(Req(over))
        raise AssertionError("expected GmailRateLimited")
    except gc.GmailRateLimited:
        pass
    # calls are spaced: at 4 per second each call is scheduled 0.25s after the previous one (the patched sleep returns at once,
    # so the requested waits simply grow by one gap per call)
    gov = gc.RateGovernor(4)
    sleeps.clear()
    for _ in range(10):
        gov.wait()
    assert len(sleeps) >= 9 and all(abs((b - a) - 0.25) < 0.03 for a, b in zip(sleeps, sleeps[1:]))


def test_without_a_worker_long_tasks_run_in_the_background_in_production_only(monkeypatch):
    import threading

    from app.core.config import get_settings
    from app.tasks import runner

    ran: dict[str, str] = {}
    gate, done = threading.Event(), threading.Event()

    def slow(*_a, **_k):
        gate.wait(5)  # still running when enqueue() has already returned
        ran["thread"] = threading.current_thread().name
        done.set()

    monkeypatch.setitem(runner._INLINE, "sync_account", slow)
    monkeypatch.setattr(get_settings(), "redis_url", "")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    runner.enqueue("sync_account", "job-1")  # returns immediately although the task is blocked
    assert "thread" not in ran
    gate.set()
    assert done.wait(5) and ran["thread"].startswith("inline-task")
    # elsewhere (tests, development) it stays synchronous so callers see the finished state
    ran.clear()
    done.clear()
    monkeypatch.setattr(get_settings(), "app_env", "test")
    runner.enqueue("sync_account", "job-2")
    assert ran["thread"] == threading.current_thread().name
    # quick tasks (export, send) always run in line, because their endpoints return the result
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setitem(runner._INLINE, "send_delivery", lambda *_a, **_k: ran.__setitem__("send", threading.current_thread().name))
    runner.enqueue("send_delivery", "d1")
    assert ran["send"] == threading.current_thread().name
