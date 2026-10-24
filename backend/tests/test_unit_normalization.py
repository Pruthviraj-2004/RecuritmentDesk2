from app.services.classification.heuristics import classify_email, extract_hints
from app.services.gmail.mime import parse_gmail_message
from app.services.normalization.text import (
    html_to_text,
    message_content_hash,
    normalize_company,
    normalize_location,
    normalize_skill,
    normalize_skill_list,
    normalize_subject,
    normalize_title,
    normalize_whitespace,
    requirement_fingerprint,
    strip_quoted_replies,
)
from tests.fakes import JD_BODY, gmail_message


def test_whitespace_and_unicode_normalization():
    assert normalize_whitespace("a  b​\r\n\r\n\r\n\r\nc  ") == "a b\n\nc"
    assert normalize_whitespace("ＡＢＣ") == "ABC"  # NFKC


def test_html_is_sanitized_to_text():
    html = "<html><head><style>x{}</style></head><body><script>alert(1)</script><p>Hello</p><div>World<br>Line</div></body></html>"
    text = html_to_text(html)
    assert "alert" not in text and "x{}" not in text
    assert "Hello" in text and "World" in text and "Line" in text


def test_quoted_reply_chain_is_removed_but_forward_kept():
    body = "New info\n> old quoted\nOn Mon, Oct 5, 2026 at 9:00 AM Bob <b@x.com> wrote:\nstale text"
    assert strip_quoted_replies(body) == "New info"
    fwd = "FYI\n---------- Forwarded message ---------\nJob: Python Dev"
    assert "Python Dev" in strip_quoted_replies(fwd)


def test_subject_and_title_normalization():
    assert normalize_subject("RE: Fwd: Python Developer!!") == normalize_subject("python developer")
    assert normalize_title("URGENT: Sr. Python Dev") == "senior python developer"
    assert normalize_company("Globex Corporation, Inc.") == normalize_company("globex")
    assert normalize_location("Bengaluru, KA") == "bangalore ka"


def test_skill_aliases_and_dedup():
    assert normalize_skill("NodeJS") == "node.js"
    assert normalize_skill("Postgres") == "postgresql"
    assert normalize_skill("K8s") == "kubernetes"
    pairs = normalize_skill_list(["Python", "python ", "Postgres", "PostgreSQL", ""])
    assert [n for _, n in pairs] == ["python", "postgresql"]


def test_content_hash_ignores_reply_prefix_case_and_quotes_but_not_content():
    a = message_content_hash("Jane@Staffing.com", "Python Dev", "Body here\n> quoted")
    b = message_content_hash("jane@staffing.com", "RE: python dev", "Body   here")
    c = message_content_hash("jane@staffing.com", "python dev", "Different body")
    assert a == b and a != c


def test_requirement_fingerprint_rules():
    f1 = requirement_fingerprint("Globex Inc", "Sr Python Developer", "GX-1", "Bangalore")
    f2 = requirement_fingerprint("globex", "Other title", "gx1", "Pune")
    assert f1 == f2  # client + reference id dominate
    assert requirement_fingerprint(None, "Python Dev", None, None) is None  # not enough identity
    assert requirement_fingerprint("A", "Python Dev", None, "Pune") != requirement_fingerprint("A", "Python Dev", None, "Delhi")


def test_classification_job_description():
    c = classify_email("Urgent requirement: Python Developer", JD_BODY, "jane@staffing.com")
    assert c.category.value == "new_requirement" and c.confidence > 0.6


def test_classification_other_categories():
    assert classify_email("Newsletter", "Unsubscribe to our weekly sale 50% off", "no-reply@shop.com").category.value == "unrelated"
    assert classify_email("Interview schedule", "Please confirm the interview slot tomorrow, zoom link below", None).category.value == "interview_scheduling"
    assert classify_email("Update", "The position has been filled, please ignore this requirement", None).category.value == "job_closure"
    assert classify_email("Candidate", "Please find the resume attached, submitting the profile", None).category.value == "candidate_submission"
    assert classify_email("Updated requirement - rate revised", JD_BODY, None).category.value == "updated_requirement"


def test_hint_extraction_is_deterministic():
    h = extract_hints(JD_BODY)
    assert h["job_reference_id"] == "GX-1042"
    assert (h["minimum_experience"], h["maximum_experience"]) == (5.0, 8.0)
    assert h["work_mode"] == "hybrid" and "jane@staffing.com" in h["emails"]


def test_mime_parse_multipart_html_and_attachments():
    raw = gmail_message("abcdef12", "Hi", "plain body", html="<b>html</b>", attachments=[("jd.txt", "text/plain", b"job text")])
    p = parse_gmail_message(raw, 1000)
    assert p.body_text == "plain body"
    assert p.sender_email == "jane@staffing.com" and p.subject == "Hi"
    assert [a.filename for a in p.attachments] == ["jd.txt"] and p.attachments[0].attachment_id
    only_html = gmail_message("abcdef13", "Hi", "x")
    only_html["payload"]["parts"] = [only_html["payload"]["parts"][0] | {"mimeType": "text/html", "body": {"data": "PHA-SGVsbG88L3A-"}}]
    assert "Hello" in parse_gmail_message(only_html, 1000).body_text
