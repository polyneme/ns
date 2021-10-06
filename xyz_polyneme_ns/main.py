import re
import secrets
import string
from bson import ObjectId

from datetime import datetime, timedelta

import csv
import os
from collections import defaultdict

from pymongo.results import BulkWriteResult, InsertOneResult
from starlette import status
from toolz import merge, dissoc
from typing import Optional, Union, List, Dict, Any, Tuple
from pathlib import Path

from fastapi import FastAPI, Request, Response, Header, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import rdflib
from rdflib import URIRef, Literal
from pymongo import ReplaceOne, UpdateOne
from pymongo.database import Database as MongoDatabase
from rdflib import namespace as rdf_ns

from xyz_polyneme_ns.auth import (
    OAuth2PasswordOrClientCredentialsRequestForm,
    create_access_token,
    ACCESS_TOKEN_EXPIRES,
    Token,
    ClientCredentials,
    get_password_hash,
)
from xyz_polyneme_ns.db import mongo_db
from xyz_polyneme_ns.idgen import ark_map
from xyz_polyneme_ns.models import (
    VocabularyTerm,
    VocabularyTermImport,
    VocabularyTermParts,
    VocabularyTermUpdates,
)
from xyz_polyneme_ns.user import (
    authenticate_user,
    authenticate_ns_client,
    get_current_active_user,
    User,
    NamespaceClient,
    get_current_ns_client,
)
from xyz_polyneme_ns.util import (
    REPO_ROOT_DIR,
    pick,
    now,
    raise404_if_none,
    generate_secret,
)

tags_metadata = [
    {"name": "auth", "description": "credentials to allow you to make updates"},
    {"name": "terms", "description": "the things in vocabularies (aka ontologies)"},
    {"name": "vocabularies", "descriptions": "the things that contain terms"},
    {"name": "util", "description": "things like redirects and catch-alls"},
    {
        "name": "legacy",
        "description": "stuff that was here before, with URLs I don't want to break",
    },
]

app = FastAPI(
    title="TermOVer API",
    version="0.1.0",
    description="TermOVer is a stupid term and ontology version tracker.",
    openapi_tags=tags_metadata,
)

TEST_BASE = "http://ns.polyneme.xyz/2021/04/marda-dd/test#"


def load_ttl(filename: Union[Path, str]) -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(str(filename), format="turtle")
    return g


API_HOST = os.getenv("API_HOST")


def into_rdflib_graph(
    docs: List[Tuple[str, Dict[str, str]]],
    term_namespace: str,
    single_term=False,
):
    g = rdflib.Graph()
    g.namespace_manager.bind("rdf", rdf_ns.RDF)
    g.namespace_manager.bind("rdfs", rdf_ns.RDFS)
    g.namespace_manager.bind("owl", rdf_ns.OWL)

    for subject, predicate_objects in docs:
        for p, o in predicate_objects.items():
            g.add(
                (
                    URIRef(f"{API_HOST}/{term_namespace}/{subject}"),
                    URIRef(p),
                    Literal(o),
                )
            )
    if single_term:
        # term-centric graph, versus a graph for a vocabulary with a single term
        subject = docs[0][0]
        g.add(
            (
                URIRef(f"{API_HOST}/{term_namespace}/{subject}"),
                URIRef("rdfs:isDefinedBy"),
                URIRef(f"{API_HOST}/{term_namespace}"),
            )
        )
    else:
        g.add(
            (
                URIRef(f"{API_HOST}/{term_namespace}"),
                URIRef("rdf:type"),
                URIRef("owl:Ontology"),
            )
        )

    return g


TERMS = load_ttl(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hello_world.ttl",
    )
)


def render_html(g: rdflib.Graph, ns_base=TEST_BASE) -> str:
    header = """<html>
  <style type="text/css">
    dt { font-weight: bold; text-decoration: underline dotted; }
  </style>
  <body>
    <dl>
"""
    footer = """
    </dl>
  </body>
</html>"""

    dl = ""
    _parsed_subjects = set()
    for subject in g.subjects():
        if subject in _parsed_subjects:
            continue
        _parsed_subjects.add(subject)
        term = subject  # .split(ns_base)[-1]
        label = g.label(subject)
        comment = g.comment(subject)

        dt = f"""      <dt id="#{term}">{label}</dt>
      <dd>{comment}</dd>"""
        dl += dt

    return header + dl + footer


