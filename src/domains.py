"""Vertical domain-pack registry (multi-domain plan §3).

A tenant's ``domain`` selects which pack — prompts, skills library, citation
sources, extraction schemas — the platform applies at request time. For now this
module only enumerates the *known* domains and their display labels; the packs
themselves (prompts/skills/sources) are layered on in later phases and will key
off these same identifiers.

Keeping the registry here — a plain dict, not an Enum on the DB model — is
deliberate: onboarding a new vertical should be an edit to this one file, not a
schema migration. See the model note on ``Tenant.domain``.
"""

from __future__ import annotations

# The domain every tenant gets unless they pick another. Behaves exactly like
# the platform did before domain packs existed (no vertical specialization).
DEFAULT_DOMAIN = "generic"

# key -> human-readable label. Add an entry here to register a new vertical.
DOMAINS: dict[str, str] = {
    "generic": "General",
    "legal": "Legal",
    "ca": "Chartered Accountancy / Tax",
}


def is_known_domain(domain: str) -> bool:
    """True if ``domain`` is a registered vertical."""
    return domain in DOMAINS


def normalize_domain(domain: str | None) -> str:
    """Coerce arbitrary input to a known domain key.

    Lower-cases and trims, then falls back to :data:`DEFAULT_DOMAIN` for
    anything unrecognized. Use this when reading a domain from an untrusted or
    historical source (e.g. a JWT claim) where you want a safe value rather than
    an error. For user-facing input prefer an explicit ``is_known_domain`` check
    so typos surface instead of silently becoming "generic".
    """
    if not domain:
        return DEFAULT_DOMAIN
    key = domain.strip().lower()
    return key if key in DOMAINS else DEFAULT_DOMAIN
