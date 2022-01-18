from typing import Optional

import typer
from requests import request

from xyz_polyneme_ns.cli import namespaces, terms, skolems
from xyz_polyneme_ns.util import HOST, ACCEPT

app = typer.Typer()
app.add_typer(namespaces.app, name="ns", help="namespaces")
app.add_typer(terms.app, name="term")
app.add_typer(skolems.app, name="skolem")


@app.command()
def read(path: str, accept: Optional[str] = ACCEPT):
    """read full url path."""
    _path = path[1:] if path.startswith("/") else path
    url = f"{HOST}/{_path}"
    rv = request("GET", url, headers={"Accept": accept})
    typer.echo(rv.content)
