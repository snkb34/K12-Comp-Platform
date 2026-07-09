import os, re, io, hashlib
from datetime import datetime
from urllib.parse import urlparse
import requests
import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from app.models import Source, Run, Document, CompRow

DOWNLOAD_DIR = os.environ.get('DOWNLOAD_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'downloads'))
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MONEY_RE = re.compile(r'\$?\s*([0-9]{2,3}(?:,[0-9]{3})+(?:\.\d{2})?|[0-9]{5,6}(?:\.\d{2})?)')
YEAR_RE = re.compile(r'(20\d{2}\s*[-–]\s*\d{2,4}|20\d{2})')


def preload_sources(db: Session, csv_path='districts_template.csv'):
    if not os.path.exists(csv_path):
        return 0
    df = pd.read_csv(csv_path).fillna('')
    added = 0
    for _, r in df.iterrows():
        district = str(r.get('District') or r.get('district') or '').strip()
        url = str(r.get('Website') or r.get('website') or r.get('URL') or r.get('url') or '').strip()
        if not district or not url:
            continue
        if not db.query(Source).filter(Source.url == url).first():
            db.add(Source(district=district, state=str(r.get('State') or r.get('state') or '').strip(), category=str(r.get('Category') or r.get('category') or '').strip(), url=url))
            added += 1
    db.commit()
    return added


def normalize_money(value):
    if value is None:
        return None
    s = str(value).replace('$','').replace(',','').strip()
    try:
        n = float(s)
        return n if n >= 1000 else None
    except Exception:
        return None


def likely_direct_file(url, content_type=''):
    u = url.lower().split('?')[0]
    ct = (content_type or '').lower()
    return any(u.endswith(ext) for ext in ['.pdf','.xlsx','.xls','.csv']) or any(x in ct for x in ['pdf','spreadsheet','excel','csv','octet-stream']) or '/fs/resource-manager/view/' in u or 'aptg.co/' in u


def discover_links(url):
    try:
        r = requests.get(url, timeout=25, headers={'User-Agent':'K12CompIntel/1.0'})
        r.raise_for_status()
    except Exception:
        return [url]
    if likely_direct_file(url, r.headers.get('content-type','')):
        return [url]
    soup = BeautifulSoup(r.text, 'lxml')
    links = []
    keywords = ['salary','compensation','schedule','licensed','admin','administrator','classified','wage','pay']
    for a in soup.find_all('a', href=True):
        text = (a.get_text(' ') + ' ' + a['href']).lower()
        if any(k in text for k in keywords):
            href = requests.compat.urljoin(url, a['href'])
            links.append(href)
    return links[:10] or [url]


def download(url):
    r = requests.get(url, timeout=60, allow_redirects=True, headers={'User-Agent':'K12CompIntel/1.0'})
    r.raise_for_status()
    content_type = r.headers.get('content-type','')
    parsed = urlparse(r.url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if not ext:
        if 'pdf' in content_type.lower(): ext = '.pdf'
        elif 'excel' in content_type.lower() or 'spreadsheet' in content_type.lower(): ext = '.xlsx'
        elif 'csv' in content_type.lower(): ext = '.csv'
        else: ext = '.bin'
    h = hashlib.sha1((url + str(datetime.utcnow())).encode()).hexdigest()[:12]
    file_name = f'{h}{ext}'
    path = os.path.join(DOWNLOAD_DIR, file_name)
    with open(path, 'wb') as f:
        f.write(r.content)
    return path, file_name, content_type, len(r.content)


def extract_pdf(path, source: Source, source_url: str):
    rows = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            year = None
            text = page.extract_text() or ''
            ym = YEAR_RE.search(text)
            if ym: year = ym.group(1)
            # table extraction first
            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []
            for table in tables:
                if not table or len(table) < 2:
                    continue
                for cells in table:
                    cells = [(c or '').strip() for c in cells]
                    line = ' | '.join([c for c in cells if c])
                    money = [normalize_money(m) for m in MONEY_RE.findall(line)]
                    money = [m for m in money if m]
                    if not money:
                        continue
                    title = next((c for c in cells if c and not MONEY_RE.search(c) and len(c) > 2), line[:120])
                    rows.append(make_row(source, source_url, title, money, year, line))
            # fallback line extraction for PDFs where tables fail
            for line in text.splitlines():
                money = [normalize_money(m) for m in MONEY_RE.findall(line)]
                money = [m for m in money if m]
                if len(money) >= 1 and len(line) < 300:
                    title_part = MONEY_RE.split(line)[0].strip(' -|:')[:150]
                    if len(title_part) >= 3:
                        rows.append(make_row(source, source_url, title_part, money, year, f'p{page_num}: {line}'))
    return dedupe_rows(rows)


def extract_excel(path, source: Source, source_url: str):
    rows = []
    xls = pd.read_excel(path, sheet_name=None, header=None)
    for sheet, df in xls.items():
        for _, r in df.fillna('').iterrows():
            cells = [str(x).strip() for x in r.tolist() if str(x).strip()]
            line = ' | '.join(cells)
            money = [normalize_money(m) for m in MONEY_RE.findall(line)]
            money = [m for m in money if m]
            if not money:
                continue
            title = next((c for c in cells if not MONEY_RE.search(c) and len(c) > 2), line[:120])
            ym = YEAR_RE.search(line)
            rows.append(make_row(source, source_url, title, money, ym.group(1) if ym else None, f'{sheet}: {line}'))
    return dedupe_rows(rows)


def extract_csv(path, source: Source, source_url: str):
    rows = []
    df = pd.read_csv(path, header=None).fillna('')
    for _, r in df.iterrows():
        cells = [str(x).strip() for x in r.tolist() if str(x).strip()]
        line = ' | '.join(cells)
        money = [normalize_money(m) for m in MONEY_RE.findall(line)]
        money = [m for m in money if m]
        if money:
            title = next((c for c in cells if not MONEY_RE.search(c) and len(c) > 2), line[:120])
            rows.append(make_row(source, source_url, title, money, None, line))
    return dedupe_rows(rows)


def make_row(source, source_url, title, money, year, raw_text):
    money = sorted([m for m in money if m])
    min_salary = money[0] if money else None
    max_salary = money[-1] if len(money) > 1 else None
    midpoint = round((min_salary + max_salary) / 2, 2) if min_salary and max_salary else None
    return CompRow(district=source.district, state=source.state, category=source.category, raw_title=title, min_salary=min_salary, midpoint=midpoint, max_salary=max_salary, year=year, source_url=source_url, raw_text=raw_text[:1000])


def dedupe_rows(rows):
    seen, out = set(), []
    for r in rows:
        key = (r.district, r.category, r.raw_title, r.min_salary, r.max_salary, r.raw_text[:100])
        if key not in seen:
            seen.add(key); out.append(r)
    return out


def run_update(db: Session):
    run = Run(status='running', message='Starting update')
    db.add(run); db.commit(); db.refresh(run)
    docs = 0; total_rows = 0
    sources = db.query(Source).order_by(Source.district).all()
    for source in sources:
        for url in discover_links(source.url):
            try:
                path, file_name, content_type, size = download(url)
                doc = Document(source_id=source.id, run_id=run.id, original_url=url, file_name=file_name, content_type=content_type, file_size=size, status='downloaded')
                db.add(doc); db.commit(); db.refresh(doc)
                ext = os.path.splitext(path)[1].lower()
                if ext == '.pdf': rows = extract_pdf(path, source, url)
                elif ext in ['.xlsx','.xls']: rows = extract_excel(path, source, url)
                elif ext == '.csv': rows = extract_csv(path, source, url)
                else: rows = []
                for row in rows:
                    row.document_id = doc.id
                    db.add(row)
                doc.status = 'extracted' if rows else 'downloaded_no_rows'
                doc.message = f'Extracted {len(rows)} rows' if rows else 'Downloaded but no salary rows recognized'
                db.commit()
                docs += 1; total_rows += len(rows)
            except Exception as e:
                doc = Document(source_id=source.id, run_id=run.id, original_url=url, status='failed', message=str(e)[:1000])
                db.add(doc); db.commit()
    run.status = 'completed'
    run.documents_downloaded = docs
    run.rows_extracted = total_rows
    run.message = f'Completed. Downloaded {docs} documents and extracted {total_rows} rows.'
    run.finished_at = datetime.utcnow()
    db.commit()
    return run


def rows_dataframe(db: Session, q: str = ''):
    query = db.query(CompRow)
    if q:
        like = f'%{q}%'
        query = query.filter(CompRow.raw_title.ilike(like) | CompRow.district.ilike(like) | CompRow.category.ilike(like) | CompRow.raw_text.ilike(like))
    rows = query.order_by(CompRow.district, CompRow.category, CompRow.raw_title).limit(10000).all()
    data = [{
        'District': r.district, 'State': r.state, 'Category': r.category, 'Raw Title': r.raw_title,
        'Standard Title': r.standard_title, 'Min Salary': r.min_salary, 'Midpoint': r.midpoint,
        'Max Salary': r.max_salary, 'Step': r.step, 'Lane': r.lane, 'Year': r.year,
        'Source URL': r.source_url, 'Raw Text': r.raw_text
    } for r in rows]
    return pd.DataFrame(data)
