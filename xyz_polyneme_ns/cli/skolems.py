import json
from typing import Optional

import typer

from xyz_polyneme_ns.cli.util import req

from xyz_polyneme_ns.util import ACCEPT

app = typer.Typer()


@app.command()
def create(shoulder: str, skolem_in: str):
    rv = req("POST", f"/{shoulder}", json=json.loads(skolem_in))
    typer.echo(rv.content)


@app.command()
def read(assigned_base_name: str, accept: Optional[str] = ACCEPT):
    rv = req("GET", f"/{assigned_base_name}", headers={"Accept": accept})
    typer.echo(rv.content)


@app.command()
def update(assigned_base_name: str, skolem_in: str):
    rv = req("PATCH", f"/{assigned_base_name}", json={"update": json.loads(skolem_in)})
    typer.echo(rv.content)
