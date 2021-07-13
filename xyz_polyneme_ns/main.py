import os
from typing import Optional, Union
from pathlib import Path

from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import HTMLResponse, RedirectResponse
import rdflib

from xyz_polyneme_ns.idgen import ark_map

app = FastAPI()

TEST_BASE = "http://ns.polyneme.xyz/2021/04/marda-dd/test#"


def load_ttl(filename: Union[Path, str]) -> rdflib.Graph:
    g = rdflib.Graph()
    g.parse(str(filename), format="turtle")
    return g


TERMS = load_ttl(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hello_world.ttl",
    )
)


def render_html(g: rdflib.Graph) -> str:
    header = """<html>
  <style type="text/css">
    dt { font-weight: bold; text-decoration: underline dotted; }
  </style>
  <body>
    <dl>
"""
    footer = """
    </dl>
  </body>
</html>"""

    dl = ""
    _parsed_subjects = set()
    for subject in g.subjects():
        if subject in _parsed_subjects:
            continue
        _parsed_subjects.add(subject)
        term = subject.split(TEST_BASE)[-1]
        label = g.label(subject)
        comment = g.comment(subject)

        dt = f"""      <dt id="#{term}">{label}</dt>
      <dd>{comment}</dd>"""
        dl += dt

    return header + dl + footer


def sorted_media_types(accept: str) -> bool:
    # e.g. "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    alternatives = [a.split(";") for a in accept.split(",")]
    for a in alternatives:
        # provide default relative quality factor
        # https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html
        if len(a) == 1:
            a.append("q=1")
        # ignore accept-params other than the relative quality factor
        for i, element in enumerate(a):
            if "=" in element and not element.startswith("q"):
                a.pop(i)
    alternatives = sorted(
        [(type_, float(qexpr[2:])) for type_, qexpr in alternatives],
        key=lambda a: a[1],
        reverse=True,
    )
    return [a[0] for a in alternatives]


def response_for(g: rdflib.Graph, accept: str, ns_base: str):
    types_ = sorted_media_types(accept)
    for media_type in types_:
        if media_type == "text/html":
            return HTMLResponse(content=render_html(g), status_code=200)
        elif media_type == "application/ld+json":
            g.namespace_manager.bind("base", ns_base)
            try:
                return Response(
                    content=g.serialize(
                        encoding="utf-8",
                        format=media_type,
                        auto_compact=True,
                    ).decode("utf-8"),
                    media_type=media_type,
                )
            except rdflib.plugin.PluginException:
                continue
        else:
            try:
                return Response(
                    content=g.serialize(
                        base=ns_base, encoding="utf-8", format=media_type
                    ).decode("utf-8"),
                    media_type=media_type,
                )
            except rdflib.plugin.PluginException:
                continue
    else:
        return HTMLResponse(content=render_html(g), status_code=200)


@app.get("/2021/04/marda-dd/test")
async def root(accept: Optional[str] = Header(None)):
    return response_for(TERMS, accept, TEST_BASE)


@app.get("/ark:/57802/{rest_of_path:path}", response_class=RedirectResponse)
async def _ark(request: Request):
    return RedirectResponse(
        url=str(request.url).replace("ark:/", "ark:"), status_code=301
    )


@app.get("/ark:57802/{rest_of_path:path}")
async def ark(rest_of_path, request: Request, accept: Optional[str] = Header(None)):
    parts = rest_of_path.split("/")
    basename = parts[0]
    leaf_and_variants = parts[-1].split(".")
    leaf, variants = leaf_and_variants[0], leaf_and_variants[1:]
    subparts = (parts[1:-1] + [leaf]) if len(parts) > 1 else []

    ark_map_url = ark_map(naan="57802").get(f"ark:57802/{basename}")
    # TODO support ?info inflection via {who,what,when,where,how} columns in ark_map.csv
    #   See: https://n2t.net/e/n2t_apidoc.html#identifier-metadata
    if ark_map_url:
        return RedirectResponse(url=ark_map_url, status_code=303)
    else:
        return {
            "resolver": str(request.base_url),
            "nma": str(request.base_url).split("/")[-2],
            "naan": "57802",
            "basename": basename,
            "subparts": subparts,
            "variants": variants,
        }
