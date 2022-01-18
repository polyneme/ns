from pathlib import Path

import json
import pylode

import re

from datetime import datetime

import csv
import os
from collections import defaultdict

from pymongo.results import DeleteResult
from starlette import status
from starlette.responses import PlainTextResponse
from toolz import dissoc, assoc, merge
from typing import Optional, List, Union

from fastapi import FastAPI, Request, Response, Header, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import rdflib
from rdflib import Graph, RDF, OWL, SKOS
from pymongo import ReplaceOne
from pymongo.database import Database as MongoDatabase

from xyz_polyneme_ns.auth import get_current_agent, get_password_hash
from xyz_polyneme_ns.db import mongo_db
from xyz_polyneme_ns.idgen import (
    ark_map,
    ark_naan_shoulder_map,
    create_ark_bon,
)
from xyz_polyneme_ns.models import (
    Doc,
    TermImport,
    DocUpdate,
    Agent,
    AgentType,
    AgentIn,
    get_agent_uri,
    ArkShoulder,
    ArkNaan,
    BASE32_LETTERS,
    get_shoulder,
)
from xyz_polyneme_ns.util import (
    REPO_ROOT_DIR,
    pick,
    now,
    raise404_if_none,
)

tags_metadata = [
    {
        "name": "namespaces",
        "description": "the things that contain terms (aka vocabularies, ontologies, etc.)",
    },
    {"name": "terms", "description": "the things in namespaces"},
    {
        "name": "skolems",
        "description": "things that don't need to be identified by human-readable signs",
    },
    {"name": "agents", "description": "do stuff using credentials"},
    {"name": "util", "description": "redirects, catch-alls, etc."},
    {
        "name": "legacy",
        "description": "stuff that was here before, with URLs I don't want to break",
    },
]

app = FastAPI(
    title="Termeric API",
    version="0.1.0",
    description="Termeric is *term* *e*gress, *r*evision, and *i*ngress -- *c*alendarized.",
    openapi_tags=tags_metadata,
)


API_HOST = os.getenv("API_HOST")

DEFAULT_JSONLD_CONTEXT = {
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def ensure_context(d):
    return merge({"@context": DEFAULT_JSONLD_CONTEXT}, d)


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


def response_for(g: rdflib.Graph, accept: str):
    types_ = sorted_media_types(accept)
    for media_type in types_:
        if media_type == "text/html" and pylode_able(g):
            html = pylode.OntDoc(g).make_html()
            return HTMLResponse(content=html)
        else:
            try:
                return Response(
                    content=g.serialize(
                        encoding="utf-8", format=media_type, auto_compact=True
                    ).decode("utf-8"),
                    media_type=media_type,
                )
            except rdflib.plugin.PluginException:
                continue
    else:
        return PlainTextResponse(content=g.serialize(format="turtle"), status_code=200)


def check_naan(mdb: MongoDatabase, naan: ArkNaan):
    if mdb.naans.find_one({"_id": naan}) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This server is not a name mapping authority for ark naan {naan}",
        )


def check_too_late(year, month):
    dt_now: datetime = now()
    if (year < dt_now.year) or (year == dt_now.year and month < dt_now.month):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update namespaces dated earlier than the current month",
        )


def check_can_update_term(agent: Agent, org: str, repo: str):
    if not (
        any(item == org or item == f"{org}/{repo}" for item in agent.can_admin)
        or any(item == f"{org}/{repo}" for item in agent.can_edit)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent {agent.username} cannot update term in {org}/{repo}.",
        )


def check_can_update_skolem(agent: Agent, shoulder: ArkShoulder):
    if not any(item == shoulder for item in agent.can_admin_shoulders):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent {agent.username} cannot update skolem with shoulder {shoulder}.",
        )


def check_shoulder_registered(mdb: MongoDatabase, naan: ArkNaan, shoulder: ArkShoulder):
    shoulders = ark_naan_shoulder_map(mdb)[naan]
    if shoulder not in shoulders:
        raise ValueError(
            f"Shoulder {shoulder} is not registered for naan {naan} "
            f"(must be one of {shoulders})."
        )


def raise_forbidden(detail):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def capability_subset(agent_can: list, requester_can: list) -> bool:
    return all(
        any(
            repo.startwsith(item if "/" in item else f"{item}/")
            for item in requester_can
        )
        for repo in agent_can
    )


