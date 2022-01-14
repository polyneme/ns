from starlette.responses import Response

from xyz_polyneme_ns.main import response_for, load_graph_from_file


def test_no_extra_prefixes():
    rv: Response = response_for(
        g=load_graph_from_file(
            "https://raw.githubusercontent.com/polyneme/ns/main/hello_world.ttl",
            format_="turtle",
        ),
        accept="text/turtle",  # not the case for application/ld+json !
    )
    assert "brick" not in rv.body.decode()
