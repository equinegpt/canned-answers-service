# app.py
from datetime import date, datetime
from typing import Optional

from fastapi import (
    FastAPI,
    Depends,
    Query,
    Request,
    HTTPException,
    status,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from db import Base, engine, SessionLocal
from models import CannedAnswer
from schemas import CannedKey, CannedAnswerOut, CannedAnswerIn

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Canned Answers Service")
templates = Jinja2Templates(directory="templates")


# --- DB session dependency -----------------------------------
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _today_melbourne() -> date:
    """Today in AU/Melbourne, for filtering UI to 'today + future'."""
    return datetime.now(ZoneInfo("Australia/Melbourne")).date()


# --- UI: per-day view ----------------------------------------
@app.get("/ui/day", response_class=HTMLResponse)
def ui_day(
    date: date,
    db: Session = Depends(get_db),
):
    """
    Simple HTML view of all canned answers for a given date.

    Called as: /ui/day?date=2025-11-29
    """

    # First try matching with a true DATE value
    rows = (
        db.query(CannedAnswer)
        .filter(CannedAnswer.date == date)
        .order_by(
            CannedAnswer.pf_meeting_id,
            CannedAnswer.race_number,
            CannedAnswer.prompt_type,
        )
        .all()
    )

    # Fallback in case legacy rows stored date as a string
    if not rows:
        rows = (
            db.query(CannedAnswer)
            .filter(CannedAnswer.date == date.isoformat())
            .order_by(
                CannedAnswer.pf_meeting_id,
                CannedAnswer.race_number,
                CannedAnswer.prompt_type,
            )
            .all()
        )

    row_html = "".join(
        f"<tr>"
        f"<td>{r.pf_meeting_id}</td>"
        f"<td>{r.race_number}</td>"
        f"<td>{r.prompt_type}</td>"
        f"<td>{r.use_count or 0}</td>"
        f"<td><pre>{(r.prompt_text or '')}</pre></td>"
        f"<td><pre>{(r.raw_response or '')}</pre></td>"
        f"</tr>"
        for r in rows
    )

    html = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>Canned answers for {date.isoformat()}</title>
      </head>
      <body>
        <h1>Canned answers for {date.isoformat()}</h1>
        <table border="1" cellpadding="4" cellspacing="0">
          <tr>
            <th>Meeting ID</th>
            <th>Race</th>
            <th>Type</th>
            <th>Use count</th>
            <th>Prompt</th>
            <th>Raw response</th>
          </tr>
          {row_html}
        </table>
      </body>
    </html>
    """

    return HTMLResponse(content=html)


# --- UI: all (today + future) --------------------------------
@app.get("/ui/all", response_class=HTMLResponse)
def ui_all(
    request: Request,
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """
    Admin-style view: all canned answers from today onwards,
    with optional date range filtering.
    """
    today = _today_melbourne()

    q = db.query(CannedAnswer).filter(CannedAnswer.date >= today)

    if start_date:
        q = q.filter(CannedAnswer.date >= start_date)
    if end_date:
        q = q.filter(CannedAnswer.date <= end_date)

    answers = (
        q.order_by(
            CannedAnswer.date,
            CannedAnswer.pf_meeting_id,
            CannedAnswer.race_number,
            CannedAnswer.prompt_type,
        )
        .all()
    )

    # Distinct dates to render as "jump to" buttons
    distinct_dates = [
        row[0]
        for row in (
            db.query(CannedAnswer.date)
            .filter(CannedAnswer.date >= today)
            .distinct()
            .order_by(CannedAnswer.date)
            .all()
        )
    ]

    return templates.TemplateResponse(
        "ui_all.html",
        {
            "request": request,
            "answers": answers,
            "distinct_dates": distinct_dates,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


# --- Healthcheck ---------------------------------------------
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# --- Usage bump helper ---------------------------------------
def bump_usage(answer: CannedAnswer, request: Request) -> None:
    now = datetime.utcnow()

    # Render passes real client IP via X-Forwarded-For
    forwarded_for = request.headers.get("x-forwarded-for")
    client_ip = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else request.client.host
    )
    user_agent = request.headers.get("user-agent")

    answer.use_count = (answer.use_count or 0) + 1

    # These fields are optional – only set them if you added them to the model
    if getattr(answer, "first_used_at", None) is None:
        setattr(answer, "first_used_at", now)
        setattr(answer, "first_used_ip", client_ip)
        setattr(answer, "first_used_ua", user_agent)

    setattr(answer, "last_used_at", now)
    setattr(answer, "last_used_ip", client_ip)
    setattr(answer, "last_used_ua", user_agent)


# --- JSON API: get / create ----------------------------------
@app.get("/canned", response_model=CannedAnswerOut, tags=["canned"])
def get_canned_answer(
    date: str,
    pf_meeting_id: int,
    race_number: int,
    prompt_type: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Fetch a cached answer by key.

    Side-effect: increments use_count (and usage metadata) each time it's read.
    """
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

    # bump use_count + IP/UA metadata
    bump_usage(row, request)
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


@app.post("/canned", response_model=CannedAnswerOut, tags=["canned"])
def create_canned_answer(
    payload: CannedAnswerIn,
    db: Session = Depends(get_db),
):
    """
    Idempotent create: first write wins.
    """
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
        use_count=0,  # new rows start at 0
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
