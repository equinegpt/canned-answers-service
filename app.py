# app.py
from datetime import date

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from db import Base, engine, SessionLocal
from models import CannedAnswer
from schemas import CannedKey, CannedAnswerOut, CannedAnswerIn

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Canned Answers Service")


# --- DB session dependency -----------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from datetime import date
from sqlalchemy.orm import Session

# ...

@app.get("/ui/day", response_class=HTMLResponse)
def ui_day(
    date: date,
    db: Session = Depends(get_db),
):
    # convert to the same "YYYY-MM-DD" string format stored in the DB
    day_str = date.isoformat()

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

    # build a simple HTML table
    row_html = "".join(
        f"<tr>"
        f"<td>{r.pf_meeting_id}</td>"
        f"<td>{r.race_number}</td>"
        f"<td>{r.prompt_type}</td>"
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
        <title>Canned answers for {day_str}</title>
      </head>
      <body>
        <h1>Canned answers for {day_str}</h1>
        <table border="1" cellpadding="4" cellspacing="0">
          <tr>
            <th>Meeting ID</th>
            <th>Race</th>
            <th>Type</th>
            <th>Prompt</th>
            <th>Raw response</th>
          </tr>
          {row_html}
        </table>
      </body>
    </html>
    """

    return HTMLResponse(content=html)


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
