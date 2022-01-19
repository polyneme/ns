import json
from typing import Optional

import typer

from xyz_polyneme_ns.cli.util import req

from xyz_polyneme_ns.util import ACCEPT

app = typer.Typer()


@app.command()
def create(shoulder: str, file: typer.FileText = typer.Option(..., "--file", "-f")):
    rv = req("POST", f"/{shoulder}", json=json.load(file))
    typer.echo(rv.content)


@app.command()
def read(assigned_base_name: str, accept: Optional[str] = ACCEPT):
    rv = req("GET", f"/{assigned_base_name}", headers={"Accept": accept})
    typer.echo(rv.content)


@app.command()
def update(
    assigned_base_name: str, file: typer.FileText = typer.Option(..., "--file", "-f")
):
    rv = req("PATCH", f"/{assigned_base_name}", json={"update": json.load(file)})
    typer.echo(rv.content)
