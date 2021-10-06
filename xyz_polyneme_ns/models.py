from bson import ObjectId
from typing import Any, Dict

import bson.json_util
from pydantic import BaseModel, validator, Extra


class VocabularyTermUpdates(BaseModel):
    term_name: str
    updates: Dict[str, str]

    @validator("updates")
    def serializes_to_mongo_json(cls, v):
        try:
            bson.json_util.dumps(v)
        except TypeError as e:
            raise ValueError(str(e))
        return v


class VocabularyTerm(BaseModel):
    class Config:
        json_encoders = {
            ObjectId: lambda oid: str(oid),
        }
        extra = Extra.allow


class VocabularyTermImport(BaseModel):
    reference_path: str
    target_name: str


class VocabularyTermParts(BaseModel):
    ns: str
    local: str
