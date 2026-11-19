"""Lanxang supports Python 3.11, whose f-strings can't hold a backslash or reuse the outer quote inside {...}.
Python 3.12+ accepts both, so a developer on a newer Python only finds out from CI - this catches it everywhere."""

import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def problems(source):
    """[(line, what)] for f-string expressions Python 3.11 would reject."""

    stack, found = [], []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.FSTRING_START:
            quote = tok.string.lstrip("rRfFbBuU")
            quote = quote[:3] if quote[:3] in ('"""', "'''") else quote[:1]
            if stack and quote == stack[-1]:
                found.append((tok.start[0], "nested f-string reuses the outer quote"))
            stack.append(quote)
        elif tok.type == tokenize.FSTRING_END:
            stack.pop()
        elif stack and tok.type == tokenize.STRING:
            if "\\" in tok.string:
                found.append((tok.start[0], "backslash inside an f-string expression"))
            if len(stack[-1]) == 1 and tok.string.lstrip("rRbBuU")[:1] == stack[-1]:
                found.append((tok.start[0], "string reuses the outer f-string quote"))
        elif stack and tok.type == tokenize.COMMENT:
            found.append((tok.start[0], "comment inside an f-string expression"))
    return found


def test_the_checker_catches_what_python_311_rejects():
    if not hasattr(tokenize, "FSTRING_START"):            # on 3.11 itself the import of a bad file already fails
        return
    assert problems('x = f"{" a=\\"b\\"" if 1 else ""}"\n')
    assert problems('x = f"{"a"}"\n')
    assert not problems("x = f\"{'a'} {y!r:>4}\"\n")


def test_no_python_312_only_f_strings():
    if not hasattr(tokenize, "FSTRING_START"):
        return
    found = [f"{path.relative_to(ROOT)}:{line} {what}" for folder in ("lanxang", "tools", "tests")
             for path in sorted((ROOT / folder).rglob("*.py")) for line, what in problems(path.read_text())]
    assert not found, "\n".join(found)
