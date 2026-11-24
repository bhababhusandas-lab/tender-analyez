from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import CompanyProfile, User
from app.core.security.auth import get_current_user

router = APIRouter()


class ProfileIn(BaseModel):
    company_name: str = ""
    company_type: str = ""
    established_year: str = ""
    website: str = ""
    address: str = ""
    gst_no: str = ""
    pan_no: str = ""
    cin_no: str = ""
    msme_no: str = ""
    msme_category: str = ""
    iso_certs: str = ""
    other_certs: str = ""
    turnover_y1: str = ""
    turnover_y2: str = ""
    turnover_y3: str = ""
    net_worth: str = ""
    emd_capacity: str = ""
    bg_limit: str = ""
    bank_name: str = ""
    gem_seller_id: str = ""
    cppp_registered: str = ""
    telangana_reg: str = ""
    other_portals: str = ""
    work_categories: str = ""
    states_registered: str = ""
    key_personnel: str = "[]"
    past_projects: str = "[]"


def _to_dict(p: CompanyProfile) -> dict:
    return {c.name: getattr(p, c.name) for c in p.__table__.columns}


def _get_or_create_profile(db: Session, user_id: int) -> CompanyProfile:
    p = db.query(CompanyProfile).filter(CompanyProfile.user_id == user_id).first()
    if not p:
        p = CompanyProfile(user_id=user_id)
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


def _owned_profile(db: Session, user_id: int, profile_id: int) -> CompanyProfile:
    profile = db.query(CompanyProfile).filter(
        CompanyProfile.id == profile_id, CompanyProfile.user_id == user_id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Company profile not found")
    return profile


@router.get("/companies")
def list_companies(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_or_create_profile(db, user.id)
    profiles = db.query(CompanyProfile).filter(CompanyProfile.user_id == user.id).order_by(CompanyProfile.id).all()
    return [_to_dict(p) for p in profiles]


@router.post("/companies")
def create_company(body: ProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = CompanyProfile(user_id=user.id, **body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_dict(p)


@router.get("/companies/{profile_id}")
def get_company(profile_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _to_dict(_owned_profile(db, user.id, profile_id))


@router.put("/companies/{profile_id}")
def update_company(profile_id: int, body: ProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _owned_profile(db, user.id, profile_id)
    for field, val in body.model_dump().items():
        setattr(p, field, val)
    db.commit()
    db.refresh(p)
    return _to_dict(p)


@router.delete("/companies/{profile_id}")
def delete_company(profile_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _owned_profile(db, user.id, profile_id)
    count = db.query(CompanyProfile).filter(CompanyProfile.user_id == user.id).count()
    if count <= 1:
        raise HTTPException(status_code=400, detail="At least one company profile is required")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/company")
def get_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _to_dict(_get_or_create_profile(db, user.id))


@router.put("/company")
def save_profile(body: ProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_or_create_profile(db, user.id)
    for field, val in body.model_dump().items():
        setattr(p, field, val)
    db.commit()
    db.refresh(p)
    return _to_dict(p)


def _profile_context(p: CompanyProfile, heading: str = "COMPANY PROFILE") -> str:
    if not p.company_name:
        return ""
    lines = [
        f"\n\n=== {heading} ===",
        f"Company: {p.company_name} ({p.company_type}, Est. {p.established_year})",
        f"GST: {p.gst_no} | PAN: {p.pan_no} | CIN: {p.cin_no}",
        f"MSME: {p.msme_no} ({p.msme_category})" if p.msme_no else "",
        f"ISO/Certifications: {p.iso_certs}" if p.iso_certs else "",
        f"Other Certifications: {p.other_certs}" if p.other_certs else "",
        f"Turnover: FY2023-24: ₹{p.turnover_y1} | FY2022-23: ₹{p.turnover_y2} | FY2021-22: ₹{p.turnover_y3}",
        f"Net Worth: ₹{p.net_worth}" if p.net_worth else "",
        f"EMD Capacity: ₹{p.emd_capacity} | Bank BG Limit: ₹{p.bg_limit} ({p.bank_name})",
        f"GeM Seller ID: {p.gem_seller_id}" if p.gem_seller_id else "",
        f"Work Categories: {p.work_categories}" if p.work_categories else "",
        f"States Registered: {p.states_registered}" if p.states_registered else "",
        f"Address: {p.address}" if p.address else "",
    ]
    if p.key_personnel and p.key_personnel != "[]":
        lines.append(f"Key Personnel (JSON): {p.key_personnel}")
    if p.past_projects and p.past_projects != "[]":
        lines.append(f"Past Projects (JSON): {p.past_projects}")
    lines.append(f"=== END {heading} ===")
    return "\n".join(l for l in lines if l)


def get_profile_context(db: Session, user_id: int | None = None, profile_id: int | None = None,
                        compare_all: bool = False) -> str:
    """Returns the user's company profile as a formatted string to inject into agent prompts."""
    if user_id is None:
        return ""
    query = db.query(CompanyProfile).filter(CompanyProfile.user_id == user_id)
    profiles = query.order_by(CompanyProfile.id).all()
    if compare_all:
        contexts = [_profile_context(p, f"COMPANY {i}: {p.company_name or 'Unnamed'}") for i, p in enumerate(profiles, 1)]
        return "".join(contexts) + """

=== MULTI-COMPANY COMPARISON MODE ===
Evaluate every company separately against every eligibility criterion. Include a comparison table with a score, verified strengths, gaps, and bid/no-bid recommendation for each company. Clearly recommend the best-fit company and explain why. Never combine credentials belonging to different companies.
=== END COMPARISON MODE ===
"""
    p = next((p for p in profiles if p.id == profile_id), None) if profile_id else (profiles[0] if profiles else None)
    return _profile_context(p) if p else ""
