import re

import json

from typing import List

import click.testing
from typer.testing import CliRunner

from xyz_polyneme_ns import cli
from xyz_polyneme_ns.db import mongo_db


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


def test_create_get_and_update_individual():
    result = cli_invoke(["create-individual", "fk1", '{"rdfs:label": "donny"}'])
    assert result.exit_code == 0
    indiv_doc_created = json.loads(result.stdout)
    assert "fk1" in indiv_doc_created["@id"]

    assigned_base_name = re.search(
        r"ark:\d{5}/(?P<abn>\w+)", indiv_doc_created["@id"]
    ).group("abn")
    result = cli_invoke(["get-individual", assigned_base_name])
    indiv_doc_unchanged = json.loads(result.stdout)
    assert indiv_doc_unchanged == indiv_doc_created

    result = cli_invoke(
        [
            "update-individual",
            assigned_base_name,
            '{"$set": {"rdfs:comment": "definitely a person"}}',
        ]
    )
    indiv_doc_updated = json.loads(result.stdout)
    assert indiv_doc_updated != indiv_doc_created
    assert indiv_doc_created.get("rdfs:comment") is None
    assert indiv_doc_updated.get("rdfs:comment") is not None

    mdb = mongo_db()
    mdb.arks.delete_one({"@id": indiv_doc_updated["@id"]})
