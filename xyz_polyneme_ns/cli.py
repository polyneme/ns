import json

import os

from requests import request
import typer

app = typer.Typer()

HOST = os.environ.get("API_HOST")
NAAN = os.environ.get("API_AGENT_NAAN")
USER = os.environ.get("API_AGENT_USERNAME")
PASS = os.environ.get("API_AGENT_PASSWORD")


def req(method, path, **kwargs):
    url = f"{HOST}/ark:{NAAN}{path}"
    return request(
        method,
        url,
        auth=(USER, PASS),
        headers={
            "Accept": "application/ld+json,text/turtle;q=0.9,application/rdf+xml;q=0.8,*/*;q=0.5"
        },
        **kwargs,
    )


@app.command()
def get_namespace(path: str):
    rv = req("GET", path)
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
def hello(name: str):
    typer.echo(f"Hello {name}")


@app.command()
def goodbye(name: str, formal: bool = False):
    if formal:
        typer.echo(f"Goodbye Ms. {name}. Have a good day.")
    else:
        typer.echo(f"Bye {name}!")