def render_html_skos(g: rdflib.Graph, ns_base=TEST_BASE) -> str:
    header = """<html>
  <style type="text/css">
    dt { font-weight: bold; text-decoration: underline dotted; }
  </style>
  <body>
    <dl>
"""
    footer = """
    </dl>
  </body>
</html>"""

    dl = ""
    _parsed_subjects = set()
    for subject in sorted(g.subjects()):
        if subject in _parsed_subjects:
            continue
        _parsed_subjects.add(subject)
        term = subject.split(ns_base)[-1]
        label = g.value(subject, rdf_ns.SKOS.prefLabel)
        definition = g.value(subject, rdf_ns.SKOS.definition)
        if label is None or definition is None:
            continue
        dt = f"""      <dt id="#{term}">{label}</dt>
      <dd>{definition}</dd>"""
        dl += dt

    return header + dl + footer


def sorted_media_types(accept: str) -> List[str]:
    """
    Example `accept`: "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8".
    """
    alternatives = [a.split(";") for a in accept.split(",")]
    for a in alternatives:
        # provide default relative quality factor
        # https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html
        if len(a) == 1:
            a.append("q=1")
        # ignore accept-params other than the relative quality factor
        for i, element in enumerate(a):
            if "=" in element and not element.startswith("q"):
                a.pop(i)
    alternatives = sorted(
        [(type_, float(qexpr[2:])) for type_, qexpr in alternatives],
        key=lambda a: a[1],
        reverse=True,
    )
    return [a[0] for a in alternatives]


def response_for(g: rdflib.Graph, accept: str, ns_base: str, html_profile=None):
    types_ = sorted_media_types(accept)
    # for media_type in types_:
    #     if media_type == "text/html":
    #         if html_profile == "None":
    #             return HTMLResponse(
    #                 content=render_html(g, ns_base=ns_base), status_code=200
    #             )
    #     elif media_type == "application/ld+json":
    #         g.namespace_manager.bind("base", ns_base)
    #         try:
    #             return Response(
    #                 content=g.serialize(
    #                     encoding="utf-8",
    #                     format=media_type,
    #                     auto_compact=True,
    #                 ).decode("utf-8"),
    #                 media_type=media_type,
    #             )
    #         except rdflib.plugin.PluginException:
    #             continue
    #     else:
    #         try:
    #             return Response(
    #                 content=g.serialize(
    #                     base=ns_base, encoding="utf-8", format=media_type
    #                 ).decode("utf-8"),
    #                 media_type=media_type,
    #             )
    #         except rdflib.plugin.PluginException:
    #             continue
    # else:
    #     return HTMLResponse(content=render_html(g), status_code=200)
    return Response(
        content=g.serialize(
            encoding="utf-8",
            format="application/ld+json",
            auto_compact=True,
        ).decode("utf-8"),
        media_type="application/json",
    )


@app.get(
    "/ark:/{naan}/{rest_of_path:path}", response_class=RedirectResponse, tags=["util"]
)
async def _ark(naan: int, request: Request):
    """normalize request to not have slash (/) preceding ark naan."""
    return RedirectResponse(
        url=str(request.url).replace("ark:/", "ark:"), status_code=301
    )


@app.get("/2021/04/marda-dd/test", summary="MaRDA DD Test", tags=["legacy"])
async def marda_dd_test(accept: Optional[str] = Header(None)):
    return response_for(
        TERMS,
        accept,
        TEST_BASE,
    )


@app.get("/ark:57802/2021/08/mardaphonons", summary="MaRDA Phonons", tags=["legacy"])
async def marda_phonons(accept: Optional[str] = Header(None)):
    return response_for(
        g=load_ttl(
            "https://raw.githubusercontent.com/marda-dd/phonons/main/concept_scheme.ttl"
        ),
        accept=accept,
        ns_base="https://n2t.net/ark:57802/2021/08/marda-phonons/",
        html_profile="SKOS",
    )


errors = {
    "too_late": HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cannot update namespaces dated earlier than the current month",
    ),
    "too_early": HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cannot update namespaces dated later than the current month",
    ),
}


def check_naan(mdb: MongoDatabase, naan: int):
    if mdb.naans.find_one({"_id": naan}) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This server is not a name mapping authority for ark naan {naan}",
        )


def check_too_early(year, month):
    dt_now: datetime = now()
    if year > dt_now.year or (year == dt_now.year and month > dt_now.month):
        raise errors["too_early"]


