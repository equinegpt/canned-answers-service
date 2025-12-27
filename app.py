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
from ra_meetings import fetch_meeting_labels

from db import Base, engine, SessionLocal
from models import CannedAnswer, MeetingLabel, FreeformQuestion
from schemas import (
    CannedKey, CannedAnswerOut, CannedAnswerIn,
    FreeformQuestionIn, FreeformQuestionOut, FreeformMatchResult,
)
from freeform_matching import (
    normalize_question, tokenize_question, tokens_to_json,
    json_to_tokens, find_best_match,
)

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
    Admin-style view: all canned answers.

    - Default (no params): show today + future (Melbourne time).
    - If start_date/end_date are provided: use that explicit range.
    """

    today = _today_melbourne()

    # Default: today + future if no explicit range supplied
    if start_date is None and end_date is None:
        start_date = today

    q = db.query(CannedAnswer)

    # IMPORTANT: compare DATE column to Python date objects, not strings
    if start_date is not None:
        q = q.filter(CannedAnswer.date >= start_date)
    if end_date is not None:
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

    # --- NEW: hydrate meeting labels using local cache + RA-crawler ---
    pf_ids = {a.pf_meeting_id for a in answers if a.pf_meeting_id is not None}
    labels: dict[int, str] = {}

    if pf_ids:
        # 1) Check local cache first
        cached_rows = (
            db.query(MeetingLabel)
            .filter(MeetingLabel.pf_meeting_id.in_(pf_ids))
            .all()
        )
        labels = {r.pf_meeting_id: r.label for r in cached_rows}
        missing_ids = pf_ids - labels.keys()

        # 2) For any missing, ask RA-crawler (within the current date range)
        if missing_ids:
            # pick a sensible range to call RA with
            # (fall back to all known dates in answers if start/end are None)
            dates_for_lookup = [a.date for a in answers if isinstance(a.date, date)]
            if dates_for_lookup:
                lo = min(dates_for_lookup)
                hi = max(dates_for_lookup)
            else:
                lo = start_date
                hi = end_date

            ra_labels = fetch_meeting_labels(lo, hi)

            # 3) Store whatever RA knows into the cache
            for mid in missing_ids:
                label = ra_labels.get(mid)
                if not label:
                    continue
                labels[mid] = label
                db.add(MeetingLabel(pf_meeting_id=mid, label=label))

            db.commit()

    # Attach label to each answer for the template
    for a in answers:
        a.meeting_label = labels.get(a.pf_meeting_id)

    # Distinct dates for the "Jump to" buttons (unchanged)
    distinct_dates = [
        row[0]
        for row in (
            db.query(CannedAnswer.date)
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
@app.get("/ui/day/mobile", response_class=HTMLResponse)
def ui_day_mobile(
    date: date,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Mobile-friendly view of canned answers for a given date.

    - Groups by meeting (track)
    - Each track is collapsible
    - Shows Race + prompt text (tips)
    """

    # Same query logic as ui_day
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

    # Get track labels from cache / RA
    meeting_labels = {}
    if rows:
        # use a 1-day window for RA
        labels = fetch_meeting_labels(date, date)
        meeting_labels = labels or {}

    # Group rows by meeting
    meetings = {}
    for r in rows:
        mid = r.pf_meeting_id
        if mid not in meetings:
            label = meeting_labels.get(mid) or str(mid)
            meetings[mid] = {
                "pf_meeting_id": mid,
                "label": label,
                "rows": [],
            }
        meetings[mid]["rows"].append(r)

    meeting_list = sorted(
        meetings.values(),
        key=lambda m: m["label"]
    )

    return templates.TemplateResponse(
        "ui_day_mobile.html",
        {
            "request": request,
            "date": date,
            "meetings": meeting_list,
        },
    )


# --- Freeform Question Endpoints --------------------------------

@app.post("/freeform", response_model=FreeformQuestionOut, tags=["freeform"])
def create_freeform_question(
    payload: FreeformQuestionIn,
    db: Session = Depends(get_db),
):
    """
    Store a freeform Q&A pair with normalized tokens for fuzzy matching.

    - Stores original question as-is
    - Computes and stores normalized version + token array
    - Idempotent: returns existing if exact same normalized question already exists for this race
    """
    # Normalize and tokenize
    normalized = normalize_question(payload.question)
    tokens = tokenize_question(normalized)
    tokens_json = tokens_to_json(tokens)

    # Check for exact duplicate (same normalized question for same race)
    existing = (
        db.query(FreeformQuestion)
        .filter_by(
            date=payload.date,
            pf_meeting_id=payload.pf_meeting_id,
            race_number=payload.race_number,
            question_normalized=normalized,
        )
        .one_or_none()
    )

    if existing:
        return FreeformQuestionOut(
            date=existing.date,
            pf_meeting_id=existing.pf_meeting_id,
            race_number=existing.race_number,
            question=existing.question,
            raw_response=existing.raw_response,
            use_count=existing.use_count,
        )

    row = FreeformQuestion(
        date=payload.date,
        pf_meeting_id=payload.pf_meeting_id,
        race_number=payload.race_number,
        question=payload.question,
        question_normalized=normalized,
        question_tokens=tokens_json,
        raw_response=payload.raw_response,
        use_count=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return FreeformQuestionOut(
        date=row.date,
        pf_meeting_id=row.pf_meeting_id,
        race_number=row.race_number,
        question=row.question,
        raw_response=row.raw_response,
        use_count=row.use_count,
    )


@app.get("/freeform/match", response_model=FreeformMatchResult, tags=["freeform"])
def match_freeform_question(
    question: str,
    date: date,
    pf_meeting_id: int,
    race_number: int,
    threshold: float = Query(default=0.70, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    """
    Find a cached freeform question matching the query using fuzzy matching.

    Algorithm:
    1. Normalize query: lowercase, remove punctuation
    2. Tokenize and remove stop words
    3. Search only within same race (date + pf_meeting_id + race_number)
    4. Calculate Jaccard similarity for each candidate
    5. Return best match if confidence >= threshold, else 404
    """
    # Normalize and tokenize the query
    normalized = normalize_question(question)
    query_tokens = tokenize_question(normalized)

    if not query_tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query contains only stop words or is empty",
        )

    # Fetch all candidates for this race (indexed query, fast)
    candidates_db = (
        db.query(FreeformQuestion)
        .filter_by(
            date=date,
            pf_meeting_id=pf_meeting_id,
            race_number=race_number,
        )
        .all()
    )

    if not candidates_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching question found",
        )

    # Build candidates list with parsed tokens
    candidates = [
        (row, json_to_tokens(row.question_tokens))
        for row in candidates_db
    ]

    # Find best match
    result = find_best_match(query_tokens, candidates, threshold)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching question found",
        )

    best_row, confidence = result

    # Bump usage count on match
    best_row.use_count = (best_row.use_count or 0) + 1
    db.add(best_row)
    db.commit()

    return FreeformMatchResult(
        question=best_row.question,
        raw_response=best_row.raw_response,
        confidence=round(confidence, 4),
    )


