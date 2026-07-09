from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Source(Base):
    __tablename__ = 'sources'
    id = Column(Integer, primary_key=True)
    district = Column(String(200), nullable=False)
    state = Column(String(20), nullable=True)
    category = Column(String(100), nullable=True)
    url = Column(Text, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    documents = relationship('Document', back_populates='source', cascade='all, delete-orphan')

class Run(Base):
    __tablename__ = 'runs'
    id = Column(Integer, primary_key=True)
    status = Column(String(50), default='started')
    message = Column(Text, default='')
    documents_downloaded = Column(Integer, default=0)
    rows_extracted = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

class Document(Base):
    __tablename__ = 'documents'
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey('sources.id'))
    run_id = Column(Integer, ForeignKey('runs.id'))
    original_url = Column(Text, nullable=False)
    file_name = Column(String(300), nullable=True)
    content_type = Column(String(200), nullable=True)
    file_size = Column(Integer, default=0)
    status = Column(String(50), default='downloaded')
    message = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    source = relationship('Source', back_populates='documents')
    rows = relationship('CompRow', back_populates='document', cascade='all, delete-orphan')

class CompRow(Base):
    __tablename__ = 'comp_rows'
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'))
    district = Column(String(200))
    state = Column(String(20))
    category = Column(String(100))
    raw_title = Column(Text)
    standard_title = Column(Text, nullable=True)
    min_salary = Column(Float, nullable=True)
    midpoint = Column(Float, nullable=True)
    max_salary = Column(Float, nullable=True)
    step = Column(String(100), nullable=True)
    lane = Column(String(100), nullable=True)
    year = Column(String(100), nullable=True)
    source_url = Column(Text)
    raw_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    document = relationship('Document', back_populates='rows')
