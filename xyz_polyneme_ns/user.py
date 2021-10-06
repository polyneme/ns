from typing import Optional, List

import pymongo.database
from fastapi import Depends, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel
from pymongo.database import Database as MongoDatabase

from xyz_polyneme_ns.auth import (
    verify_password,
    SECRET_KEY,
    ALGORITHM,
    oauth2_scheme,
    credentials_exception,
    TokenData,
    optional_oauth2_scheme,
)

from xyz_polyneme_ns.db import mongo_db

Username = str
Namespace = str


class User(BaseModel):
    username: Username
    email: Optional[str] = None
    full_name: Optional[str] = None
    allow: List[Namespace] = []
    disabled: Optional[bool] = None


class UserInDB(User):
    hashed_password: str


def get_user(mdb, username: str) -> UserInDB:
    user = mdb.users.find_one({"username": username})
    if user is not None:
        return UserInDB(**user)


def authenticate_user(mdb, username: str, password: str):
    user = get_user(mdb, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    mdb: pymongo.database.Database = Depends(mongo_db),
) -> UserInDB:
    if mdb.invalidated_tokens.find_one({"_id": token}):
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject: str = payload.get("sub")
        if subject is None:
            raise credentials_exception
        if not subject.startswith("user:"):
            raise credentials_exception
        username = subject.split("user:", 1)[1]
        token_data = TokenData(subject=username)
    except JWTError:
        raise credentials_exception
    user = get_user(mdb, username=token_data.subject)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> UserInDB:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


class NamespaceClient(BaseModel):
    allow: Namespace
    client_id: str
    hashed_client_secret: str
    created_by: Username


def get_ns_client(mdb, client_id: str):
    client = mdb.ns_clients.find_one({"client_id": client_id})
    if client is not None:
        return NamespaceClient(**client)


def authenticate_ns_client(mdb, client_id: str, client_secret: str):
    client = get_ns_client(mdb, client_id)
    if not client:
        return False
    if not verify_password(client_secret, client.hashed_client_secret):
        return False
    return client


async def get_current_ns_client(
    token: str = Depends(oauth2_scheme),
    mdb: MongoDatabase = Depends(mongo_db),
) -> NamespaceClient:
    if mdb.invalidated_tokens.find_one({"_id": token}):
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject: str = payload.get("sub")
        if subject is None:
            raise credentials_exception
        if not subject.startswith("client:"):
            raise credentials_exception
        client_id = subject.split("client:", 1)[1]
        token_data = TokenData(subject=client_id)
    except JWTError:
        raise credentials_exception
    client = get_ns_client(mdb, client_id=token_data.subject)
    if client is None:
        raise credentials_exception
    return client


async def maybe_get_current_ns_client(
    token: str = Depends(optional_oauth2_scheme),
    mdb: pymongo.database.Database = Depends(mongo_db),
):
    if token is None:
        return None
    return await get_current_ns_client(token, mdb)
