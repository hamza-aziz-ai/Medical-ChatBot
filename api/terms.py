# Known parsing artefacts in medical.csv that contain letters but are not medical terms.
QUARANTINED_TERMS = frozenset({"living"})


def is_valid_term(term):
    return (
        isinstance(term, str)
        and any(ch.isalpha() for ch in term)
        and term.strip().lower() not in QUARANTINED_TERMS
    )


def clean_terms(terms):
    return [t.strip() for t in terms if is_valid_term(t)]
