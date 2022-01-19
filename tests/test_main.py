from starlette.responses import Response

from xyz_polyneme_ns.db import mongo_db
from xyz_polyneme_ns.main import (
    response_for,
    load_graph_from_file,
    ensure_initial_resources_on_boot,
)
from xyz_polyneme_ns.util import NAAN


def test_no_extra_prefixes():
    rv: Response = response_for(
        g=load_graph_from_file(
            "https://raw.githubusercontent.com/polyneme/ns/main/hello_world.ttl",
            format_="turtle",
        ),
        accept="text/turtle",  # not the case for application/ld+json !
    )
    assert "brick" not in rv.body.decode()


def test_no_clobbering_of_naan_shoulders_on_restart():
    mdb = mongo_db()
    fake_shoulder = "fkfkfkfk4"
    naan = int(NAAN)
    assert fake_shoulder not in mdb.naans.find_one({"_id": naan})["shoulders"]
    mdb.naans.update_one({"_id": naan}, {"$addToSet": {"shoulders": fake_shoulder}})

    ensure_initial_resources_on_boot()

    assert fake_shoulder in mdb.naans.find_one({"_id": naan})["shoulders"]
    mdb.naans.update_one({"_id": naan}, {"$pull": {"shoulders": fake_shoulder}})
