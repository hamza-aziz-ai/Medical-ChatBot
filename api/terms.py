import logging

logger = logging.getLogger(__name__)

# Known parsing artefacts in medical.csv that contain letters but are not medical terms.
QUARANTINED_TERMS = frozenset({"living"})


def is_valid_term(term):
    return (
        isinstance(term, str)
        and any(ch.isalpha() for ch in term)
        and term.strip().lower() not in QUARANTINED_TERMS
    )


def clean_terms(terms):
    kept = [t.strip() for t in terms if is_valid_term(t)]
    if len(kept) < len(terms):
        logger.debug("Dropped %d artefact term(s): %s", len(terms) - len(kept), [t for t in terms if not is_valid_term(t)])
    return kept
