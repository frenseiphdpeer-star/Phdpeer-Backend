"""DocumentArtifact model."""
from sqlalchemy import Column, String, Text, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import BaseModel


class DocumentArtifact(Base, BaseModel):
    """
    DocumentArtifact model for storing uploaded documents and related metadata.
    
    Documents can include research proposals, literature reviews, papers,
    progress reports, etc.
    
    Attributes:
        user_id: Reference to the user who uploaded the document
        title: Document title
        description: Document description
        file_type: Type of file (pdf, docx, etc.)
        file_path: Storage path or URL of the document
        file_size_bytes: Size of the file in bytes
        document_type: Type of document (proposal, paper, report, etc.)
        raw_text: Raw extracted text (before normalization)
        document_text: Normalized extracted text (after processing)
        word_count: Number of words in the document
        detected_language: ISO 639-1 language code (e.g., 'en', 'es')
        section_map_json: Structured section map with headings and content ranges
        document_metadata: Additional JSON metadata
    """
    
    __tablename__ = "document_artifacts"
    
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    file_type = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    document_type = Column(String, nullable=True)
    
    # Enhanced text processing fields
    raw_text = Column(Text, nullable=True)  # Raw extracted text (before normalization)
    document_text = Column(Text, nullable=True)  # Normalized text (after processing)
    word_count = Column(Integer, nullable=True)
    detected_language = Column(String(10), nullable=True)
    section_map_json = Column(JSONB, nullable=True)  # Section map with headings + heuristics
    
    # Note: renamed from 'metadata' to avoid SQLAlchemy reserved keyword
    document_metadata = Column(JSONB, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="document_artifacts")
    baseline = relationship("Baseline", back_populates="document_artifact")
