import csv
import os
from collections import defaultdict
from functools import lru_cache
import re

import base32_lib as base32
from pydantic import HttpUrl, ValidationError, BaseModel, constr

ARK_MAP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ark_map.csv"
)
ARK_NAAN_SHOULDER_MAP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ark_naan_shoulder_map.csv",
)


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
def ark_map(naan: str = "57802"):
    with open(ARK_MAP_PATH) as csvfile:
        reader = csv.DictReader(csvfile)
        return {
            row["ark"]: row["url"]
            for row in reader
            if row["ark"].startswith(f"ark:{naan}")
        }


@lru_cache
def ark_naan_shoulder_map():
    with open(ARK_NAAN_SHOULDER_MAP_PATH) as csvfile:
        reader = csv.DictReader(csvfile)
        naan_shoulders = defaultdict(set)
        for row in reader:
            naan_shoulders[row["naan"]].add(row["shoulder"])
        return naan_shoulders


ark_basename = re.compile(rf"ark:[^/]+/([^/]+)")


@lru_cache
def existing_basenames(naan: str = "57802"):
    return {ark.split("/")[1].split(".", maxsplit=1)[0] for ark in ark_map(naan)}


def generate_id_unique(
    naan: str = "57802", shoulder: str = "fk1", **generate_id_kwargs
) -> str:
    """Generate unique Crockford Base32-encoded ID for ARK naan basename.

    Use local ark_map to check uniqueness under naan.

    """
    get_one = True
    collection = existing_basenames(naan)
    while get_one:
        eid = shoulder + generate_id(**generate_id_kwargs)
        get_one = eid in collection
    return eid


Ark = constr(regex=r"^ark:[^/]+/.+$")


class ArkMapEntry(BaseModel):
    ark: Ark
    url: HttpUrl


def add_ark_map_entry(
    url: str,
    id_desired: str = None,
    shoulder: str = "fk1",
    naan: str = "57802",
):
    if id_desired is not None:
        if id_desired in existing_basenames(naan):
            raise ValueError(f"id_desired already has ark map entry under ark:{naan}/.")
        else:
            id_to_use = id_desired
    else:
        # length 8 minus 2-digit checksum => (2**5)**6 ~ 1 billion blades for each shoulder.
        id_to_use = generate_id_unique(
            naan=naan, shoulder=shoulder, length=8, split_every=0, checksum=True
        )
    if not isinstance(id_to_use, str):
        raise Exception("internal error: add_ark_map_entry")

    shoulders = ark_naan_shoulder_map()[naan]
    for s in shoulders:
        if id_to_use.startswith(s):
            break
    else:  # id_to_use does not start with a registered should for this naan
        raise ValueError(
            f"ID {id_to_use} does not start with a registered shoulder for naan {naan} "
            f"(must be one of {shoulders})."
        )

    ark_new = f"ark:{naan}/{id_to_use}"
    try:
        ArkMapEntry(ark=ark_new, url=url)
    except ValidationError as e:
        raise ValueError(f"bad ark map entry: {e}")

    with open(ARK_MAP_PATH, "a") as f:
        f.write(f"ark:{naan}/{id_to_use},{url}\n")
    ark_map.cache_clear()
    return ark_new, ark_map(naan)[ark_new]
