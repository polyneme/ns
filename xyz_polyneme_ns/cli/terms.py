import json
from typing import Optional

import typer

from xyz_polyneme_ns.cli.util import req

from xyz_polyneme_ns.util import ACCEPT

app = typer.Typer()


@app.command()
def create(path: str, term: str, term_in: str):
    rv = req("POST", path, params={"term": term}, json=json.loads(term_in))
    typer.echo(rv.content)


@app.command()
def read(term_path: str, accept: Optional[str] = ACCEPT):
    rv = req("GET", term_path, headers={"Accept": accept})
    typer.echo(rv.content)


@app.command()
def update(path: str, term_in: str):
    rv = req("PATCH", path, json={"update": json.loads(term_in)})
    typer.echo(rv.content)