def check_can_manage(requester: Agent, agent: Agent):
    if agent.can_admin:
        raise_forbidden("No one can manage agents that can_admin.")
    if requester.type == AgentType.software_agent:
        raise_forbidden("Software agents cannot manage other agents.")
    if agent.type == AgentType.person:
        if not capability_subset(agent.can_edit, requester.can_admin):
            raise_forbidden(
                "A requester person agent can manage a target person agent "
                "only if the target agent's can_edit capabilities "
                "are a subset of the requester's can_admin capabilities."
            )
    elif agent.type == AgentType.software_agent:
        if not capability_subset(
            agent.can_edit, requester.can_edit + requester.can_admin
        ):
            raise_forbidden(
                "A requester person can manage a target software_agent "
                "only if the target agent's can_edit capabilities "
                "are a subset of the requester's can_edit or can_admin capabilities."
            )


def unset_equivalences():
    return {
        "$unset": {
            "owl:equivalentProperty": "",
            "owl:equivalentClass": "",
            "owl:sameAs": "",
        }
    }


def load_graph_from_file(filename: Union[Path, str], format_=None) -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(str(filename), format=format_)
    return g


def jsonld_doc_response(jsonld_doc, accept):
    jsonld_doc = dissoc(jsonld_doc, "_id")
    g = Graph()
    g.parse(data=json.dumps(jsonld_doc), format="json-ld")
    return response_for(g, accept)


def pylode_able(g: rdflib.Graph) -> bool:
    return g.value(predicate=RDF.type, object=OWL.Ontology) or g.value(
        predicate=RDF.type, object=SKOS.ConceptScheme
    )


@app.get("/2021/04/marda-dd/test", summary="MaRDA DD Test", tags=["legacy"])
async def marda_dd_test(accept: Optional[str] = Header(None)):
    return response_for(
        g=load_graph_from_file(
            "https://raw.githubusercontent.com/polyneme/ns/main/hello_world.ttl",
            format_="turtle",
        ),
        accept=accept,
    )


@app.get("/ark:57802/2021/08/mardaphonons", summary="MaRDA Phonons", tags=["legacy"])
async def marda_phonons(accept: Optional[str] = Header(None)):
    # XXX important that this route is registered *before*
    #     the more general "/ark:{naan}/{rest_of_path:path}" route.
    return response_for(
        g=load_graph_from_file(
            "https://raw.githubusercontent.com/marda-dd/phonons/main/concept_scheme.ttl",
            format_="turtle",
        ),
        accept=accept,
    )


@app.post(
    "/ark:{naan}/{year}/{month}/{org}/{repo}/{term}:import",
    status_code=status.HTTP_201_CREATED,
    tags=["terms"],
)
async def import_term(
    naan: ArkNaan,
    year: int,
    month: int,
    org: str,
    repo: str,
    term: str,
    term_import: TermImport,
    agent: Agent = Depends(get_current_agent),
    mdb: MongoDatabase = Depends(mongo_db),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    check_too_late(year, month)
    check_can_update_term(agent, org, repo)

    term_tgt_uri = f"ark:{naan}/{year}/{month:02d}/{org}/{repo}/{term}"
    term_src_uri = term_import.term_uri

    term_src_namespace, _, source_name = term_src_uri.rpartition("/")
    if (m := re.match(term_namespace_pattern, term_src_namespace)) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid term source namespace '{term_src_namespace}'.",
        )
    year, month = int(m.group("year")), int(m.group("month"))
    dt_now: datetime = now()
    if (year > dt_now.year) or (year == dt_now.year and month >= dt_now.month):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot import from future or current-month namespaces",
        )

    term_src_doc = mdb.terms.find_one({"@id": term_src_uri})
    if term_src_doc is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No entry for {term_src_doc} found.",
        )
    mdb.terms.insert_one(
        ensure_context(assoc(dissoc(term_src_doc, "_id", "@id"), "@id", term_tgt_uri))
    )
    term_doc = mdb.terms.find_one({"@id": term_tgt_uri})
    return jsonld_doc_response(term_doc, accept)


