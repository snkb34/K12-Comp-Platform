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

APP_VERSION = 'K-12 Compensation Intelligence v0.2.0 - production foundation'

app = FastAPI(title='K-12 Compensation Intelligence')
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

def _source_parser_for(employee_group: str = "", document_type: str = "") -> str:
    """Choose a default parser from source metadata."""
    group = (employee_group or "").strip().lower()
    doc_type = (document_type or "").strip().lower()

    if "job" in doc_type:
        return "Job List"
    if group == "licensed":
        return "Teacher Schedule"
    if group in {"admin", "administrator", "cabinet", "non represented", "non-represented"}:
        return "Admin Range"
    if group == "classified":
        return "Classified Range"
    if "contract" in doc_type:
        return "Contract"
    return "Generic"


def _source_status(value: str = "") -> str:
    value = (value or "").strip()
    return value or "Active"


def _get_csv_value(row, *names):
    """Read a CSV field with flexible column naming."""
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


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
        db.add(Source(
            district=district.strip(),
            state=state.strip(),
            category=category.strip(),
            employee_group=category.strip(),
            employee_sub_group=category.strip(),
            document_type='Salary Schedule',
            parser=_source_parser_for(category.strip(), 'Salary Schedule'),
            status='Active',
            url=url.strip()
        ))
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
        db.query(CompRow).delete()
        db.query(Document).delete()
        db.query(Source).delete()
        db.commit()

    for _, r in df.iterrows():
        district = _get_csv_value(r, 'District', 'district')
        state = _get_csv_value(r, 'State', 'state')
        url = _get_csv_value(r, 'Website', 'website', 'URL', 'url')

        # New master-source fields
        employee_group = _get_csv_value(r, 'Employee Group', 'employee_group', 'Category', 'category')
        employee_sub_group = _get_csv_value(r, 'Employee Sub Group', 'employee_sub_group', 'Sub Group', 'sub_group')
        document_type = _get_csv_value(r, 'Document Type', 'document_type')
        school_year = _get_csv_value(r, 'School Year', 'school_year', 'Year', 'year')
        parser = _get_csv_value(r, 'Parser', 'parser')
        status = _source_status(_get_csv_value(r, 'Status', 'status'))
        notes = _get_csv_value(r, 'Notes', 'notes')

        # Backward-compatible category field
        category = _get_csv_value(r, 'Category', 'category') or employee_group

              if not parser:
            parser = _source_parser_for(employee_group or category, document_type)

        employee_group_value = (employee_group or category).strip()
        employee_sub_group_value = (
            employee_sub_group
            or employee_group_value
        ).strip()
        document_type_value = (
            document_type or 'Salary Schedule'
        ).strip()
        school_year_value = school_year.strip()
        url_value = url.strip()

        existing_source = (
            db.query(Source)
            .filter(
                Source.url == url_value,
                Source.employee_group == employee_group_value,
                Source.document_type == document_type_value,
                Source.school_year == school_year_value,
            )
            .first()
        )

        if district and url_value and not existing_source:
            db.add(
                Source(
                    district=district.strip(),
                    state=state.strip(),
                    category=category.strip() or employee_group_value,
                    employee_group=employee_group_value,
                    employee_sub_group=employee_sub_group_value,
                    document_type=document_type_value,
                    school_year=school_year_value,
                    parser=parser.strip(),
                    status=status.strip() or 'Active',
                    notes=notes.strip(),
                    url=url_value,
                )
            )

    db.commit()
    return RedirectResponse('/', status_code=303)



@app.get('/source-manager', response_class=HTMLResponse)
def source_manager(request: Request, db: Session = Depends(get_db)):
    sources = db.query(Source).order_by(Source.district, Source.employee_group, Source.employee_sub_group, Source.document_type).all()
    return templates.TemplateResponse('source_manager.html', {
        'request': request,
        'version': APP_VERSION,
        'sources': sources,
        'source_count': len(sources),
    })


@app.post('/source-manager/add')
def source_manager_add(
    district: str = Form(...),
    state: str = Form('CO'),
    employee_group: str = Form(''),
    employee_sub_group: str = Form(''),
    document_type: str = Form('Salary Schedule'),
    school_year: str = Form(''),
    parser: str = Form(''),
    status: str = Form('Active'),
    url: str = Form(...),
    notes: str = Form(''),
    db: Session = Depends(get_db),
):
    district_value = district.strip()
    state_value = state.strip()
    employee_group_value = employee_group.strip()
    employee_sub_group_value = (
        employee_sub_group.strip() or employee_group_value
    )
    document_type_value = (
        document_type.strip() or 'Salary Schedule'
    )
    school_year_value = school_year.strip()
    url_value = url.strip()
    parser_value = (
        parser.strip()
        or _source_parser_for(
            employee_group_value,
            document_type_value,
        )
    )

    existing_source = (
        db.query(Source)
        .filter(
            Source.url == url_value,
            Source.employee_group == employee_group_value,
            Source.document_type == document_type_value,
            Source.school_year == school_year_value,
        )
        .first()
    )

    if district_value and url_value and not existing_source:
        db.add(
            Source(
                district=district_value,
                state=state_value,
                category=employee_group_value,
                employee_group=employee_group_value,
                employee_sub_group=employee_sub_group_value,
                document_type=document_type_value,
                school_year=school_year_value,
                parser=parser_value,
                status=_source_status(status),
                url=url_value,
                notes=notes.strip(),
            )
        )
        db.commit()

    return RedirectResponse('/source-manager', status_code=303)


@app.post('/source-manager/delete/{source_id}')
def source_manager_delete(source_id: int, db: Session = Depends(get_db)):
    src = db.query(Source).get(source_id)
    if src:
        db.delete(src)
        db.commit()
    return RedirectResponse('/source-manager', status_code=303)


@app.get('/source-manager/export.csv')
def source_manager_export_csv(db: Session = Depends(get_db)):
    sources = db.query(Source).order_by(Source.district, Source.employee_group, Source.employee_sub_group).all()
    data = [{
        'District': s.district,
        'State': s.state,
        'Employee Group': s.employee_group or s.category,
        'Employee Sub Group': s.employee_sub_group or s.category,
        'Document Type': s.document_type,
        'School Year': s.school_year,
        'Website': s.url,
        'Parser': s.parser,
        'Status': s.status,
        'Notes': s.notes,
    } for s in sources]
    df = pd.DataFrame(data)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=k12_comp_master_sources_export.csv'}
    )


@app.post('/run')
def run_now(db: Session = Depends(get_db)):
    run_update(db)
    return RedirectResponse('/', status_code=303)

@app.get('/results', response_class=HTMLResponse)
def results(request: Request, q: str = '', db: Session = Depends(get_db)):
    df = rows_dataframe(db, q)
    rows = df.head(500).to_dict(orient='records') if not df.empty else []
    return templates.TemplateResponse('results.html', {'request': request, 'version': APP_VERSION, 'q': q, 'rows': rows, 'count': len(df)})

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
