from enum import Enum

from bson import ObjectId
from typing import Any, Dict, List, Union

import bson.json_util
from pydantic import BaseModel, validator, Extra, constr


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


Username = constr(regex=r"[a-zA-Z0-9_]+")
Org = constr(regex=r"[a-zA-Z0-9_]+")
Repo = constr(regex=r"[a-zA-Z0-9_]+/[a-zA-Z0-9_]+")


class AgentType(str, Enum):
    person = "person"
    software_agent = "software_agent"


class AgentIn(BaseModel):
    username: Username
    password: str
    can_edit: List[Repo]
    type: AgentType


AgentUri = constr(
    regex=r"ark:(?P<naan>\d{5,})/9999/12/system/agents/(?P<username>[a-zA-Z0-9_]+)"
)


def get_agent_uri(naan, username):
    return f"ark:{naan}/9999/12/system/agents/{username}"


class Agent(BaseModel):
    id: AgentUri
    username: Username
    hashed_password: str
    can_edit: List[Repo]
    can_admin: List[Union[Org, Repo]]
    type: AgentType
