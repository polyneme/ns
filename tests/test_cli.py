import re

import json

from typing import List

import click.testing
from typer.testing import CliRunner

from xyz_polyneme_ns import cli
from xyz_polyneme_ns.db import mongo_db
from xyz_polyneme_ns.util import now


def cli_invoke(args: List[str]) -> click.testing.Result:
    return CliRunner().invoke(cli.app, args)


def test_hello():
    result = cli_invoke(["hello", "Donny"])
    assert result.exit_code == 0


def test_goodbye():
    result = cli_invoke(["goodbye", "Donny"])
    assert result.exit_code == 0
    assert result.stdout.startswith("Bye")
    result = cli_invoke(["goodbye", "--formal", "Donny"])
    assert result.stdout.startswith("Goodbye")


def test_get_legacy_routes():
    result = cli_invoke(["get", "/2021/04/marda-dd/test", "--accept", "text/turtle"])
    assert result.stdout.startswith("@prefix")
    assert "vulgar" in result.stdout

    result = cli_invoke(
        ["get", "/ark:57802/2021/08/mardaphonons", "--accept", "text/turtle"]
    )
    assert result.stdout.startswith("@prefix")
    assert "skos:ConceptScheme" in result.stdout


def test_crud_individual():
    result = cli_invoke(["create-individual", "fk1", '{"rdfs:label": "donny"}'])
    assert result.exit_code == 0
    doc_c = json.loads(result.stdout)
    assert "fk1" in doc_c["@id"]

    assigned_base_name = re.search(r"ark:\d{5}/(?P<abn>\w+)", doc_c["@id"]).group("abn")
    result = cli_invoke(["get-individual", assigned_base_name])
    doc_r = json.loads(result.stdout)
    assert doc_r == doc_c

    result = cli_invoke(
        [
            "update-individual",
            assigned_base_name,
            '{"$set": {"rdfs:comment": "definitely a person"}}',
        ]
    )
    doc_u = json.loads(result.stdout)
    assert doc_u != doc_c
    assert doc_c.get("rdfs:comment") is None
    assert doc_u.get("rdfs:comment") is not None

    mdb = mongo_db()
    mdb.arks.delete_one({"@id": doc_c["@id"]})


def test_crud_namespace():
    dt = now()
    test_org = f"/{dt.year}/{dt.month}/testorg"
    result = cli_invoke(["create-namespace", test_org, "testrepo"])
    assert result.exit_code == 0
    doc_c = json.loads(result.stdout)
    assert "/2022/01/testorg/testrepo" in doc_c["@id"]
    assert doc_c["@type"] == "owl:Ontology"

    result = cli_invoke(["get-namespace", f"{test_org}/testrepo"])
    doc_r = json.loads(result.stdout)
    assert doc_c == doc_r

    result = cli_invoke(
        [
            "update-namespace",
            f"{test_org}/testrepo",
            '{"$set": {"dc:title": "My Test Namespace"}}',
        ]
    )
    doc_u = json.loads(result.stdout)
    assert doc_u != doc_c
    assert doc_c.get("dc:title") is None
    assert doc_u.get("dc:title") is not None

    mdb = mongo_db()
    mdb.namespaces.delete_one({"@id": doc_c["@id"]})


def test_cannot_create_past_namespace():
    result = cli_invoke(["create-namespace", "/1000/01/testorg", "testrepo"])
    doc_err = json.loads(result.stdout)
    assert "Cannot" in doc_err["detail"]