@app.post(
    "/ark:{naan}/{shoulder}",
    status_code=status.HTTP_201_CREATED,
    tags=["skolems"],
)
async def create_skolem(
    naan: ArkNaan,
    shoulder: ArkShoulder,
    skolem_in: Doc,
    mdb: MongoDatabase = Depends(mongo_db),
    agent: Agent = Depends(get_current_agent),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    check_can_update_skolem(agent, shoulder)
    check_shoulder_registered(mdb, naan, shoulder)

    ark_new = create_ark_bon(mdb=mdb, naan=naan, shoulder=shoulder)
    ark_doc = assoc(skolem_in.dict(), "@id", f"{API_HOST}/{ark_new}")
    mdb.arks.replace_one({"_id": ark_new}, ensure_context(ark_doc), upsert=False)
    ark_doc = mdb.arks.find_one({"_id": ark_new})
    ark_map.cache_clear()
    return jsonld_doc_response(ark_doc, accept)


@app.get(
    "/ark:{naan}/{assigned_base_name}",
    tags=["skolems"],
)
async def get_skolem(
    naan: ArkNaan,
    assigned_base_name: str,
    mdb: MongoDatabase = Depends(mongo_db),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)

    indiv_uri = f"{API_HOST}/ark:{naan}/{assigned_base_name}"
    indiv_doc = raise404_if_none(mdb.arks.find_one({"@id": indiv_uri}))

    return jsonld_doc_response(indiv_doc, accept)


@app.patch(
    "/ark:{naan}/{assigned_base_name}",
    tags=["skolems"],
)
async def update_skolem(
    naan: ArkNaan,
    assigned_base_name: str,
    indiv_update: DocUpdate,
    mdb: MongoDatabase = Depends(mongo_db),
    agent: Agent = Depends(get_current_agent),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    check_can_update_skolem(agent, get_shoulder(assigned_base_name))
    indiv_uri = f"{API_HOST}/ark:{naan}/{assigned_base_name}"
    raise404_if_none(mdb.arks.find_one({"@id": indiv_uri}))

    mdb.arks.update_one({"@id": indiv_uri}, unset_equivalences())
    mdb.arks.update_one({"@id": indiv_uri}, indiv_update.update)
    indiv_doc = mdb.arks.find_one({"@id": indiv_uri})
    return jsonld_doc_response(indiv_doc, accept)


@app.post(
    "/ark:{naan}/{year}/{month}/{org}/{repo}",
    status_code=status.HTTP_201_CREATED,
    tags=["terms"],
)
async def create_term(
    naan: ArkNaan,
    year: int,
    month: int,
    org: str,
    repo: str,
    term: str,
    term_in: Doc,
    mdb: MongoDatabase = Depends(mongo_db),
    agent: Agent = Depends(get_current_agent),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    check_too_late(year, month)
    check_can_update_term(agent, org, repo)

    term_uri = f"{API_HOST}/ark:{naan}/{year}/{month:02d}/{org}/{repo}/{term}"
    if mdb.terms.find_one({"@id": term_uri}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Term already exists!"
        )
    term_doc = assoc(term_in.dict(), "@id", term_uri)
    mdb.terms.insert_one(ensure_context(term_doc))
    term_doc = mdb.terms.find_one({"@id": term_uri})
    return jsonld_doc_response(term_doc, accept)


@app.get(
    "/ark:{naan}/{year}/{month}/{org}/{repo}/{term}",
    tags=["terms"],
)
async def get_term(
    naan: ArkNaan,
    year: int,
    month: int,
    org: str,
    repo: str,
    term: str,
    mdb: MongoDatabase = Depends(mongo_db),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)

    term_uri = f"{API_HOST}/ark:{naan}/{year}/{month:02d}/{org}/{repo}/{term}"
    term_doc = raise404_if_none(mdb.terms.find_one({"@id": term_uri}))

    return jsonld_doc_response(term_doc, accept)


@app.patch(
    "/ark:{naan}/{year}/{month}/{org}/{repo}/{term}",
    tags=["terms"],
)
async def update_term(
    naan: ArkNaan,
    year: int,
    month: int,
    org: str,
    repo: str,
    term: str,
    term_update: DocUpdate,
    mdb: MongoDatabase = Depends(mongo_db),
    agent: Agent = Depends(get_current_agent),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    check_too_late(year, month)
    check_can_update_term(agent, org, repo)
    term_uri = f"{API_HOST}/ark:{naan}/{year}/{month:02d}/{org}/{repo}/{term}"
    raise404_if_none(mdb.terms.find_one({"@id": term_uri}))

    mdb.terms.update_one({"@id": term_uri}, unset_equivalences())
    mdb.terms.update_one({"@id": term_uri}, term_update.update)
    term_doc = mdb.terms.find_one({"@id": term_uri})
    return jsonld_doc_response(term_doc, accept)


@app.delete(
    "/ark:{naan}/{year}/{month}/{org}/{repo}/{term}",
    tags=["terms"],
)
async def delete_term(
    naan: ArkNaan,
    year: int,
    month: int,
    org: str,
    repo: str,
    term: str,
    mdb: MongoDatabase = Depends(mongo_db),
    agent: Agent = Depends(get_current_agent),
):
    check_naan(mdb, naan)
    check_too_late(year, month)
    check_can_update_term(agent, org, repo)
    term_uri = f"{API_HOST}/ark:{naan}/{year}/{month:02d}/{org}/{repo}/{term}"
    raise404_if_none(mdb.terms.find_one({"@id": term_uri}))

    rv: DeleteResult = mdb.terms.delete_one({"@id": term_uri})
    return {"n_deleted": rv.deleted_count}


@app.post(
    "/ark:{naan}/{year}/{month}/{org}",
    status_code=status.HTTP_201_CREATED,
    tags=["namespaces"],
)
async def create_namespace(
    naan: ArkNaan,
    year: int,
    month: int,
    org: str,
    repo: str,
    ns_in: Doc,
    mdb: MongoDatabase = Depends(mongo_db),
    agent: Agent = Depends(get_current_agent),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    check_too_late(year, month)
    check_can_update_term(agent, org, repo)

    term_namespace_uri = f"{API_HOST}/ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    if mdb.namespaces.find_one({"@id": term_namespace_uri}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Namespace already exists!"
        )

    ns_doc = merge(ns_in.dict(), {"@id": term_namespace_uri, "@type": "owl:Ontology"})
    mdb.namespaces.insert_one(ensure_context(ns_doc))
    ns_doc = mdb.namespaces.find_one({"@id": term_namespace_uri})
    return jsonld_doc_response(dissoc(ns_doc, "_id"), accept)


@app.get(
    "/ark:{naan}/{year}/{month}/{org}/{repo}",
    tags=["namespaces"],
)
async def get_namespace(
    naan: ArkNaan,
    year: int,
    month: int,
    org: str,
    repo: str,
    mdb: MongoDatabase = Depends(mongo_db),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)

    term_namespace_uri = f"{API_HOST}/ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    ns_doc = raise404_if_none(mdb.namespaces.find_one({"@id": term_namespace_uri}))
    term_docs = list(mdb.terms.find({"@id": {"$regex": rf"^{term_namespace_uri}"}}))

    g = Graph()
    g.parse(data=json.dumps(dissoc(ns_doc, "_id")), format="json-ld")
    for doc in term_docs:
        g.parse(data=json.dumps(dissoc(doc, "_id")), format="json-ld")
    return response_for(g, accept)


@app.patch(
    "/ark:{naan}/{year}/{month}/{org}/{repo}",
    tags=["namespaces"],
)
async def update_namespace(
    naan: ArkNaan,
    year: int,
    month: int,
    org: str,
    repo: str,
    update: DocUpdate,
    mdb: MongoDatabase = Depends(mongo_db),
    agent: Agent = Depends(get_current_agent),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    check_too_late(year, month)
    check_can_update_term(agent, org, repo)
    term_namespace_uri = f"{API_HOST}/ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    raise404_if_none(mdb.namespaces.find_one({"@id": term_namespace_uri}))

    mdb.namespaces.update_one({"@id": term_namespace_uri}, update.update)
    ns_doc = mdb.namespaces.find_one({"@id": term_namespace_uri})
    return jsonld_doc_response(ns_doc, accept)


@app.delete(
    "/ark:{naan}/{year}/{month}/{org}/{repo}",
    tags=["namespaces"],
)
async def delete_namespace(
    naan: ArkNaan,
    year: int,
    month: int,
    org: str,
    repo: str,
    mdb: MongoDatabase = Depends(mongo_db),
    agent: Agent = Depends(get_current_agent),
):
    check_naan(mdb, naan)
    check_too_late(year, month)
    check_can_update_term(agent, org, repo)
    term_namespace_uri = f"{API_HOST}/ark:{naan}/{year}/{month:02d}/{org}/{repo}"
    raise404_if_none(mdb.namespaces.find_one({"@id": term_namespace_uri}))

    rv: DeleteResult = mdb.namespaces.delete_one({"@id": term_namespace_uri})
    return {"n_deleted": rv.deleted_count}


term_namespace_pattern = re.compile(
    rf"{API_HOST}/ark:(?P<naan>\d{5,})/(?P<year>\d{4})/(?P<month>\d{2})/(?P<org>[\w\-]+)/(?P<repo>[\w\-]+)"
)


@app.post(
    "/ark:{naan}/9999/12/system/agents",
    status_code=status.HTTP_201_CREATED,
    tags=["agents"],
)
async def create_agent(
    naan: ArkNaan,
    agent_in: AgentIn,
    mdb: MongoDatabase = Depends(mongo_db),
    requester_agent: Agent = Depends(get_current_agent),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    check_can_manage(requester_agent, target_agent)

    agent_uri = get_agent_uri(naan, agent_in.username)
    if mdb.agents.find_one({"id": agent_uri}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Agent already exists!"
        )
    target_agent = Agent(
        **agent_in.dict(),
        hashed_password=get_password_hash(agent_in.password),
        can_admin=[],
        id=agent_uri,
    )

    mdb.agents.insert_one(ensure_context(target_agent.dict()))
    agent_doc = mdb.namespaces.find_one({"id": agent_uri})
    return jsonld_doc_response(agent_doc, accept)


@app.get(
    "/ark:{naan}/9999/12/system/agents/{username}",
    tags=["agents"],
)
async def get_agent(
    naan: ArkNaan,
    username: str,
    mdb: MongoDatabase = Depends(mongo_db),
    requester_agent: Agent = Depends(get_current_agent),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    agent_uri = get_agent_uri(naan, username)
    agent_doc = raise404_if_none(mdb.agents.find_one({"id": agent_uri}))
    target_agent = Agent(**agent_doc.dict())
    check_can_manage(requester_agent, target_agent)

    return jsonld_doc_response(agent_doc, accept)


@app.patch(
    "/ark:{naan}/9999/12/system/agents/{username}",
    tags=["agents"],
)
async def update_agent(
    naan: ArkNaan,
    username: str,
    update: DocUpdate,
    mdb: MongoDatabase = Depends(mongo_db),
    requester_agent: Agent = Depends(get_current_agent),
    accept: Optional[str] = Header(None),
):
    check_naan(mdb, naan)
    agent_uri = get_agent_uri(naan, username)
    agent_doc = raise404_if_none(mdb.agents.find_one({"id": agent_uri}))
    target_agent = Agent(**agent_doc.dict())
    check_can_manage(requester_agent, target_agent)

    mdb.agents.update_one({"id": agent_uri}, update.update)
    agent_doc = mdb.namespaces.find_one({"id": agent_uri})
    return jsonld_doc_response(agent_doc, accept)


@app.delete(
    "/ark:{naan}/9999/12/system/agents/{username}",
    tags=["agents"],
)
async def delete_agent(
    naan: ArkNaan,
    username: str,
    mdb: MongoDatabase = Depends(mongo_db),
    requester_agent: Agent = Depends(get_current_agent),
):
    check_naan(mdb, naan)
    agent_uri = get_agent_uri(naan, username)
    agent_doc = raise404_if_none(mdb.agents.find_one({"id": agent_uri}))
    target_agent = Agent(**agent_doc.dict())
    check_can_manage(requester_agent, target_agent)

    rv: DeleteResult = mdb.agents.delete_one({"id": agent_uri})
    return {"n_deleted": rv.deleted_count}


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


@app.get(
    "/ark:/{naan}/{rest_of_path:path}",
    response_class=RedirectResponse,
    tags=["util"],
    summary="Get ARK (Slash Before NAAN)",
)
async def _ark(naan: ArkNaan, request: Request):
    """normalize request to not have slash (/) preceding ark naan."""
    return RedirectResponse(
        url=str(request.url).replace("ark:/", "ark:"), status_code=301
    )


@app.get(
    "/ark:{naan}/{year}/{month}/{org}/{repo}/",
    tags=["util"],
    summary="Get Namespace (Trailing Slash)",
)
async def _get_namespace(
    naan: ArkNaan,
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
    "/ark:{naan}/{rest_of_path:path}",
    tags=["util"],
    summary="Get ARK (Arbitrary ID Pattern)",
)
async def ark(
    naan: ArkNaan,
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

    ark_map_url = ark_map(mdb, naan=naan).get(f"ark:{naan}/{basename}")
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
