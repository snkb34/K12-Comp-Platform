from fastapi import FastAPI, Request, Depends, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import io, os
import pandas as pd

from app.database import init_db, get_db
from app.models import Source, Run, Document, CompRow
from app.services.pipeline import preload_sources, run_update, rows_dataframe
from app.services.analytics import licensed_market_summary

APP_VERSION = 'K-12 Compensation Intelligence v0.2.0 - production foundation'

app = FastAPI(title='K-12 Compensation Intelligence')
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

@app.on_event('startup')
def startup():
    init_db()
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        if db.query(Source).count() == 0:
            preload_sources(db)
    finally:
        db.close()

@app.get('/', response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse('index.html', {
        'request': request,
        'version': APP_VERSION,
        'sources': db.query(Source).order_by(Source.district, Source.category).all(),
        'runs': db.query(Run).order_by(Run.started_at.desc()).limit(5).all(),
        'docs': db.query(Document).order_by(Document.created_at.desc()).limit(10).all(),
        'source_count': db.query(Source).count(),
        'row_count': db.query(CompRow).count(),
        'doc_count': db.query(Document).count(),
    })

@app.post('/sources/add')
def add_source(district: str = Form(...), state: str = Form(''), category: str = Form(''), url: str = Form(...), db: Session = Depends(get_db)):
    if district.strip() and url.strip() and not db.query(Source).filter(Source.url == url.strip()).first():
        db.add(Source(district=district.strip(), state=state.strip(), category=category.strip(), url=url.strip()))
        db.commit()
    return RedirectResponse('/', status_code=303)

@app.post('/sources/delete/{source_id}')
def delete_source(source_id: int, db: Session = Depends(get_db)):
    src = db.query(Source).get(source_id)
    if src:
        db.delete(src); db.commit()
    return RedirectResponse('/', status_code=303)

@app.post('/sources/upload')
async def upload_sources(file: UploadFile = File(...), replace: str = Form('no'), db: Session = Depends(get_db)):
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content)).fillna('')
    if replace == 'yes':
        db.query(CompRow).delete(); db.query(Document).delete(); db.query(Source).delete(); db.commit()
    for _, r in df.iterrows():
        district = str(r.get('District') or r.get('district') or '').strip()
        state = str(r.get('State') or r.get('state') or '').strip()
        category = str(r.get('Category') or r.get('category') or '').strip()
        url = str(r.get('Website') or r.get('website') or r.get('URL') or r.get('url') or '').strip()
        if district and url and not db.query(Source).filter(Source.url == url).first():
            db.add(Source(district=district, state=state, category=category, url=url))
    db.commit()
    return RedirectResponse('/', status_code=303)

@app.post('/run')
def run_now(db: Session = Depends(get_db)):
    run_update(db)
    return RedirectResponse('/', status_code=303)

@app.get('/results', response_class=HTMLResponse)
def results(request: Request, q: str = '', db: Session = Depends(get_db)):
    df = rows_dataframe(db, q)
    rows = df.head(500).to_dict(orient='records') if not df.empty else []
    return templates.TemplateResponse('results.html', {'request': request, 'version': APP_VERSION, 'q': q, 'rows': rows, 'count': len(df)})


@app.get('/licensed-market', response_class=HTMLResponse)
def licensed_market(request: Request, db: Session = Depends(get_db)):
    summary = licensed_market_summary(db)
    return templates.TemplateResponse('licensed_market.html', {
        'request': request,
        'version': APP_VERSION,
        'rows': summary['rows'],
        'stats': summary['stats'],
        'jeffco': summary['jeffco'],
    })

@app.get('/licensed-market.csv')
def licensed_market_csv(db: Session = Depends(get_db)):
    summary = licensed_market_summary(db)
    df = pd.DataFrame(summary['rows'])
    if df.empty:
        df = pd.DataFrame(columns=[
            'rank', 'district', 'state', 'year', 'minimum_salary', 'minimum_label',
            'midpoint', 'maximum_salary', 'maximum_label', 'steps', 'lanes'
        ])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=licensed_market_summary.csv'}
    )

@app.get('/documents', response_class=HTMLResponse)
def documents(request: Request, db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).limit(500).all()
    return templates.TemplateResponse('documents.html', {'request': request, 'version': APP_VERSION, 'docs': docs})

@app.post('/clear-results')
def clear_results(db: Session = Depends(get_db)):
    db.query(CompRow).delete(); db.query(Document).delete(); db.query(Run).delete(); db.commit()
    return RedirectResponse('/', status_code=303)

@app.get('/export.csv')
def export_csv(q: str = '', db: Session = Depends(get_db)):
    df = rows_dataframe(db, q)
    if df.empty:
        df = pd.DataFrame(columns=['District','State','Category','Raw Title','Standard Title','Min Salary','Midpoint','Max Salary','Step','Lane','Year','Source URL','Raw Text'])
    buf = io.StringIO(); df.to_csv(buf, index=False); buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type='text/csv', headers={'Content-Disposition':'attachment; filename=k12_comp_results.csv'})

@app.get('/export.xlsx')
def export_excel(q: str = '', db: Session = Depends(get_db)):
    df = rows_dataframe(db, q)
    if df.empty:
        df = pd.DataFrame(columns=['District','State','Category','Raw Title','Standard Title','Min Salary','Midpoint','Max Salary','Step','Lane','Year','Source URL','Raw Text'])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Extracted Rows')
        summary = df.groupby(['District','Category']).size().reset_index(name='Rows') if not df.empty else pd.DataFrame(columns=['District','Category','Rows'])
        summary.to_excel(writer, index=False, sheet_name='Summary')
    output.seek(0)
    return StreamingResponse(output, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition':'attachment; filename=k12_comp_results.xlsx'})
