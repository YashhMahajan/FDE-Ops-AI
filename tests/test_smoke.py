import fdeops


def test_package_imports_and_has_version() -> None:
    assert fdeops.__version__ == "0.1.0"
