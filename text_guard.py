"""Detect common lossy text conversion before sending; never guess the missing characters."""
import re

ENCODING_ERROR = ("Message blocked: suspected text encoding damage. Recreate the original in a UTF-8 file. "
                  "For PowerShell pipes, set both $OutputEncoding and [Console]::OutputEncoding to UTF-8.")


class TextEncodingError(ValueError):
    code = 400


def encoding_issue(text):
    try:
        text.encode("utf-8")
    except UnicodeError:
        return ENCODING_ERROR
    # Quoted evidence and code may deliberately contain replacement characters or ?? operators.
    prose = re.sub(r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*(?:\n|$)", "", text)
    prose = re.sub(r"`[^`\n]*`|(?m:^[ \t]*>.*$)", "", prose)
    runs = re.findall(r"\?{2,}", prose)
    if "\ufffd" in prose or (len(runs) >= 4 and sum(map(len, runs)) >= 16
                              and prose.count("?") >= len(prose) * 0.04):
        return ENCODING_ERROR
    return None


def require_text(text):
    if encoding_issue(text):
        raise TextEncodingError(ENCODING_ERROR)