def check_too_late(year, month):
    dt_now: datetime = now()
    if (year < dt_now.year) or (year == dt_now.year and month < dt_now.month):
        raise errors["too_late"]


@app.get(
    "/ark:{naan}/{year}/{month}/{org}/{repo}/{term}",
    response_model=VocabularyTerm,
    tags=["terms"],
)
async def get_vocabulary_term(
    naan: int,
    year: int,
    month: int,
    org: str,
    repo: str,
    term: str,
    mdb: MongoDatabase = Depends(mongo_db),
    accept: Optional[str] = Header(None),
):
    """

    Cannot match on URL fragment (i.e., `{repo}#{term}`) because a browser does not send the
    fragment to the server.
    """
    check_naan(mdb, naan)
    check_too_early(year, month)

    term_namespace = f"ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    term_doc = raise404_if_none(
        mdb.terms.find_one(
            {"_aliases": {"$elemMatch": {"ns": term_namespace, "local": term}}}
        )
    )

    docs = []
    for d in [term_doc]:
        subject = next(
            alias["local"] for alias in d["_aliases"] if alias["ns"] == term_namespace
        )
        predicate_objects = dissoc(d, "_id", "_aliases")
        docs.append((subject, predicate_objects))
    g = into_rdflib_graph(docs=docs, term_namespace=term_namespace, single_term=True)
    return response_for(g, accept, ns_base=term_namespace)


@app.get(
    "/ark:{naan}/{year}/{month}/{org}/{repo}/",
    response_model=List[VocabularyTerm],
    tags=["util"],
)
async def _list_vocabulary_terms(
    naan: int,
    year: int,
    month: int,
    org: str,
    repo: str,
    request: Request,
):
    term_namespace = f"ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    return RedirectResponse(
        url=str(request.url).replace(f"{term_namespace}/", term_namespace),
        status_code=301,
    )


@app.get(
    "/ark:{naan}/{year}/{month}/{org}/{repo}",
    response_model=List[VocabularyTerm],
    tags=["vocabularies"],
)
async def list_vocabulary_terms(
    naan: int,
    year: int,
    month: int,
    org: str,
    repo: str,
    mdb: MongoDatabase = Depends(mongo_db),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    check_too_early(year, month)

    term_namespace = f"ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    term_docs = list(mdb.terms.find({"_aliases.ns": term_namespace}))
    if not term_docs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="none found")

    docs = []
    for d in term_docs:
        subject = next(
            alias["local"] for alias in d["_aliases"] if alias["ns"] == term_namespace
        )
        predicate_objects = dissoc(d, "_id", "_aliases")
        docs.append((subject, predicate_objects))
    g = into_rdflib_graph(
        docs=docs,
        term_namespace=term_namespace,
    )
    return response_for(g, accept, ns_base=term_namespace)


term_namespace_pattern = re.compile(
    r"ark:(?P<naan>\d{5,})/(?P<year>\d{4})/(?P<month>\d{2})/(?P<org>[\w\-]+)/(?P<repo>[\w\-]+)"
)


def term_namespace_in_past(term_namespace) -> bool:
    if (m := re.match(term_namespace_pattern, term_namespace)) is None:
        raise ValueError(f"Invalid term namespace '{term_namespace}'.")
    year, month = int(m.group("year")), int(m.group("month"))
    dt_now: datetime = now()
    return (year < dt_now.year) or (year == dt_now.year and month < dt_now.month)


@app.post(
    "/ark:{naan}/{year}/{month}/{org}/{repo}:import",
    response_model=List[VocabularyTerm],
    tags=["vocabularies"],
)
async def import_vocabulary_terms(
    naan: int,
    year: int,
    month: int,
    org: str,
    repo: str,
    term_imports: List[VocabularyTermImport],
    client: NamespaceClient = Depends(get_current_ns_client),
    mdb: MongoDatabase = Depends(mongo_db),
):
    check_naan(mdb, naan)
    check_too_early(year, month)
    check_too_late(year, month)

    term_namespace = f"ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    if client.allow not in term_namespace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client not allowed to import terms to this namespace.",
        )

    term_imports_todo = {}
    for term_import in term_imports:
        reference_path, target_name = (
            term_import.reference_path,
            term_import.target_name,
        )
        reference_namespace, _, source_name = reference_path.rpartition("/")
        if (m := re.match(term_namespace_pattern, reference_namespace)) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid term namespace '{reference_namespace}' for '{reference_path}'.",
            )
        year, month = int(m.group("year")), int(m.group("month"))
        dt_now: datetime = now()
        if (year > dt_now.year) or (year == dt_now.year and month >= dt_now.month):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot import from future or current-month namespaces",
            )

        term_doc = mdb.terms.find_one(
            {
                "_aliases": {
                    "$elemMatch": {
                        "ns": reference_namespace,
                        "local": source_name,
                    }
                }
            },
            {"_id": 1},
        )
        if term_doc is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No entry for {reference_path} found.",
            )
        term_imports_todo[term_doc["_id"]] = target_name

    mdb.terms.bulk_write(
        [
            UpdateOne(
                {"_id": doc_id},
                {
                    "$addToSet": {
                        "_aliases": {"ns": term_namespace, "local": target_name}
                    }
                },
            )
            for doc_id, target_name in term_imports_todo.items()
        ]
    )
    return list(mdb.terms.find({"_id": {"$in": list(term_imports_todo.keys())}}))


