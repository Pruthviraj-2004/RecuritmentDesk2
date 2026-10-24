"""Text, title, location, skill and fingerprint normalization (pure functions)."""
from __future__ import annotations

import hashlib
import re
import unicodedata

from bs4 import BeautifulSoup

_WS = re.compile(r"[ \t ]+")
_BLANKS = re.compile(r"\n{3,}")
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)


def normalize_unicode(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_ZERO_WIDTH)
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")


def normalize_whitespace(text: str) -> str:
    text = normalize_unicode(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip()


def html_to_text(html: str) -> str:
    """Convert untrusted HTML to plain text. Scripts, styles and active content are dropped, never executed."""
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "iframe", "object", "embed", "noscript", "head", "svg", "form"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for blk in soup.find_all(["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "table", "ul", "ol"]):
        blk.append("\n")
    return normalize_whitespace(soup.get_text())


_QUOTE_HEADER = re.compile(r"^(on .{5,200}wrote:|-{2,}\s*original message\s*-{2,}|from:.{0,200}sent:.{0,200})\s*$", re.I)
_FORWARD_MARKER = re.compile(r"-{3,}\s*forwarded message\s*-{3,}", re.I)


def strip_quoted_replies(text: str) -> str:
    """Remove '>' quoted lines and trailing reply chains while keeping forwarded content (often the JD itself)."""
    out: list[str] = []
    for line in text.split("\n"):
        if line.lstrip().startswith(">"):
            continue
        if _QUOTE_HEADER.match(line.strip()) and not _FORWARD_MARKER.search(line):
            break
        out.append(line)
    return "\n".join(out).strip()


def is_forwarded(text: str) -> bool:
    return bool(_FORWARD_MARKER.search(text or ""))


_SUBJECT_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|sv)\s*:\s*)+", re.I)


def normalize_subject(subject: str | None) -> str:
    s = _SUBJECT_PREFIX.sub("", normalize_unicode(subject or "")).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def normalize_email_address(value: str | None) -> str:
    if not value:
        return ""
    m = re.search(r"[\w.+\-']+@[\w\-]+(?:\.[\w\-]+)+", value)
    return (m.group(0) if m else value).strip().lower()


_COMPANY_SUFFIX = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|pvt|private|corp|corporation|co|company|gmbh|plc|llp|technologies|technology|solutions|services|systems)\b\.?",
    re.I,
)


