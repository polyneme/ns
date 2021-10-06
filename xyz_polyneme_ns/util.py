import secrets

import string

from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from pathlib import Path
from starlette import status

from toolz import keyfilter

PKG_ROOT_DIR = Path(__file__).parent
REPO_ROOT_DIR = PKG_ROOT_DIR.parent


def pick(whitelist, d):
    return keyfilter(lambda k: k in whitelist, d)


def omit(blacklist, d):
    return keyfilter(lambda k: k not in blacklist, d)


def now(as_str=False):
    dt = datetime.now(timezone.utc)
    return dt.isoformat() if as_str else dt


def raise404_if_none(doc, detail="Not found"):
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return doc


def generate_secret(length=12, include_punctuation=True):
    """Generate a secret.

    With
    - at least one lowercase character,
    - at least one uppercase character, and
    - at least three digits

    """
    if length < 8:
        raise ValueError(f"{length=} must be >=8.")
    alphabet = (
        string.ascii_letters
        + string.digits
        + (string.punctuation if include_punctuation else "")
    )
    # based on https://docs.python.org/3.8/library/secrets.html#recipes-and-best-practices
    while True:
        _secret = "".join(secrets.choice(alphabet) for i in range(length))
        if (
            any(c.islower() for c in _secret)
            and any(c.isupper() for c in _secret)
            and sum(c.isdigit() for c in _secret) >= 3
        ):
            break
    return _secret


def expiry_dt_from_now(days=0, hours=0, minutes=0, seconds=0):
    return now() + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def has_passed(dt):
    return now() > dt
