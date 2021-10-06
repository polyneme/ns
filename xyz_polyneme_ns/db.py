import os
from functools import lru_cache
from pathlib import Path

from pymongo import MongoClient
from pymongo.database import Database as MongoDatabase
from toolz import merge

from xyz_polyneme_ns.util import REPO_ROOT_DIR

MONGO_HOST = os.getenv("MONGO_HOST")
MONGO_PORT = os.getenv("MONGO_PORT")
MONGO_USERNAME = os.getenv("MONGO_USERNAME")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_DBNAME = os.getenv("MONGO_DBNAME")
MONGO_TLS = os.getenv("MONGO_TLS")
MONGO_TLS_CA_FILE = os.getenv("MONGO_TLS_CA_FILE")


@lru_cache
def mongo_db() -> MongoDatabase:
    host = MONGO_HOST or "localhost"
    try:
        port = int(MONGO_PORT)
    except TypeError:
        port = 27017
    username = MONGO_USERNAME
    password = MONGO_PASSWORD
    tls = MONGO_TLS == "true"
    tls_ca_file = (
        tls and MONGO_TLS_CA_FILE and REPO_ROOT_DIR.joinpath(MONGO_TLS_CA_FILE)
    )
    kwargs = dict(host=host, port=port)
    if username:
        kwargs = merge(kwargs, dict(username=username, password=password))
    if tls:
        kwargs = merge(kwargs, dict(tls=tls, tlsCAFile=str(tls_ca_file)))
    _client = MongoClient(**kwargs)
    return _client[MONGO_DBNAME]
