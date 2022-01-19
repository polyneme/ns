import json
from typing import Optional

import typer

from xyz_polyneme_ns.cli.util import req

from xyz_polyneme_ns.util import ACCEPT

app = typer.Typer()


@app.command()
def create(
    ns_path: str, term: str, file: typer.FileText = typer.Option(..., "--file", "-f")
):
    rv = req("POST", ns_path, params={"term": term}, json=json.load(file))
    typer.echo(rv.content)


@app.command()
def read(term_path: str, accept: Optional[str] = ACCEPT):
    rv = req("GET", term_path, headers={"Accept": accept})
    typer.echo(rv.content)


@app.command()
def update(term_path: str, file: typer.FileText = typer.Option(..., "--file", "-f")):
    rv = req("PATCH", term_path, json={"update": json.load(file)})
    typer.echo(rv.content)
