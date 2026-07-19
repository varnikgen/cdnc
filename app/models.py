from sqlalchemy import Column, String, DateTime, UUID
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import uuid
from app.db import Base

class Device(Base):
    __tablename__ = "devices"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mac = Column(String(12), unique=True, index=True, nullable=False)
    model = Column(String(20), nullable=False)
    firmware_target = Column(String(20), default="96.86.0.15")
    status = Column(String(20), default="unknown")
    last_seen = Column(DateTime)
    template_id = Column(PG_UUID(as_uuid=True), nullable=True)
    overrides = Column(JSONB, default=dict)

class Template(Base):
    __tablename__ = "templates"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    scope = Column(String(20), nullable=False)  # "global", "model:T3x", "model:T4x"
    content = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)