@app.get("/ui/freeform", response_class=HTMLResponse)
def ui_freeform(
    date: date,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    UI view showing all freeform Q&As for a date, grouped by meeting/race.
    """
    rows = (
        db.query(FreeformQuestion)
        .filter(FreeformQuestion.date == date)
        .order_by(
            FreeformQuestion.pf_meeting_id,
            FreeformQuestion.race_number,
            FreeformQuestion.created_at,
        )
        .all()
    )

    # Get meeting labels
    meeting_labels = {}
    if rows:
        labels = fetch_meeting_labels(date, date)
        meeting_labels = labels or {}

    # Group by meeting, then by race
    meetings = {}
    for r in rows:
        mid = r.pf_meeting_id
        if mid not in meetings:
            label = meeting_labels.get(mid) or str(mid)
            meetings[mid] = {
                "pf_meeting_id": mid,
                "label": label,
                "races": {},
            }

        race_num = r.race_number
        if race_num not in meetings[mid]["races"]:
            meetings[mid]["races"][race_num] = []
        meetings[mid]["races"][race_num].append(r)

    # Sort meetings and races
    meeting_list = sorted(meetings.values(), key=lambda m: m["label"])
    for m in meeting_list:
        m["races"] = dict(sorted(m["races"].items()))

    return templates.TemplateResponse(
        "ui_freeform.html",
        {
            "request": request,
            "date": date,
            "meetings": meeting_list,
        },
    )


@app.get("/ui/freeform/stats", response_class=HTMLResponse)
def ui_freeform_stats(
    request: Request,
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """
    Analytics view for freeform question caching - shows fuzzy match performance.
    """
    today = _today_melbourne()

    # Default: last 7 days if no range supplied
    if start_date is None and end_date is None:
        end_date = today
        start_date = today - __import__('datetime').timedelta(days=7)

    # Query all freeform questions in range
    q = db.query(FreeformQuestion)
    if start_date is not None:
        q = q.filter(FreeformQuestion.date >= start_date)
    if end_date is not None:
        q = q.filter(FreeformQuestion.date <= end_date)

    all_questions = q.all()

    # Calculate stats
    total_cached = len(all_questions)
    total_matches = sum(fq.use_count for fq in all_questions)
    questions_with_matches = sum(1 for fq in all_questions if fq.use_count > 0)

    # Group by date for daily breakdown
    daily_stats = {}
    for fq in all_questions:
        d = fq.date
        if d not in daily_stats:
            daily_stats[d] = {"cached": 0, "matches": 0, "questions_matched": 0}
        daily_stats[d]["cached"] += 1
        daily_stats[d]["matches"] += fq.use_count
        if fq.use_count > 0:
            daily_stats[d]["questions_matched"] += 1

    # Sort by date descending
    daily_breakdown = sorted(
        [{"date": d, **stats} for d, stats in daily_stats.items()],
        key=lambda x: x["date"],
        reverse=True
    )

    # Top matched questions (most reused)
    top_questions = sorted(
        [fq for fq in all_questions if fq.use_count > 0],
        key=lambda x: x.use_count,
        reverse=True
    )[:20]

    # Get meeting labels for top questions
    meeting_labels = {}
    if top_questions and start_date and end_date:
        labels = fetch_meeting_labels(start_date, end_date)
        meeting_labels = labels or {}

    return templates.TemplateResponse(
        "ui_freeform_stats.html",
        {
            "request": request,
            "start_date": start_date,
            "end_date": end_date,
            "total_cached": total_cached,
            "total_matches": total_matches,
            "questions_with_matches": questions_with_matches,
            "match_rate": round((questions_with_matches / total_cached * 100), 1) if total_cached > 0 else 0,
            "daily_breakdown": daily_breakdown,
            "top_questions": top_questions,
            "meeting_labels": meeting_labels,
        },
    )