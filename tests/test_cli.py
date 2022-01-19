import re

import json

from typing import List

import click.testing
from typer.testing import CliRunner

from xyz_polyneme_ns.cli.main import app
from xyz_polyneme_ns.db import mongo_db
from xyz_polyneme_ns.util import now, REPO_ROOT_DIR

TESTS_DIR = REPO_ROOT_DIR.joinpath("tests")
EMPTYDOC = TESTS_DIR.joinpath("emptydoc.json")


def cli_invoke(args: List[str]) -> click.testing.Result:
    return CliRunner().invoke(app, args)


def test_read_legacy_routes():
    result = cli_invoke(["read", "/2021/04/marda-dd/test", "--accept", "text/turtle"])
    assert result.stdout.startswith("@prefix")
    assert "vulgar" in result.stdout

    result = cli_invoke(
        ["read", "/ark:57802/2021/08/mardaphonons", "--accept", "text/turtle"]
    )
    assert result.stdout.startswith("@prefix")
    assert "skos:ConceptScheme" in result.stdout


def test_skolem_transient_redirect():
    result = cli_invoke(["skolem", "read", "fk1234", "--accept", "text/html"])
    # XXX redirects to http://example.org
    assert "<title>Example Domain</title>" in result.stdout


def test_crud_skolem():
    result = cli_invoke(
        ["skolem", "create", "fk1", "-f", TESTS_DIR.joinpath("skolem_create.json")]
    )
    assert result.exit_code == 0
    doc_c = json.loads(result.stdout)
    assert "fk1" in doc_c["@id"]

    assigned_base_name = re.search(r"ark:\d{5}/(?P<abn>\w+)", doc_c["@id"]).group("abn")
    result = cli_invoke(["skolem", "read", assigned_base_name])
    doc_r = json.loads(result.stdout)
    assert doc_r == doc_c

    result = cli_invoke(
        [
            "skolem",
            "update",
            assigned_base_name,
            "-f",
            TESTS_DIR.joinpath("skolem_update.json"),
        ]
    )
    doc_u = json.loads(result.stdout)
    assert doc_u != doc_c
    assert doc_c.get("rdfs:comment") is None
    assert doc_u.get("rdfs:comment") is not None

    mdb = mongo_db()
    mdb.arks.delete_one({"@id": doc_c["@id"]})


def _ns_create():
    dt = now()
    test_org = f"/{dt.year}/{dt.month:02}/testorg"
    test_repo = f"{test_org}/testrepo"
    result = cli_invoke(
        [
            "ns",
            "create",
            test_org,
            "testrepo",
            "-f",
            EMPTYDOC,
        ]
    )
    assert result.exit_code == 0
    doc_c = json.loads(result.stdout)
    assert test_repo in doc_c["@id"]
    assert doc_c["@type"] == "owl:Ontology"
    assert doc_c["dct:title"] == "testrepo"
    return doc_c, test_repo


def _ns_delete(id_):
    mdb = mongo_db()
    mdb.namespaces.delete_one({"@id": id_})


def test_crud_namespace():
    doc_c, test_repo = _ns_create()

    try:
        result = cli_invoke(["ns", "read", test_repo])
        doc_r = json.loads(result.stdout)
        assert doc_c == doc_r

        result = cli_invoke(
            [
                "ns",
                "update",
                test_repo,
                "-f",
                TESTS_DIR.joinpath("ns_update.json"),
            ]
        )
        doc_u = json.loads(result.stdout)
        assert doc_u != doc_c
        assert doc_c.get("rdfs:comment") is None
        assert doc_u.get("rdfs:comment") is not None
    finally:
        _ns_delete(doc_c["@id"])


def test_crud_term():
    ns_doc_c, test_repo = _ns_create()

    try:
        result = cli_invoke(
            [
                "term",
                "create",
                test_repo,
                "testterm",
                "-f",
                TESTS_DIR.joinpath("term_create.json"),
            ]
        )
        term_id = f"{test_repo}/testterm"
        doc_c = json.loads(result.stdout)
        assert doc_c["@id"].endswith(term_id)
        assert doc_c["rdfs:label"] == "Test Term"

        result = cli_invoke(["term", "read", term_id])
        doc_r = json.loads(result.stdout)
        assert doc_c == doc_r

        result = cli_invoke(
            [
                "term",
                "update",
                term_id,
                "-f",
                TESTS_DIR.joinpath("term_update.json"),
            ]
        )
        doc_u = json.loads(result.stdout)
        assert doc_u != doc_c
        assert doc_c.get("rdfs:label") == "Test Term"
        assert doc_u.get("rdfs:label") == "Testy Term"

        mdb = mongo_db()
        mdb.terms.delete_one({"@id": doc_c["@id"]})
    finally:
        _ns_delete(ns_doc_c["@id"])


def test_cannot_create_past_namespace():
    result = cli_invoke(
        [
            "ns",
            "create",
            "/1000/01/testorg",
            "testrepo",
            "-f",
            EMPTYDOC,
        ]
    )
    doc_err = json.loads(result.stdout)
    assert "Cannot" in doc_err["detail"]


def test_ark_explain():
    result = cli_invoke(
        ["read", "/explain/ark:57802/fk1234/subpart1/subpart2/leaf.variant1.variant2"]
    )
    doc = {
        "resolver": "http://localhost:8000/",
        "nma": "localhost:8000",
        "naan": "57802",
        "basename": "fk1234",
        "subparts": ["subpart1", "subpart2", "leaf"],
        "variants": ["variant1", "variant2"],
    }
    doc_r = json.loads(result.stdout)
    assert doc == doc_r


def test_update_missing_dollar_op():
    ns_doc_c, test_repo = _ns_create()
    try:
        result = cli_invoke(
            "ns update /2022/01/dwi/main -f tests/ns_update_noset.json".split()
        )
        doc_err = json.loads(result.stdout)
        assert "update only works with $ operators" in doc_err["detail"]
    finally:
        _ns_delete(ns_doc_c["@id"])
