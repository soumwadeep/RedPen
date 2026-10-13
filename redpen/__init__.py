"""RedPen -- an offline contract reviewer for freelancers.

Architecture in one paragraph: the document is parsed and split into clauses
(ingest), a deterministic open-source rule library decides what is dangerous and
cites the exact words that fired (rules.catalog + engine), and a local open-weight
model is used only to turn that into language the user can send (llm + narrate).
Nothing in the pipeline can reach the internet: the only network call is to a
loopback port running the model on the same laptop.
"""

from .engine import Analysis, Finding, analyse
from .ingest import Contract, DocumentTooShort, load, load_text

__version__ = "0.1.0"
__all__ = [
    "Analysis", "Finding", "Contract", "DocumentTooShort",
    "analyse", "load", "load_text", "__version__",
]
