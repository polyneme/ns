import json
from typing import Optional

import typer

from xyz_polyneme_ns.cli.util import req

from xyz_polyneme_ns.util import ACCEPT

app = typer.Typer()


@app.command()
def create(
    org: str, repo: str, file: typer.FileText = typer.Option(..., "--file", "-f")
):
    rv = req("POST", org, params={"repo": repo}, json=json.load(file))
    typer.echo(rv.content)


@app.command()
def read(ns_path: str, accept: Optional[str] = ACCEPT):
    rv = req("GET", ns_path, headers={"Accept": accept})
    typer.echo(rv.content)


@app.command()
def update(ns_path: str, file: typer.FileText = typer.Option(..., "--file", "-f")):
    rv = req("PATCH", ns_path, json={"update": json.load(file)})
    typer.echo(rv.content)


# TODO `def list` to list existing namespaces that I can_admin or can_edit.