def normalize_company(name: str | None) -> str:
    if not name:
        return ""
    s = normalize_unicode(name).lower()
    s = _COMPANY_SUFFIX.sub(" ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_TITLE_NOISE = re.compile(r"\b(urgent|hot|immediate|requirement|req|opening|hiring|position|role|for|need|needed|wanted)\b", re.I)
_TITLE_ALIASES = [
    (re.compile(r"\bsr\b\.?", re.I), "senior"),
    (re.compile(r"\bjr\b\.?", re.I), "junior"),
    (re.compile(r"\bengr\b", re.I), "engineer"),
    (re.compile(r"\bdev\b", re.I), "developer"),
    (re.compile(r"\bswe\b", re.I), "software engineer"),
    (re.compile(r"\bqa\b", re.I), "quality assurance"),
    (re.compile(r"\bmgr\b", re.I), "manager"),
]


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    s = normalize_unicode(title).lower()
    for pat, repl in _TITLE_ALIASES:
        s = pat.sub(repl, s)
    s = _TITLE_NOISE.sub(" ", s)
    s = re.sub(r"[^a-z0-9+#.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_LOCATION_ALIASES = {
    "bengaluru": "bangalore", "bombay": "mumbai", "gurgaon": "gurugram", "nyc": "new york", "sf": "san francisco",
    "usa": "united states", "us": "united states", "u.s.": "united states", "uk": "united kingdom",
    "ca": "california", "tx": "texas", "ny": "new york", "wa": "washington", "nj": "new jersey", "fl": "florida",
}


def normalize_location(loc: str | None) -> str:
    if not loc:
        return ""
    s = normalize_unicode(loc).lower()
    tokens = [t for t in re.split(r"[^a-z0-9.]+", s) if t]
    return " ".join(_LOCATION_ALIASES.get(t, t) for t in tokens)


SKILL_ALIASES: dict[str, str] = {
    "js": "javascript", "node": "node.js", "nodejs": "node.js", "node js": "node.js", "reactjs": "react", "react.js": "react",
    "react js": "react", "vuejs": "vue", "vue.js": "vue", "angularjs": "angular", "ts": "typescript", "py": "python",
    "postgres": "postgresql", "psql": "postgresql", "mongo": "mongodb", "k8s": "kubernetes", "gcp": "google cloud",
    "google cloud platform": "google cloud", "amazon web services": "aws", "ml": "machine learning", "ai": "artificial intelligence",
    "dotnet": ".net", "dot net": ".net", "c sharp": "c#", "golang": "go", "tf": "terraform", "ci/cd": "ci/cd", "cicd": "ci/cd",
    "ms sql": "sql server", "mssql": "sql server", "springboot": "spring boot", "fast api": "fastapi", "scikit learn": "scikit-learn",
    "sklearn": "scikit-learn", "nextjs": "next.js", "next js": "next.js", "expressjs": "express", "express.js": "express",
}

_SKILL_CATEGORIES = {
    "language": {"python", "java", "javascript", "typescript", "go", "c#", "c++", "ruby", "php", "kotlin", "swift", "rust", "scala", "sql", "r"},
    "framework": {"react", "angular", "vue", "django", "flask", "fastapi", "spring boot", "node.js", ".net", "next.js", "express", "rails", "laravel"},
    "database": {"postgresql", "mysql", "mongodb", "redis", "oracle", "sql server", "cassandra", "dynamodb", "elasticsearch", "snowflake"},
    "cloud": {"aws", "azure", "google cloud"},
    "devops": {"docker", "kubernetes", "terraform", "jenkins", "ansible", "ci/cd", "git", "github actions"},
    "ai_ml": {"machine learning", "artificial intelligence", "tensorflow", "pytorch", "scikit-learn", "nlp", "llm", "deep learning"},
}


def normalize_skill(skill: str | None) -> str:
    if not skill:
        return ""
    s = re.sub(r"\s+", " ", normalize_unicode(skill).lower().strip(" .,;:-•*"))
    return SKILL_ALIASES.get(s, s)


def skill_category(normalized: str) -> str | None:
    for cat, members in _SKILL_CATEGORIES.items():
        if normalized in members:
            return cat
    return None


def normalize_skill_list(skills: list[str] | None) -> list[tuple[str, str]]:
    """Return de-duplicated (display_name, normalized) pairs preserving first-seen order."""
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for raw in skills or []:
        norm = normalize_skill(raw)
        if not norm or len(norm) > 100 or norm in seen:
            continue
        seen.add(norm)
        display = re.sub(r"\s+", " ", normalize_unicode(raw)).strip(" .,;:-•*")
        result.append((display or norm, norm))
    return result


def sha256_hex(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", "replace"))
        h.update(b"\x1f")
    return h.hexdigest()


def message_content_hash(sender_email: str | None, subject: str | None, body: str | None, attachment_sigs: list[str] | None = None) -> str:
    """Cross-account fingerprint. Gmail IDs are per-mailbox, so identical content is matched by content."""
    body_norm = re.sub(r"\s+", " ", strip_quoted_replies(normalize_whitespace(body or ""))).strip().lower()[:8000]
    return sha256_hex(
        normalize_email_address(sender_email),
        normalize_subject(subject),
        body_norm,
        "|".join(sorted(attachment_sigs or [])),
    )


def requirement_fingerprint(client: str | None, title: str | None, reference_id: str | None, location: str | None) -> str | None:
    """Canonical key for exact duplicate detection. Returns None if there is not enough identifying data."""
    c, t = normalize_company(client), normalize_title(title)
    ref = re.sub(r"[^a-z0-9]", "", (reference_id or "").lower())
    if ref and c:
        return sha256_hex("ref", c, ref)
    if c and t:
        return sha256_hex("ct", c, t, normalize_location(location))
    return None
