def test_version_exposed():
    # Expect the package to expose a semantic version string
    import scp

    assert isinstance(scp.__version__, str)
    assert scp.__version__.count(".") == 2

