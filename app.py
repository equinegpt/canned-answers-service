# app.py
from datetime import date

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from db import Base, engine, SessionLocal
from models import CannedAnswer
from schemas import CannedKey, CannedAnswerOut, CannedAnswerIn

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Canned Answers Service")
templates = Jinja2Templates(directory="templates")


# --- DB session dependency -----------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- UI day view ---------------------------------------------
@app.get("/ui/day", response_class=HTMLResponse)
def ui_day(
    day: date,
    request: Request,
    db: Session = Depends(get_db),
):
    # convert to same format you store in DB: "YYYY-MM-DD"
    day_str = day.isoformat()

    rows = (
        db.query(CannedAnswer)
        .filter(CannedAnswer.date == day_str)
        .order_by(
            CannedAnswer.pf_meeting_id,
            CannedAnswer.race_number,
            CannedAnswer.prompt_type,
        )
        .all()
    )
    return templates.TemplateResponse(
        "ui_day.html",
        {"request": request, "rows": rows, "date": day_str},
    )


# Healthcheck
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# GET /canned?date=...&pf_meeting_id=...&race_number=...&prompt_type=...
@app.get("/canned", response_model=CannedAnswerOut, tags=["canned"])
def get_canned_answer(
    date: str,
    pf_meeting_id: int,
    race_number: int,
    prompt_type: str,
    db: Session = Depends(get_db),
):
    key = CannedKey(
        date=date,
        pf_meeting_id=pf_meeting_id,
        race_number=race_number,
        prompt_type=prompt_type,
    )

    row = (
        db.query(CannedAnswer)
        .filter_by(
            date=key.date,
            pf_meeting_id=key.pf_meeting_id,
            race_number=key.race_number,
            prompt_type=key.prompt_type,
        )
        .one_or_none()
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cached answer",
        )

    return CannedAnswerOut(
        date=row.date,
        pf_meeting_id=row.pf_meeting_id,
        race_number=row.race_number,
        prompt_type=row.prompt_type,
        raw_response=row.raw_response,
    )


# POST /canned  (idempotent "first write wins")
@app.post("/canned", response_model=CannedAnswerOut, tags=["canned"])
def create_canned_answer(
    payload: CannedAnswerIn,
    db: Session = Depends(get_db),
):
    # Check if already exists (first-answer-wins)
    existing = (
        db.query(CannedAnswer)
        .filter_by(
            date=payload.date,
            pf_meeting_id=payload.pf_meeting_id,
            race_number=payload.race_number,
            prompt_type=payload.prompt_type,
        )
        .one_or_none()
    )

    if existing:
        # Return existing row unchanged
        return CannedAnswerOut(
            date=existing.date,
            pf_meeting_id=existing.pf_meeting_id,
            race_number=existing.race_number,
            prompt_type=existing.prompt_type,
            raw_response=existing.raw_response,
        )

    row = CannedAnswer(
        date=payload.date,
        pf_meeting_id=payload.pf_meeting_id,
        race_number=payload.race_number,
        prompt_type=payload.prompt_type,
        prompt_text=payload.prompt_text,
        raw_response=payload.raw_response,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return CannedAnswerOut(
        date=row.date,
        pf_meeting_id=row.pf_meeting_id,
        race_number=row.race_number,
        prompt_type=row.prompt_type,
        raw_response=row.raw_response,
    )
