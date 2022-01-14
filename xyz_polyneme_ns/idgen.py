import csv
import os
from collections import defaultdict
from functools import lru_cache
import re

import base32_lib as base32
from pydantic import HttpUrl, ValidationError, BaseModel, constr
from pymongo.database import Database as MongoDatabase


def generate_id(length=10, split_every=4, checksum=True) -> str:
    """Generate random base32 string: a user-shareable ID for a database entity.

    Uses Douglas Crockford Base32 encoding: <https://www.crockford.com/base32.html>

    Default is 8 characters (5-bits each) plus 2 digit characters for ISO 7064 checksum,
    so 2**40 ~ 1 trillion possible values, *much* larger than the number of statements
    feasibly storable by the database. Hyphen splits are optional for human readability,
    and the default is one split after 5 characters, so an example output using the default
    settings is '3sbk2-5j060'.

    :param length: non-hyphen identifier length *including* checksum
    :param split_every: hyphenates every that many characters
    :param checksum: computes and appends ISO-7064 checksum
    :returns: identifier as a string
    """
    return base32.generate(length=length, split_every=split_every, checksum=checksum)


def decode_id(encoded: str, checksum=True) -> int:
    """Decodes generated string ID (via `generate_id`) to a number.

    The string is normalized -- lowercased, hyphens removed,
    {I,i,l,L}=>1 and {O,o}=>0 (user typos corrected) -- before decoding.

    If `checksum` is enabled, raises a ValueError on checksum error.

    :param encoded: string to decode
    :param checksum: extract checksum and validate
    :returns: original number.
    """
    return base32.decode(encoded=encoded, checksum=checksum)


def encode_id(number: int, split_every=4, min_length=10, checksum=True) -> int:
    """Encodes `number` to URI-friendly Douglas Crockford base32 string.

    :param number: number to encode
    :param split_every: if provided, insert '-' every `split_every` characters
                        going from left to right
    :param min_length: 0-pad beginning of string to obtain minimum desired length
    :param checksum: append modulo 97-10 (ISO 7064) checksum to string
    :returns: A random Douglas Crockford base32 encoded string composed only
              of valid URI characters.
    """
    return base32.encode(
        number, split_every=split_every, min_length=min_length, checksum=checksum
    )


@lru_cache
def ark_map(mdb: MongoDatabase, naan: int = 57802):
    return {
        d["_id"]: d.get("_t")
        for d in mdb.arks.find({"_id": {"$regex": rf"^ark:{naan}"}}, ["_t"])
    }


@lru_cache
def ark_naan_shoulder_map(mdb: MongoDatabase):
    return {d["_id"]: set(d["shoulders"]) for d in mdb.naans.find({}, ["shoulders"])}


ark_basename = re.compile(rf"ark:[^/]+/([^/]+)")


@lru_cache
def existing_basenames(mdb: MongoDatabase, naan: int = 57802):
    return {ark.split("/")[1].split(".", maxsplit=1)[0] for ark in ark_map(mdb, naan)}


# sping: "semi-opaque string" (https://n2t.net/e/n2t_apidoc.html).
SPING_SIZE_THRESHOLDS = [(n, (2 ** (5 * n)) // 2) for n in [2, 4, 6, 8, 10]]


def create_ark_bon(
    mdb: MongoDatabase,
    naan: int = 57802,
    shoulder: str = "fk1",
) -> str:
    """Create and persist a new ARK Base Object Name (BON) for ARK naan + shoulder.

    Generates a unique, as-short-as-reasonable Crockford Base32-encoded ID.
    """
    ark_to_shoulder = f"ark:{naan}/{shoulder}"
    existing_blades = {
        a.split(ark_to_shoulder, maxsplit=1)[1]
        for a in mdb.arks.distinct("_id", {"_id": {"$regex": rf"^{ark_to_shoulder}"}})
    }
    n_chars = next(
        (n for n, t in SPING_SIZE_THRESHOLDS if (1 + len(existing_blades)) < t),
        12,
    )
    while True:
        blade = generate_id(length=(n_chars + 2), split_every=0, checksum=True)
        bon = f"ark:{naan}/{shoulder}{blade}"
        taken = mdb.arks.find_one({"_id": {"$regex": rf"^{bon}"}}, ["_id"]) is not None
        if not taken:
            mdb.arks.insert_one({"_id": bon})
            break
    return bon
