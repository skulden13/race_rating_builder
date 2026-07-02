"""Trail participant rating builder.

Currently the only implemented participant source is RaceResult, and the only
implemented rating provider is ITRA. The package is split so additional sources
and providers, such as UTMB Index, can be added without rewriting the shared
matching or output code.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
