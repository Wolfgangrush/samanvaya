"""Refusal firewall for credential-shaped material in a declaration.

WHY this module exists: the tool processes hand-authored declarations about an
organisation.  If it ever held a live client credential, its author — a
practising advocate — would become a Data Processor in his own right, with his
own statutory breach-notification duty and indemnity exposure.  Therefore any
declaration containing something credential-shaped is REFUSED outright rather
than sanitised or warned about: the safest handling of a secret is never to
capture it in the first place.

Note that no field of :class:`CredentialFound` carries matched text; error
messages are constructed so the secret never reaches a log or traceback.

Worked false positives that MUST come back clean (prose that merely mentions
security words):

* ``"Cloud hosting provider (contract dated 1 April 2026)"``
* ``"Payment processor: settlement only, no card data retained"``
* ``"Access control: role-based access control"``
* ``"encryption: AES-256 at rest and TLS 1.3 in transit"`` — ``encryption`` is
  not a secret name.
* ``"Data Protection Officer: privacy@example.com"`` — not a secret name.
* ``"token bucket rate limiting is applied"`` — ``token`` with no assignment.

Worked true positives that MUST be refused:

* ``"postgresql://u:p@host:5432/db"``
* ``"mysql://root:toor@example-db-host/app"``
* ``"mongodb+srv://admin:pw@cluster.mongodb.net"``
* ``"AKIAIOSFODNN7EXAMPLE"``
* ``"-----BEGIN RSA PRIVATE KEY-----"``
* ``"aws_secret_access_key=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"``
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = ["CredentialFound", "scan", "assert_clean"]

# Detection patterns are compiled once at import so that scanning a large
# declaration never pays repeated compilation cost.

# Rule 1: URI with embedded userinfo (user:password@) for database/message
# schemes.  Case-insensitive; the userinfo pair must contain a colon.
_URI_USERINFO_RE = re.compile(
    r"""(?xi)\b
    (?:postgres|postgresql|mysql|mariadb|mongodb|mongodb\+srv|redis|rediss|
       amqp|amqps|mssql|oracle|jdbc|ftp|sftp|ldap|ldaps)
    :// [^/@\s]+ : [^/@\s]+ @
    """
)

# Rule 2: AWS access key identifiers.
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")

# Rule 3: PEM private key headers, e.g. "-----BEGIN RSA PRIVATE KEY-----".
# One or two label words may precede PRIVATE KEY.
_PEM_HEADER_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ ){0,2}PRIVATE KEY-----"
)

# Rule 4: Google API keys.
_GOOGLE_API_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")

# Rule 5: Slack tokens.
_SLACK_TOKEN_RE = re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}\b")

# Rule 6: Three-segment signed JWTs.
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"
)

_SECRET_NAMES = (
    "password|passwd|pwd|secret|api_key|apikey|access_key|secret_key|"
    "aws_secret_access_key|client_secret|private_key|token|auth_token|"
    "bearer|credentials"
)

# Rule 7: a secret-looking name followed by an assignment whose value looks
# like a secret rather than prose.  The value must be at least 8 non-space
# characters, contain a digit or one of _ - + / . (via the character class in
# the lookahead), and — critically — must not simply be a normal English word
# sequence trailing off to the end of the string (which is how prose such as a
# hyphenated job title would otherwise slip through).
_ASSIGNMENT_RE = re.compile(
    rf"""(?xi)
    # NOT `\b`: a word boundary does not exist between `_` and a letter, because both
    # are word characters. That let `my_password=` and `db_secret=` walk straight
    # through the firewall whose whole purpose is to stop them. Anchor on the start of
    # the string or on any character that is not a letter or a digit, which admits the
    # underscore-prefixed forms without matching a secret name buried inside a word.
    (?:^|[^A-Za-z0-9])(?:{_SECRET_NAMES})\s*[:=]\s*
    (?=\S{{8,}}(?:\s|$))
    (?=\S*[0-9_+\-/])
    (?![A-Za-z]+(?:[-.][A-Za-z]+){{1,}}(?:\s|$))
    \S+
    """
)

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("embedded userinfo credential in URI", _URI_USERINFO_RE),
    ("AWS access key id", _AWS_KEY_RE),
    ("PEM private key header", _PEM_HEADER_RE),
    ("Google API key", _GOOGLE_API_KEY_RE),
    ("Slack token", _SLACK_TOKEN_RE),
    ("JSON Web Token", _JWT_RE),
    ("credential assignment", _ASSIGNMENT_RE),
)


@dataclass(frozen=True)
class CredentialFound:
    """Description of where a credential-shaped value was found.

    ``path`` is a JSON-ish path such as ``"recipients[0]"`` or
    ``"organisation.legal_name"``; ``kind`` names the detection rule.

    Deliberately no field carries the matched text: propagating the secret
    would defeat the very refusal this firewall exists to enforce.
    """

    path: str
    kind: str


def _check_text(text: str) -> str | None:
    """Return the kind name of the first rule matching ``text``, else None."""
    for kind, pattern in _RULES:
        if pattern.search(text):
            return kind
    return None


def _join(parent: str, segment: str) -> str:
    """Build a JSON-ish path segment, dot-separating named keys."""
    if not parent:
        return segment
    return f"{parent}.{segment}"


def _walk(obj: object, path: str) -> CredentialFound | None:
    """Depth-first walk returning the first credential-shaped match."""
    if isinstance(obj, str):
        kind = _check_text(obj)
        if kind is not None:
            return CredentialFound(path=path, kind=kind)
        return None
    if isinstance(obj, dict):
        # Keys are walked as well as values: a credential-shaped key proves
        # the same intent and carries the same legal exposure.
        for key, value in obj.items():
            if isinstance(key, str):
                kind = _check_text(key)
                if kind is not None:
                    return CredentialFound(
                        path=f"{path}[{key!r}]" if path else repr(key),
                        kind=kind,
                    )
            child_path = _join(path, key) if isinstance(key, str) else (
                f"{path}[{key!r}]" if path else repr(key)
            )
            found = _walk(value, child_path)
            if found is not None:
                return found
        return None
    if isinstance(obj, (list, tuple)):
        for index, item in enumerate(obj):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            found = _walk(item, child_path)
            if found is not None:
                return found
        return None
    # Scalars (int, float, bool, None, enums, ...) cannot meaningfully encode
    # any of the credential shapes, so they are skipped without recursion.
    return None


def scan(obj: object) -> CredentialFound | None:
    """Walk ``obj`` and return the first credential-shaped match, or None.

    ``obj`` may be any nested structure of dicts, lists, tuples, strings and
    scalars.  Returning only the first match is deliberate: once one
    credential is present the declaration is refused regardless of how many
    more exist, and minimising traversal limits exposure.
    """
    return _walk(obj, "")


def assert_clean(obj: object) -> None:
    """Raise :class:`ValueError` if ``obj`` contains anything credential-shaped.

    The message names the path and the kind of credential but never includes
    the matched text — the error may end up in logs or a traceback, and a
    secret repeated there is a breach in its own right.
    """
    found = scan(obj)
    if found is not None:
        raise ValueError(
            f"Refused: credential-shaped data detected at path "
            f"'{found.path}' (kind: {found.kind}). Declarations must never "
            "contain live credentials; remove the credential and re-submit."
        )
