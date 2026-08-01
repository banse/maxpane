from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("maxpane")
except PackageNotFoundError:
    # Running straight from a source checkout with nothing installed -- there
    # is no distribution metadata to read.  This used to raise, and because
    # every widget module reaches ``maxpane_dashboard.__init__`` on import, a
    # bare ``python -m maxpane_dashboard`` in a fresh clone died on the import
    # line rather than on anything the user could act on.  A version string is
    # never worth taking the app down for: degrade to a marker that is honest
    # about being unknown and still parses as PEP 440.
    __version__ = "0+unknown"
