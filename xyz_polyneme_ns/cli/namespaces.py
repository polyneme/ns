import json
from typing import Optional

import typer

from xyz_polyneme_ns.cli.util import req

from xyz_polyneme_ns.util import ACCEPT

app = typer.Typer()


@app.command()
def create(org: str, repo: str):
    rv = req("POST", org, params={"repo": repo}, json={})
    typer.echo(rv.content)


@app.command()
def read(ns_path: str, accept: Optional[str] = ACCEPT):
    rv = req("GET", ns_path, headers={"Accept": accept})
    typer.echo(rv.content)


@app.command()
def update(path: str, ns_in: str):
    rv = req("PATCH", path, json={"update": json.loads(ns_in)})
    typer.echo(rv.content)
