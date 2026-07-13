from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Float,
    ForeignKey,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Source(Base):
    """
    Master source record for district compensation documents.

    This model is backward-compatible with the original app:
    - category still exists
    - url still exists
    - existing upload/import logic will continue working

    New fields support the long-term Source Manager.
    """
    __tablename__ = 'sources'

    __table_args__ = (
        UniqueConstraint(
            'url',
            'employee_group',
            'document_type',
            'school_year',
            name='uq_source_url_group_document_year',
        ),
    )

    id = Column(Integer, primary_key=True)

    district = Column(String(200), nullable=False)
    state = Column(String(20), nullable=True)

    category = Column(String(100), nullable=True)

    employee_group = Column(String(100), nullable=True)
    employee_sub_group = Column(String(200), nullable=True)
    document_type = Column(String(100), nullable=True)
    school_year = Column(String(50), nullable=True)
    parser = Column(String(100), nullable=True)
    status = Column(String(50), nullable=True, default='Active')
    priority = Column(Integer, nullable=True, default=1)
    notes = Column(Text, nullable=True)

    url = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship(
        'Document',
        back_populates='source',
        cascade='all, delete-orphan',
    )


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
    quality_issues = relationship('DataQualityIssue', back_populates='document', cascade='all, delete-orphan')


class CompRow(Base):
    """
    Raw extracted compensation rows.

    This remains the landing zone for parser output. Analytics tables can be built
    from this data later.
    """
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


class DataQualityIssue(Base):
    """
    Stores issues found during extraction or analytics validation.

    Examples:
    - Missing step labels
    - Missing lane labels
    - Suspicious salary value
    - Too few rows extracted
    - Broken source URL
    """
    __tablename__ = 'data_quality_issues'

    id = Column(Integer, primary_key=True)

    source_id = Column(Integer, ForeignKey('sources.id'), nullable=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=True)

    district = Column(String(200), nullable=True)
    employee_group = Column(String(100), nullable=True)
    school_year = Column(String(50), nullable=True)

    severity = Column(String(50), default='warning')  # info, warning, critical
    issue_type = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)

    expected_value = Column(String(200), nullable=True)
    actual_value = Column(String(200), nullable=True)

    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship('Document', back_populates='quality_issues')


class PositionCompensation(Base):
    """
    Normalized position-based compensation record.

    Used primarily for Administrator, Classified, Cabinet, and Non-Represented
    market comparisons where a position maps to a salary range or grade.
    """
    __tablename__ = 'position_compensation'

    id = Column(Integer, primary_key=True)

    source_id = Column(Integer, ForeignKey('sources.id'), nullable=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=True)

    district = Column(String(200), nullable=False)
    state = Column(String(20), nullable=True)
    employee_group = Column(String(100), nullable=True)
    employee_sub_group = Column(String(200), nullable=True)
    school_year = Column(String(50), nullable=True)

    raw_title = Column(Text, nullable=True)
    standard_title = Column(Text, nullable=True)

    job_code = Column(String(100), nullable=True)
    grade = Column(String(100), nullable=True)
    range_name = Column(String(100), nullable=True)

    min_salary = Column(Float, nullable=True)
    midpoint = Column(Float, nullable=True)
    max_salary = Column(Float, nullable=True)
    hourly_min = Column(Float, nullable=True)
    hourly_max = Column(Float, nullable=True)

    source_url = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LicensedScheduleCell(Base):
    """
    Normalized licensed salary schedule cell.

    This is the long-term model for teacher/licensed schedules:
    one row per district/year/step/lane/salary.
    """
    __tablename__ = 'licensed_schedule_cells'

    id = Column(Integer, primary_key=True)

    source_id = Column(Integer, ForeignKey('sources.id'), nullable=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=True)

    district = Column(String(200), nullable=False)
    state = Column(String(20), nullable=True)
    school_year = Column(String(50), nullable=True)

    schedule_name = Column(String(200), nullable=True)
    step = Column(String(100), nullable=True)
    lane = Column(String(100), nullable=True)
    salary = Column(Float, nullable=False)

    source_url = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MarketSnapshot(Base):
    """
    Stores reusable market-analysis outputs.

    This allows the app to save generated reports instead of recalculating them
    every time.
    """
    __tablename__ = 'market_snapshots'

    id = Column(Integer, primary_key=True)

    analysis_type = Column(String(100), nullable=False)  # licensed_summary, admin_position, classified_position
    title = Column(String(300), nullable=True)
    school_year = Column(String(50), nullable=True)
    comparison_group = Column(String(200), nullable=True)

    district_count = Column(Integer, default=0)
    average_minimum = Column(Float, nullable=True)
    average_midpoint = Column(Float, nullable=True)
    average_maximum = Column(Float, nullable=True)

    focus_district = Column(String(200), nullable=True)
    focus_rank = Column(Integer, nullable=True)
    focus_difference = Column(Float, nullable=True)
    focus_percent_difference = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class JobAlias(Base):
    """
    Stores title matching and standardization rules.

    Example:
    raw_title = "Chief Talent Officer"
    standard_title = "Chief Human Resources Officer"
    """
    __tablename__ = 'job_aliases'

    id = Column(Integer, primary_key=True)

    employee_group = Column(String(100), nullable=True)
    raw_title = Column(Text, nullable=False)
    standard_title = Column(Text, nullable=False)

    match_confidence = Column(Float, nullable=True)
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
