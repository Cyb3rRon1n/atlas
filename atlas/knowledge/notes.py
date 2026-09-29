import re
from pathlib import Path


# Scripts/unit files count too: homelab scripts document themselves in comments.
NOTE_SUFFIXES = {".md", ".txt", ".sh", ".py", ".service", ".timer", ".yml", ".yaml", ".conf", ".j2"}

MAX_FILE_BYTES = 1_000_000

EXCERPT_CHARS = 1200

HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def _note_files(paths):

    for root in paths:

        root = Path(root)

        if root.is_file():
            yield root
            continue

        if not root.is_dir():
            continue

        for path in sorted(root.rglob("*")):

            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue

            if path.suffix.lower() in NOTE_SUFFIXES and path.is_file() and path.stat().st_size <= MAX_FILE_BYTES:
                yield path


def _sections(text):

    heading = ""
    lines = []

    for line in text.splitlines():

        match = HEADING.match(line)

        if match:

            if lines:
                yield heading, "\n".join(lines).strip()

            heading = match.group(1).strip()
            lines = []

        else:
            lines.append(line)

    if lines or heading:
        yield heading, "\n".join(lines).strip()


def search_notes(paths, query, limit=5):
    """
    Keyword search over Markdown/text notes, section by section (split on
    headings). A term in a section's heading or file name counts triple -
    runbooks are titled by what they're about. No embeddings/index on
    purpose: a homelab's notes are a few hundred KB, a scan is instant.
    """

    terms = [term for term in re.findall(r"[\w.:/-]+", query.lower()) if len(term) > 1]

    if not terms:
        return {"results": [], "error": "Empty query"}

    scored = []

    for path in _note_files(paths):

        try:
            text = path.read_text(errors="replace")

        except OSError:
            continue

        # Only Markdown has headings; in scripts a leading '#' is a comment.
        sections = _sections(text) if path.suffix.lower() == ".md" else [("", text)]

        for heading, body in sections:

            title = f"{path.name} {heading}".lower()
            body_lower = body.lower()

            score = sum(3 * title.count(term) + body_lower.count(term) for term in terms)
            matched = sum(1 for term in terms if term in title or term in body_lower)

            if score:
                scored.append((matched, score, str(path), heading, body))

    scored.sort(key=lambda row: (-row[0], -row[1]))

    return {
        "results": [
            {
                "file": file,
                "section": heading,
                "excerpt": body[:EXCERPT_CHARS]
            }
            for _, _, file, heading, body in scored[:limit]
        ]
    }