def clone_term_from(
    term_parts: VocabularyTermParts, mdb: MongoDatabase, doc_id: ObjectId
) -> ObjectId:
    to_clone = dissoc(mdb.terms.find_one({"_id": doc_id}), "_id", "_aliases")
    new_doc = merge(
        to_clone, {"_aliases": [{"ns": term_parts.ns, "local": term_parts.local}]}
    )
    rv: InsertOneResult = mdb.terms.insert_one(new_doc)
    return rv.inserted_id


@app.post(
    "/ark:{naan}/{year}/{month}/{org}/{repo}:update",
    response_model=List[VocabularyTerm],
    tags=["vocabularies"],
)
async def update_vocabulary_terms(
    naan: int,
    year: int,
    month: int,
    org: str,
    repo: str,
    term_updates: List[VocabularyTermUpdates],
    client: NamespaceClient = Depends(get_current_ns_client),
    mdb: MongoDatabase = Depends(mongo_db),
):
    """
    Updates will be attempted in the order given by `term_updates`. This operation is NOT atomic.
    That is, if N updates are given, and the Nth update fails for some reason, the first N-1 updates
    will have been applied.
    """
    check_naan(mdb, naan)
    check_too_early(year, month)
    check_too_late(year, month)

    term_namespace = f"ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    if client.allow not in term_namespace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client not allowed to import terms to this namespace.",
        )
    term_doc_ids = []
    for term_up in term_updates:
        term_name, updates = term_up.term_name, term_up.updates
        term_doc = mdb.terms.find_one(
            {"_aliases": {"$elemMatch": {"ns": term_namespace, "local": term_name}}},
            {"_id": 1, "_aliases": 1},
        )
        if term_doc is not None:
            if any(term_namespace_in_past(a) for a in term_doc["_aliases"]):
                term_doc_id = clone_term_from(
                    VocabularyTermParts(ns=term_namespace, local=term_name),
                    mdb,
                    term_doc["_id"],
                )
            else:
                term_doc_id = term_doc["_id"]
            mdb.terms.update_one({"_id": term_doc_id}, {"$set": updates})
        else:
            rv = mdb.terms.insert_one(
                merge(
                    updates,
                    {"_aliases": [{"ns": term_namespace, "local": term_name}]},
                )
            )
            term_doc_id = rv.inserted_id
        term_doc_ids.append(term_doc_id)
    return list(mdb.terms.find({"_id": {"$in": term_doc_ids}}))


@app.get("/ark:{naan}/{rest_of_path:path}", tags=["util"])
async def ark(
    naan: int,
    rest_of_path,
    request: Request,
    mdb: MongoDatabase = Depends(mongo_db),
    accept: Optional[str] = Header(None),
):
    """Fall-through route."""
    check_naan(mdb, naan)
    parts = rest_of_path.split("/")
    basename = parts[0].replace("-", "")
    leaf_and_variants = parts[-1].split(".")
    leaf, variants = leaf_and_variants[0], leaf_and_variants[1:]
    subparts = (parts[1:-1] + [leaf]) if len(parts) > 1 else []

    ark_map_url = ark_map(mdb, naan=str(naan)).get(f"ark:{naan}/{basename}")
    # TODO support ?info inflection via {who,what,when,how} columns in ark_map.csv
    #   See: https://n2t.net/e/n2t_apidoc.html#identifier-metadata
    if ark_map_url:
        return RedirectResponse(url=ark_map_url, status_code=303)
    else:
        return {
            "resolver": str(request.base_url),
            "nma": str(request.base_url).split("/")[-2],
            "naan": "57802",
            "basename": basename,
            "subparts": subparts,
            "variants": variants,
        }


