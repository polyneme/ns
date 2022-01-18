from requests import request
from toolz import merge

from xyz_polyneme_ns.util import HOST, NAAN, USER, PASS, ACCEPT


def req(method, path, **kwargs):
    url = f"{HOST}/ark:{NAAN}{path}"
    headers = merge({"Accept": ACCEPT}, kwargs.get("headers", {}))
    kwargs.pop("headers", None)
    return request(
        method,
        url,
        auth=(USER, PASS),
        headers=headers,
        **kwargs,
    )
