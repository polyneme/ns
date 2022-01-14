from xyz_polyneme_ns.models import get_shoulder


def test_get_shoulder():
    assert get_shoulder("fk1tt46") == "fk1"
    assert get_shoulder("fkttbb") is None
