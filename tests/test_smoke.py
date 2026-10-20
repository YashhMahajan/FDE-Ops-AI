import fdeops


def test_package_imports_and_has_version() -> None:
    assert fdeops.__version__ == "2.1.0"
