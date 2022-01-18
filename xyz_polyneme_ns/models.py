import re
from enum import Enum

from bson import ObjectId
from typing import Any, Dict, List, Union

import bson.json_util
from pydantic import BaseModel, validator, Extra, constr, conint


class DocUpdate(BaseModel):
    update: Dict[str, Any]

    @validator("update")
    def serializes_to_mongo_json(cls, v):
        try:
            bson.json_util.dumps(v)
        except TypeError as e:
            raise ValueError(str(e))
        return v


class Doc(BaseModel):
    class Config:
        json_encoders = {
            ObjectId: lambda oid: str(oid),
        }
        extra = Extra.allow


TermUri = constr(
    regex=r"ark:(?P<naan>\d{5,})/(?P<year>\d{4})/(?P<month>\d{2})/(?P<org>\w+)/(?P<repo>\w+)/(?P<term>\w+)"
)


class TermImport(BaseModel):
    term_uri: TermUri


# NO i, l, o or u.
BASE32_LETTERS = "abcdefghjkmnpqrstvwxyz"

Username = constr(regex=r"[a-zA-Z0-9_]+")
Org = constr(regex=r"[a-zA-Z0-9_]+")
Repo = constr(regex=r"[a-zA-Z0-9_]+/[a-zA-Z0-9_]+")
Ark = constr(regex=r"^ark:[^/]+/.+$")
ArkShoulder = constr(regex=rf"^[{BASE32_LETTERS}]+\d$")
# XXX In practice, every assigned NAAN has consisted of exactly five digits.
# However, the spec says that NAANs are opaque strings of one or more "betanumeric" characters.
# So prepare to swap the ArkNaan line below for:
# ArkNaan = BetanumericStr
#
# Source:
# J. A. Kunze, "The ARK Identifier Scheme (v.27)."
# Internet Engineering Task Force (IETF), Feb. 2021. [Online].
# Available: https://www.ietf.org/archive/id/draft-kunze-ark-27.txt
BetanumericStr = constr(regex=r"^[0123456789bcdfghjkmnpqrstvwxz]+$")
ArkNaan = conint(ge=10000, lt=100000)  # exactly five digits

pattern_shoulder = re.compile(rf"(?P<shoulder>[{BASE32_LETTERS}]+\d)")


class AgentType(str, Enum):
    person = "person"
    software_agent = "software_agent"


class AgentIn(BaseModel):
    username: Username
    password: str
    can_edit: List[Repo]
    can_admin_shoulders: List[ArkShoulder]
    type: AgentType


AgentUri = constr(
    regex=r"ark:(?P<naan>\d{5,})/9999/12/system/agents/(?P<username>[a-zA-Z0-9_]+)"
)


def get_agent_uri(naan, username):
    return f"ark:{naan}/9999/12/system/agents/{username}"


def get_shoulder(assigned_base_name: str):
    m = re.search(pattern_shoulder, assigned_base_name)
    return m.group("shoulder") if m else None


class Agent(BaseModel):
    id: AgentUri
    username: Username
    hashed_password: str
    can_admin_shoulders: List[ArkShoulder]
    can_edit: List[Repo]
    can_admin: List[Union[Org, Repo]]
    type: AgentType