@app.post("/token", response_model=Token, tags=["auth"])
async def login_for_access_token(
    form_data: OAuth2PasswordOrClientCredentialsRequestForm = Depends(),
    mdb: MongoDatabase = Depends(mongo_db),
):
    if form_data.grant_type == "password":
        user = authenticate_user(mdb, form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token_expires = timedelta(**ACCESS_TOKEN_EXPIRES.dict())
        access_token = create_access_token(
            data={"sub": f"user:{user.username}"}, expires_delta=access_token_expires
        )
    else:  # form_data.grant_type == "client_credentials"
        site = authenticate_ns_client(mdb, form_data.client_id, form_data.client_secret)
        if not site:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect client_id or client_secret",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # TODO make below an absolute time
        access_token_expires = timedelta(**ACCESS_TOKEN_EXPIRES.dict())
        access_token = create_access_token(
            data={"sub": f"client:{form_data.client_id}"},
            expires_delta=access_token_expires,
        )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires": ACCESS_TOKEN_EXPIRES.dict(),
    }


def _generate_credentials_for_ns_client(mdb: MongoDatabase, user: User, ns: str):
    client_allowed = mdb.users.find_one({"username": user.username, "allow": ns})
    if not client_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You're not allowed to generate credentials for this namespace.",
        )

    # XXX client_id must not contain a ':' because HTTPBasic auth splits on ':'.
    generate_client_id = True
    client_id = None
    while generate_client_id:
        client_id = generate_secret(length=12, include_punctuation=False)
        generate_client_id = (
            mdb.ns_clients.find_one({"client_id": client_id}) is not None
        )
    client_secret = generate_secret(length=18)
    hashed_client_secret = get_password_hash(client_secret)

    mdb.ns_clients.insert_one(
        NamespaceClient(
            client_id=client_id,
            hashed_client_secret=hashed_client_secret,
            allow=ns,
            created_by=user.username,
        ).dict(exclude_unset=True)
    )

    return {
        "client_id": client_id,
        "client_secret": client_secret,
    }


@app.post(
    "/ark:{naan}/{year}/{month}/{org}:generateCredentials",
    response_model=ClientCredentials,
    tags=["auth"],
)
def generate_credentials_for_org_ns_client(
    naan: int,
    year: int,
    month: int,
    org: str,
    mdb: MongoDatabase = Depends(mongo_db),
    user: User = Depends(get_current_active_user),
):
    check_naan(mdb, naan)
    check_too_early(year, month)
    check_too_late(year, month)

    org_namespace = f"ark:{naan}/{year}/{month:02d}/{org}"
    return _generate_credentials_for_ns_client(mdb, user, org_namespace)


@app.post(
    "/ark:{naan}/{year}/{month}/{org}/{repo}:generateCredentials",
    response_model=ClientCredentials,
    tags=["auth"],
)
def generate_credentials_for_term_ns_client(
    naan: int,
    year: int,
    month: int,
    org: str,
    repo: str,
    mdb: MongoDatabase = Depends(mongo_db),
    user: User = Depends(get_current_active_user),
):
    check_naan(mdb, naan)
    check_too_early(year, month)
    check_too_late(year, month)

    term_namespace = f"ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    return _generate_credentials_for_ns_client(mdb, user, term_namespace)


@app.on_event("startup")
async def ensure_initial_resources_on_boot():
    """ensure these resources are loaded when (re-)booting the system."""
    mdb = mongo_db()

    with open(REPO_ROOT_DIR.joinpath("ark_map.csv")) as csvfile:
        reader = csv.DictReader(csvfile)
        docs = [{"_id": row["ark"], "_t": row["url"]} for row in reader]
    mdb.arks.bulk_write([ReplaceOne(pick(["_id"], d), d, upsert=True) for d in docs])

    with open(REPO_ROOT_DIR.joinpath("ark_naan_shoulder_map.csv")) as csvfile:
        reader = csv.DictReader(csvfile)
        naan_shoulders = defaultdict(set)
        for row in reader:
            naan_shoulders[int(row["naan"])].add(row["shoulder"])
        docs = [
            {"_id": naan, "shoulders": list(shoulders)}
            for naan, shoulders in naan_shoulders.items()
        ]
    mdb.naans.bulk_write([ReplaceOne(pick(["_id"], d), d, upsert=True) for d in docs])
