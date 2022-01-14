from toolz import merge
from typing import Optional

import json

import os

from requests import request
import typer

from xyz_polyneme_ns.models import ArkNaan, ArkShoulder
from xyz_polyneme_ns.util import HOST, NAAN, USER, PASS, ACCEPT

app = typer.Typer()


def req(method, path, **kwargs):
    url = f"{HOST}/ark:{NAAN}{path}"
    headers = merge({"Accept": ACCEPT}, kwargs.get("headers", {}))
    kwargs.pop("headers", None)
    return request(
        method,
        url,
        auth=(USER, PASS),
        headers=headers,
        **kwargs,
    )


@app.command()
def get(path: str, accept: Optional[str] = ACCEPT):
    _path = path[1:] if path.startswith("/") else path
    url = f"{HOST}/{_path}"
    rv = request("GET", url, headers={"Accept": accept})
    typer.echo(rv.content)


@app.command()
def get_namespace(path: str, accept: Optional[str] = ACCEPT):
    rv = req("GET", path, headers={"Accept": accept})
    typer.echo(rv.content)


@app.command()
def create_namespace(org: str, repo: str):
    rv = req("POST", org, params={"repo": repo}, json={})
    typer.echo(rv.content)


@app.command()
def update_namespace(path: str, update: str):
    rv = req("PATCH", path, json={"update": json.loads(update)})
    typer.echo(rv.content)


@app.command()
def get_term(path: str):
    rv = req("GET", path)
    typer.echo(rv.content)


@app.command()
def create_term(path: str, term: str, term_in: str):
    rv = req("POST", path, params={"term": term}, json=json.loads(term_in))
    typer.echo(rv.content)


@app.command()
def create_individual(shoulder: str, individual_in: str):
    rv = req("POST", f"/{shoulder}", json=json.loads(individual_in))
    typer.echo(rv.content)


@app.command()
def get_individual(assigned_base_name: str, accept: Optional[str] = ACCEPT):
    rv = req("GET", f"/{assigned_base_name}", headers={"Accept": accept})
    typer.echo(rv.content)


@app.command()
def update_individual(assigned_base_name: str, individual_in: str):
    rv = req(
        "PATCH", f"/{assigned_base_name}", json={"update": json.loads(individual_in)}
    )
    typer.echo(rv.content)


@app.command()
def hello(name: str):
    typer.echo(f"Hello {name}")


@app.command()
def goodbye(name: str, formal: bool = False):
    if formal:
        typer.echo(f"Goodbye Ms. {name}. Have a good day.")
    else:
        typer.echo(f"Bye {name}!")
