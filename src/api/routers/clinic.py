"""Clinic vertical endpoints — Phase 1 (feature-implementation-plan §33).

Roles: reception, doctor, management (=org_admin). Every query is tenant-scoped
(a clinic == a tenant). Reception's reach is bounded by its assignment (a specific
doctor, or open-for-all); a doctor sees and acts on ONLY their own queue.
Real-time (SSE) and AI insights arrive in later phases.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import (require_admin, require_clinic_staff, require_clinician, require_doctor,
                          require_reception)
from src.api.deps import resolve_task_llm
from src.clinic.insights import generate_insights
from src.db.models import (ClinicNotification, DoctorProfile, DoctorStatus, FollowUp, Patient,
                           PatientShare, QueueEntry, QueueStatus, ReceptionAssignment, User,
                           UserRole, Visit)
from src.db.session import get_db
from src.providers.factory import LLMTask
from src.storage.cache import get_cache

router = APIRouter(prefix="/clinic", tags=["clinic"])
logger = logging.getLogger(__name__)


# ── Live events (SSE, §33 P2) ─────────────────────────────────────────────────

def _channel(tenant_id: str) -> str:
    return f"clinic:events:{tenant_id}"


async def _publish(tenant_id: str, event: dict) -> None:
    await get_cache().publish_event(_channel(tenant_id), event)


def _event_for_user(event: dict, user: User) -> bool:
    """Whether a broadcast event should reach this connected user."""
    if event.get("recipient_user_id") == user.id:
        return True
    aud = event.get("audience")
    if aud == "clinic":
        return True
    if aud == "reception":
        return user.role in (UserRole.reception, UserRole.org_admin)
    if aud == "doctor":
        return user.role == UserRole.doctor and event.get("doctor_user_id") == user.id
    return False


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateDoctorRequest(BaseModel):
    user_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=255)
    specialty: str | None = Field(default=None, max_length=255)
    room: str | None = Field(default=None, max_length=50)


class DoctorOut(BaseModel):
    user_id: str
    display_name: str
    specialty: str | None
    room: str | None
    status: str
    waiting_count: int


class StatusRequest(BaseModel):
    status: DoctorStatus


class CreatePatientRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    dob: str | None = Field(default=None, max_length=20)
    details: dict | None = None


class PatientOut(BaseModel):
    id: str
    name: str
    phone: str | None
    dob: str | None
    details: dict | None
    created_at: str


class EnqueueRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    doctor_user_id: str = Field(min_length=1)
    priority: int = Field(default=0, ge=0, le=10)


class QueueEntryOut(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    doctor_user_id: str
    status: str
    priority: int
    created_at: str
    called_at: str | None
    done_at: str | None


class UpdateQueueRequest(BaseModel):
    status: QueueStatus


class CreateFollowUpRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    scheduled_at: datetime
    reason: str | None = Field(default=None, max_length=2000)


class FollowUpOut(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    doctor_user_id: str
    scheduled_at: str
    reason: str | None


class AssignmentRequest(BaseModel):
    doctor_user_id: str | None = None   # None = open-for-all


class AssignmentOut(BaseModel):
    reception_user_id: str
    reception_email: str
    doctor_user_id: str | None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_doctor_user(db: AsyncSession, tenant_id: str, doctor_user_id: str) -> User:
    doc = (await db.execute(
        select(User).where(User.id == doctor_user_id, User.tenant_id == tenant_id,
                           User.role == UserRole.doctor)
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, detail="Doctor not found in this clinic")
    return doc


async def _reception_scope(db: AsyncSession, user: User) -> str | None:
    """The doctor a request is restricted to, or None for no restriction.

    Management (org_admin) is never restricted. A receptionist is restricted to
    their assigned doctor; if unassigned or assigned open-for-all, None.
    """
    if user.role == UserRole.org_admin:
        return None
    row = (await db.execute(
        select(ReceptionAssignment).where(
            ReceptionAssignment.tenant_id == user.tenant_id,
            ReceptionAssignment.reception_user_id == user.id,
        )
    )).scalar_one_or_none()
    return row.doctor_user_id if row else None


async def _waiting_counts(db: AsyncSession, tenant_id: str) -> dict[str, int]:
    rows = (await db.execute(
        select(QueueEntry.doctor_user_id, func.count(QueueEntry.id))
        .where(QueueEntry.tenant_id == tenant_id, QueueEntry.status == QueueStatus.waiting)
        .group_by(QueueEntry.doctor_user_id)
    )).all()
    return {d: n for d, n in rows}


# ── Doctors ────────────────────────────────────────────────────────────────

@router.post("/doctors", response_model=DoctorOut, status_code=201)
async def create_doctor(
    body: CreateDoctorRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Management: turn a clinic user into a doctor (sets role=doctor + a profile)."""
    user = (await db.execute(
        select(User).where(User.id == body.user_id, User.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, detail="User not found in this clinic")
    existing = (await db.execute(
        select(DoctorProfile).where(DoctorProfile.user_id == user.id)
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, detail="This user is already a doctor")
    user.role = UserRole.doctor
    profile = DoctorProfile(
        tenant_id=current_user.tenant_id, user_id=user.id, display_name=body.display_name,
        specialty=body.specialty, room=body.room, status=DoctorStatus.available,
    )
    db.add(profile)
    await db.commit()
    return DoctorOut(user_id=user.id, display_name=profile.display_name, specialty=profile.specialty,
                     room=profile.room, status=profile.status.value, waiting_count=0)


@router.get("/doctors", response_model=list[DoctorOut])
async def list_doctors(
    current_user: User = Depends(require_clinic_staff),
    db: AsyncSession = Depends(get_db),
):
    profiles = (await db.execute(
        select(DoctorProfile).where(DoctorProfile.tenant_id == current_user.tenant_id)
        .order_by(DoctorProfile.display_name)
    )).scalars().all()
    counts = await _waiting_counts(db, current_user.tenant_id)
    return [
        DoctorOut(user_id=p.user_id, display_name=p.display_name, specialty=p.specialty,
                  room=p.room, status=p.status.value, waiting_count=counts.get(p.user_id, 0))
        for p in profiles
    ]


@router.patch("/me/status", response_model=DoctorOut)
async def set_my_status(
    body: StatusRequest,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Doctor toggles their availability. Auto-creates a profile if missing."""
    profile = (await db.execute(
        select(DoctorProfile).where(DoctorProfile.user_id == current_user.id)
    )).scalar_one_or_none()
    if profile is None:
        profile = DoctorProfile(tenant_id=current_user.tenant_id, user_id=current_user.id,
                                display_name=current_user.email, status=body.status)
        db.add(profile)
    else:
        profile.status = body.status
    await db.commit()
    await _publish(current_user.tenant_id, {
        "type": "presence", "audience": "clinic",
        "doctor_user_id": current_user.id, "status": profile.status.value,
    })
    counts = await _waiting_counts(db, current_user.tenant_id)
    return DoctorOut(user_id=current_user.id, display_name=profile.display_name,
                     specialty=profile.specialty, room=profile.room,
                     status=profile.status.value, waiting_count=counts.get(current_user.id, 0))


# ── Patients ──────────────────────────────────────────────────────────────

@router.post("/patients", response_model=PatientOut, status_code=201)
async def create_patient(
    body: CreatePatientRequest,
    current_user: User = Depends(require_clinic_staff),
    db: AsyncSession = Depends(get_db),
):
    patient = Patient(
        tenant_id=current_user.tenant_id, name=body.name, phone=body.phone, dob=body.dob,
        details=body.details, created_by=current_user.id,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return _patient_out(patient)


@router.get("/patients", response_model=list[PatientOut])
async def list_patients(
    current_user: User = Depends(require_reception),   # reception + management
    db: AsyncSession = Depends(get_db),
    search: str = "",
    skip: int = 0,
    limit: int = 100,
):
    q = select(Patient).where(Patient.tenant_id == current_user.tenant_id)
    if search.strip():
        q = q.where(Patient.name.ilike(f"%{search.strip()}%"))
    q = q.order_by(Patient.created_at.desc()).offset(max(0, skip)).limit(min(max(1, limit), 200))
    return [_patient_out(p) for p in (await db.execute(q)).scalars().all()]


def _patient_out(p: Patient) -> PatientOut:
    return PatientOut(id=p.id, name=p.name, phone=p.phone, dob=p.dob, details=p.details,
                      created_at=p.created_at.isoformat())


# ── Queue ─────────────────────────────────────────────────────────────────

@router.post("/queue", response_model=QueueEntryOut, status_code=201)
async def enqueue(
    body: EnqueueRequest,
    current_user: User = Depends(require_reception),
    db: AsyncSession = Depends(get_db),
):
    scope = await _reception_scope(db, current_user)
    if scope is not None and body.doctor_user_id != scope:
        raise HTTPException(403, detail="You are assigned to a different doctor.")
    doctor = await _get_doctor_user(db, current_user.tenant_id, body.doctor_user_id)
    patient = (await db.execute(
        select(Patient).where(Patient.id == body.patient_id, Patient.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if patient is None:
        raise HTTPException(404, detail="Patient not found in this clinic")
    entry = QueueEntry(
        tenant_id=current_user.tenant_id, patient_id=patient.id, doctor_user_id=doctor.id,
        priority=body.priority, status=QueueStatus.waiting, created_by=current_user.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    await _publish(current_user.tenant_id, {
        "type": "queue_changed", "audience": "clinic", "doctor_user_id": doctor.id,
    })
    return _queue_out(entry, patient.name)


@router.get("/queue", response_model=list[QueueEntryOut])
async def view_queue(
    current_user: User = Depends(require_reception),
    db: AsyncSession = Depends(get_db),
    doctor_user_id: str = "",
    status: QueueStatus | None = None,
):
    scope = await _reception_scope(db, current_user)
    q = select(QueueEntry, Patient.name).join(Patient, QueueEntry.patient_id == Patient.id).where(
        QueueEntry.tenant_id == current_user.tenant_id
    )
    if scope is not None:
        q = q.where(QueueEntry.doctor_user_id == scope)     # reception bound to one doctor
    elif doctor_user_id:
        q = q.where(QueueEntry.doctor_user_id == doctor_user_id)
    if status is not None:
        q = q.where(QueueEntry.status == status)
    q = q.order_by(QueueEntry.priority.desc(), QueueEntry.created_at)
    return [_queue_out(e, name) for e, name in (await db.execute(q)).all()]


@router.get("/me/queue", response_model=list[QueueEntryOut])
async def my_queue(
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
    include_done: bool = False,
):
    q = select(QueueEntry, Patient.name).join(Patient, QueueEntry.patient_id == Patient.id).where(
        QueueEntry.tenant_id == current_user.tenant_id,
        QueueEntry.doctor_user_id == current_user.id,
    )
    if not include_done:
        q = q.where(QueueEntry.status.in_([QueueStatus.waiting, QueueStatus.in_progress]))
    q = q.order_by(QueueEntry.priority.desc(), QueueEntry.created_at)
    return [_queue_out(e, name) for e, name in (await db.execute(q)).all()]


@router.patch("/queue/{entry_id}", response_model=QueueEntryOut)
async def update_queue_entry(
    entry_id: str,
    body: UpdateQueueRequest,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Doctor advances one of THEIR OWN queue entries (call/in-progress/done/cancel)."""
    entry = (await db.execute(
        select(QueueEntry).where(
            QueueEntry.id == entry_id, QueueEntry.tenant_id == current_user.tenant_id,
            QueueEntry.doctor_user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, detail="Queue entry not found")
    entry.status = body.status
    now = datetime.now(timezone.utc)
    if body.status == QueueStatus.in_progress and entry.called_at is None:
        entry.called_at = now
    if body.status == QueueStatus.done:
        entry.done_at = now
    await db.commit()
    await db.refresh(entry)
    await _publish(current_user.tenant_id, {
        "type": "queue_changed", "audience": "clinic", "doctor_user_id": entry.doctor_user_id,
    })
    patient = await db.get(Patient, entry.patient_id)
    return _queue_out(entry, patient.name if patient else "")


def _queue_out(e: QueueEntry, patient_name: str) -> QueueEntryOut:
    return QueueEntryOut(
        id=e.id, patient_id=e.patient_id, patient_name=patient_name, doctor_user_id=e.doctor_user_id,
        status=e.status.value, priority=e.priority, created_at=e.created_at.isoformat(),
        called_at=e.called_at.isoformat() if e.called_at else None,
        done_at=e.done_at.isoformat() if e.done_at else None,
    )


# ── Follow-ups ────────────────────────────────────────────────────────────

@router.post("/follow-ups", response_model=FollowUpOut, status_code=201)
async def create_follow_up(
    body: CreateFollowUpRequest,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    patient = (await db.execute(
        select(Patient).where(Patient.id == body.patient_id, Patient.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if patient is None:
        raise HTTPException(404, detail="Patient not found in this clinic")
    fu = FollowUp(
        tenant_id=current_user.tenant_id, patient_id=patient.id, doctor_user_id=current_user.id,
        scheduled_at=body.scheduled_at, reason=body.reason, created_by=current_user.id,
    )
    db.add(fu)
    await db.commit()
    await db.refresh(fu)
    return FollowUpOut(id=fu.id, patient_id=fu.patient_id, patient_name=patient.name,
                       doctor_user_id=fu.doctor_user_id, scheduled_at=fu.scheduled_at.isoformat(),
                       reason=fu.reason)


@router.get("/follow-ups", response_model=list[FollowUpOut])
async def list_follow_ups(
    current_user: User = Depends(require_clinic_staff),
    db: AsyncSession = Depends(get_db),
    upcoming_only: bool = True,
):
    q = select(FollowUp, Patient.name).join(Patient, FollowUp.patient_id == Patient.id).where(
        FollowUp.tenant_id == current_user.tenant_id
    )
    # A doctor sees only their own follow-ups; reception/management see the clinic's.
    if current_user.role == UserRole.doctor:
        q = q.where(FollowUp.doctor_user_id == current_user.id)
    if upcoming_only:
        q = q.where(FollowUp.scheduled_at >= datetime.now(timezone.utc))
    q = q.order_by(FollowUp.scheduled_at)
    return [
        FollowUpOut(id=f.id, patient_id=f.patient_id, patient_name=name,
                    doctor_user_id=f.doctor_user_id, scheduled_at=f.scheduled_at.isoformat(),
                    reason=f.reason)
        for f, name in (await db.execute(q)).all()
    ]


# ── Reception assignments (management) ────────────────────────────────────

@router.get("/assignments", response_model=list[AssignmentOut])
async def list_assignments(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(ReceptionAssignment, User.email)
        .join(User, ReceptionAssignment.reception_user_id == User.id)
        .where(ReceptionAssignment.tenant_id == current_user.tenant_id)
    )).all()
    return [
        AssignmentOut(reception_user_id=a.reception_user_id, reception_email=email,
                      doctor_user_id=a.doctor_user_id)
        for a, email in rows
    ]


@router.put("/assignments/{reception_user_id}", response_model=AssignmentOut)
async def set_assignment(
    reception_user_id: str,
    body: AssignmentRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Assign a receptionist to a doctor (or None = open-for-all)."""
    reception = (await db.execute(
        select(User).where(User.id == reception_user_id, User.tenant_id == current_user.tenant_id,
                           User.role == UserRole.reception)
    )).scalar_one_or_none()
    if reception is None:
        raise HTTPException(404, detail="Receptionist not found in this clinic")
    if body.doctor_user_id is not None:
        await _get_doctor_user(db, current_user.tenant_id, body.doctor_user_id)
    row = (await db.execute(
        select(ReceptionAssignment).where(
            ReceptionAssignment.tenant_id == current_user.tenant_id,
            ReceptionAssignment.reception_user_id == reception_user_id,
        )
    )).scalar_one_or_none()
    if row is None:
        row = ReceptionAssignment(tenant_id=current_user.tenant_id,
                                  reception_user_id=reception_user_id, doctor_user_id=body.doctor_user_id)
        db.add(row)
    else:
        row.doctor_user_id = body.doctor_user_id
    await db.commit()
    return AssignmentOut(reception_user_id=reception_user_id, reception_email=reception.email,
                         doctor_user_id=body.doctor_user_id)


# ── Real-time: send-patient-in, notifications, SSE (§33 P2) ────────────────

class SendPatientInRequest(BaseModel):
    message: str | None = Field(default=None, max_length=500)
    patient_id: str | None = None


class NotificationOut(BaseModel):
    id: str
    type: str
    payload: dict | None
    read: bool
    created_at: str


async def _relevant_receptions(db: AsyncSession, tenant_id: str, doctor_user_id: str) -> list[User]:
    """Receptionists who manage this doctor: those assigned to them, plus any
    open-for-all (no assignment row, or a null assignment)."""
    receptions = (await db.execute(
        select(User).where(User.tenant_id == tenant_id, User.role == UserRole.reception,
                           User.is_active.is_(True))
    )).scalars().all()
    assigns = {a.reception_user_id: a.doctor_user_id for a in (await db.execute(
        select(ReceptionAssignment).where(ReceptionAssignment.tenant_id == tenant_id)
    )).scalars().all()}
    return [r for r in receptions if assigns.get(r.id) in (None, doctor_user_id)]


@router.post("/send-patient-in")
async def send_patient_in(
    body: SendPatientInRequest,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Doctor signals reception to send the next patient in — persists a
    notification for each relevant receptionist and broadcasts it live."""
    receptions = await _relevant_receptions(db, current_user.tenant_id, current_user.id)
    payload = {
        "doctor_user_id": current_user.id,
        "message": body.message or "Please send in the next patient.",
        "patient_id": body.patient_id,
    }
    for r in receptions:
        db.add(ClinicNotification(tenant_id=current_user.tenant_id, recipient_user_id=r.id,
                                  type="patient_in", payload=payload))
    await db.commit()
    await _publish(current_user.tenant_id, {"type": "patient_in", "audience": "reception", **payload})
    return {"notified": len(receptions)}


@router.get("/notifications", response_model=list[NotificationOut])
async def my_notifications(
    current_user: User = Depends(require_clinic_staff),
    db: AsyncSession = Depends(get_db),
    unread_only: bool = True,
    limit: int = 50,
):
    q = select(ClinicNotification).where(
        ClinicNotification.tenant_id == current_user.tenant_id,
        ClinicNotification.recipient_user_id == current_user.id,
    )
    if unread_only:
        q = q.where(ClinicNotification.read.is_(False))
    q = q.order_by(ClinicNotification.created_at.desc()).limit(min(max(1, limit), 200))
    return [
        NotificationOut(id=n.id, type=n.type, payload=n.payload, read=n.read,
                        created_at=n.created_at.isoformat())
        for n in (await db.execute(q)).scalars().all()
    ]


@router.post("/notifications/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(require_clinic_staff),
    db: AsyncSession = Depends(get_db),
):
    n = (await db.execute(
        select(ClinicNotification).where(
            ClinicNotification.id == notification_id,
            ClinicNotification.tenant_id == current_user.tenant_id,
            ClinicNotification.recipient_user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if n is None:
        raise HTTPException(404, detail="Notification not found")
    n.read = True
    await db.commit()


@router.get("/events")
async def clinic_events(
    current_user: User = Depends(require_clinic_staff),
    db: AsyncSession = Depends(get_db),
):
    """Server-Sent Events stream of live clinic events (presence, queue changes,
    'patient in') relevant to the caller. One Redis subscription per connection."""
    cache = get_cache()
    channel = _channel(current_user.tenant_id)

    async def gen():
        yield ": connected\n\n"
        try:
            async for event in cache.subscribe(channel):
                if _event_for_user(event, current_user):
                    yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:  # client disconnected
            raise

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive",
    })


# ── Visits + AI insights (§33 P3) ─────────────────────────────────────────────

class CreateVisitRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    notes: str = Field(min_length=1, max_length=20_000)


class VisitOut(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    doctor_user_id: str
    notes: str | None
    ai_insights: dict | None
    created_at: str


def _visit_out(v: Visit, patient_name: str) -> VisitOut:
    return VisitOut(id=v.id, patient_id=v.patient_id, patient_name=patient_name,
                    doctor_user_id=v.doctor_user_id, notes=v.notes, ai_insights=v.ai_insights,
                    created_at=v.created_at.isoformat())


@router.post("/visits", response_model=VisitOut, status_code=201)
async def create_visit(
    body: CreateVisitRequest,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Doctor records a visit (typed notes) → AI insights are generated and stored.
    Notes are encrypted at rest; insights never fail the save (best-effort)."""
    patient = (await db.execute(
        select(Patient).where(Patient.id == body.patient_id, Patient.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if patient is None:
        raise HTTPException(404, detail="Patient not found in this clinic")
    llm = await resolve_task_llm(db, current_user.tenant_id, LLMTask.EXTRACT)
    insights = await generate_insights(llm, body.notes)
    visit = Visit(tenant_id=current_user.tenant_id, patient_id=patient.id,
                  doctor_user_id=current_user.id, notes=body.notes, ai_insights=insights)
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    return _visit_out(visit, patient.name)


@router.get("/visits", response_model=list[VisitOut])
async def list_visits(
    current_user: User = Depends(require_clinician),   # doctor + management only (not reception)
    db: AsyncSession = Depends(get_db),
    patient_id: str = "",
    limit: int = 50,
):
    q = select(Visit, Patient.name).join(Patient, Visit.patient_id == Patient.id).where(
        Visit.tenant_id == current_user.tenant_id
    )
    if current_user.role == UserRole.doctor:
        # a doctor sees visits they authored OR for a patient shared with them (P4)
        shared = select(PatientShare.patient_id).where(
            PatientShare.tenant_id == current_user.tenant_id,
            PatientShare.doctor_user_id == current_user.id,
        )
        q = q.where(or_(Visit.doctor_user_id == current_user.id, Visit.patient_id.in_(shared)))
    if patient_id:
        q = q.where(Visit.patient_id == patient_id)
    q = q.order_by(Visit.created_at.desc()).limit(min(max(1, limit), 200))
    return [_visit_out(v, name) for v, name in (await db.execute(q)).all()]


@router.get("/analytics")
async def analytics(
    current_user: User = Depends(require_admin),   # management only
    db: AsyncSession = Depends(get_db),
):
    """Management dashboard: clinic totals, per-doctor load, and aggregated AI
    insights (summaries + red flags from recent visits — no raw notes)."""
    tid = current_user.tenant_id
    patients_count = (await db.execute(select(func.count(Patient.id)).where(Patient.tenant_id == tid))).scalar() or 0
    visits_count = (await db.execute(select(func.count(Visit.id)).where(Visit.tenant_id == tid))).scalar() or 0
    waiting = await _waiting_counts(db, tid)
    done_counts = {
        d: n for d, n in (await db.execute(
            select(QueueEntry.doctor_user_id, func.count(QueueEntry.id))
            .where(QueueEntry.tenant_id == tid, QueueEntry.status == QueueStatus.done)
            .group_by(QueueEntry.doctor_user_id)
        )).all()
    }
    visit_counts = {
        d: n for d, n in (await db.execute(
            select(Visit.doctor_user_id, func.count(Visit.id))
            .where(Visit.tenant_id == tid).group_by(Visit.doctor_user_id)
        )).all()
    }
    profiles = (await db.execute(
        select(DoctorProfile).where(DoctorProfile.tenant_id == tid)
    )).scalars().all()
    per_doctor = [
        {"doctor_user_id": p.user_id, "display_name": p.display_name, "status": p.status.value,
         "waiting": waiting.get(p.user_id, 0), "done": done_counts.get(p.user_id, 0),
         "visits": visit_counts.get(p.user_id, 0)}
        for p in profiles
    ]
    upcoming = (await db.execute(
        select(func.count(FollowUp.id)).where(
            FollowUp.tenant_id == tid, FollowUp.scheduled_at >= datetime.now(timezone.utc))
    )).scalar() or 0
    # aggregated AI insights from recent visits (summaries + red flags only)
    recent = (await db.execute(
        select(Visit, Patient.name).join(Patient, Visit.patient_id == Patient.id)
        .where(Visit.tenant_id == tid).order_by(Visit.created_at.desc()).limit(20)
    )).all()
    red_flag_total = sum(len((v.ai_insights or {}).get("red_flags", [])) for v, _ in recent)
    recent_insights = [
        {"patient_name": name, "doctor_user_id": v.doctor_user_id,
         "summary": (v.ai_insights or {}).get("summary", ""),
         "red_flags": (v.ai_insights or {}).get("red_flags", [])}
        for v, name in recent
    ]
    return {
        "patients": patients_count,
        "doctors": len(profiles),
        "visits": visits_count,
        "waiting_total": sum(waiting.values()),
        "upcoming_follow_ups": upcoming,
        "red_flag_total": red_flag_total,
        "per_doctor": per_doctor,
        "recent_insights": recent_insights,
    }


# ── Team sharing + hand-off (§33 P4) ──────────────────────────────────────────

class ShareRequest(BaseModel):
    doctor_user_id: str = Field(min_length=1)


class ShareOut(BaseModel):
    patient_id: str
    doctor_user_id: str
    doctor_email: str


class HandoffRequest(BaseModel):
    doctor_user_id: str = Field(min_length=1)


@router.post("/patients/{patient_id}/share", response_model=ShareOut, status_code=201)
async def share_patient(
    patient_id: str,
    body: ShareRequest,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Share a patient with a teammate doctor (they gain read access to visits)."""
    patient = (await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if patient is None:
        raise HTTPException(404, detail="Patient not found in this clinic")
    if body.doctor_user_id == current_user.id:
        raise HTTPException(400, detail="Patient is already yours.")
    target = await _get_doctor_user(db, current_user.tenant_id, body.doctor_user_id)
    db.add(PatientShare(tenant_id=current_user.tenant_id, patient_id=patient.id,
                        doctor_user_id=target.id, shared_by=current_user.id))
    db.add(ClinicNotification(
        tenant_id=current_user.tenant_id, recipient_user_id=target.id, type="patient_shared",
        payload={"patient_id": patient.id, "patient_name": patient.name, "shared_by": current_user.id},
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, detail="Patient already shared with this doctor.")
    await _publish(current_user.tenant_id, {
        "type": "patient_shared", "recipient_user_id": target.id,
        "patient_id": patient.id, "patient_name": patient.name,
    })
    return ShareOut(patient_id=patient.id, doctor_user_id=target.id, doctor_email=target.email)


@router.get("/patients/{patient_id}/shares", response_model=list[ShareOut])
async def list_shares(
    patient_id: str,
    current_user: User = Depends(require_clinician),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(PatientShare, User.email).join(User, PatientShare.doctor_user_id == User.id)
        .where(PatientShare.tenant_id == current_user.tenant_id, PatientShare.patient_id == patient_id)
    )).all()
    return [ShareOut(patient_id=patient_id, doctor_user_id=s.doctor_user_id, doctor_email=email)
            for s, email in rows]


@router.delete("/patients/{patient_id}/shares/{doctor_user_id}", status_code=204)
async def unshare_patient(
    patient_id: str,
    doctor_user_id: str,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    share = (await db.execute(
        select(PatientShare).where(
            PatientShare.tenant_id == current_user.tenant_id,
            PatientShare.patient_id == patient_id,
            PatientShare.doctor_user_id == doctor_user_id,
        )
    )).scalar_one_or_none()
    if share is None:
        raise HTTPException(404, detail="Share not found")
    await db.delete(share)
    await db.commit()


@router.post("/queue/{entry_id}/handoff", response_model=QueueEntryOut)
async def handoff_queue_entry(
    entry_id: str,
    body: HandoffRequest,
    current_user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Hand a queued patient off to another doctor — re-queues them (status=waiting)
    on the target's list. Only the current owning doctor may hand off."""
    entry = (await db.execute(
        select(QueueEntry).where(
            QueueEntry.id == entry_id, QueueEntry.tenant_id == current_user.tenant_id,
            QueueEntry.doctor_user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, detail="Queue entry not found")
    if body.doctor_user_id == current_user.id:
        raise HTTPException(400, detail="Already assigned to you.")
    target = await _get_doctor_user(db, current_user.tenant_id, body.doctor_user_id)
    entry.doctor_user_id = target.id
    entry.status = QueueStatus.waiting
    entry.called_at = None
    patient = await db.get(Patient, entry.patient_id)
    db.add(ClinicNotification(
        tenant_id=current_user.tenant_id, recipient_user_id=target.id, type="handoff",
        payload={"patient_id": entry.patient_id, "patient_name": patient.name if patient else "",
                 "from_doctor": current_user.id},
    ))
    await db.commit()
    await db.refresh(entry)
    for did in (current_user.id, target.id):
        await _publish(current_user.tenant_id, {"type": "queue_changed", "audience": "clinic", "doctor_user_id": did})
    await _publish(current_user.tenant_id, {"type": "handoff", "recipient_user_id": target.id,
                                            "patient_id": entry.patient_id})
    return _queue_out(entry, patient.name if patient else "")
