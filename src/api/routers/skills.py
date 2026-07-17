"""Skills library endpoint (feature-implementation-plan §25).

Returns the pre-built, domain-scoped workflow templates a tenant can launch. The
set is determined by the tenant's ``domain`` (its vertical's skills plus the
always-on generic ones); no skill exposes another vertical's templates.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_viewer
from src.db.models import Tenant, User
from src.db.session import get_db
from src.domains import DEFAULT_DOMAIN
from src.skills import get_skills_for_domain

router = APIRouter(prefix="/skills", tags=["skills"])
logger = logging.getLogger(__name__)


class Skill(BaseModel):
    id: str
    domain: str
    name: str
    description: str
    feature: str
    preset: dict


class SkillsResponse(BaseModel):
    domain: str
    skills: list[Skill]


@router.get("/", response_model=SkillsResponse)
async def list_skills(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """List the skills available to the caller's tenant, scoped to its domain."""
    tenant = await db.get(Tenant, current_user.tenant_id)
    domain = getattr(tenant, "domain", None) or DEFAULT_DOMAIN
    skills = get_skills_for_domain(domain)
    return SkillsResponse(domain=domain, skills=[Skill(**s) for s in skills])
