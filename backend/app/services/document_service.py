"""Document service for handling document uploads and storage."""
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.document_artifact import DocumentArtifact
from app.models.user import User
from app.utils.file_utils import (
    generate_unique_filename,
    save_upload_file,
    validate_file_type,
    get_file_size,
)
from app.utils.text_extractor import extract_text, TextExtractionError
from app.utils.text_processor import TextProcessor


class DocumentServiceError(Exception):
    """Base exception for document service errors."""
    pass


class UnsupportedFileTypeError(DocumentServiceError):
    """Raised when file type is not supported."""
    pass


class DocumentService:
    """
    Service for handling document uploads and text extraction.
    
    Supports PDF and DOCX file formats.
    Extracts raw text and stores as DocumentArtifact.
    """
    
    ALLOWED_TYPES = [".pdf", ".docx"]
    
    def __init__(self, db: Session):
        """
        Initialize document service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def upload_document(
        self,
        user_id: UUID,
        file_content: bytes,
        filename: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> UUID:
        """
        Upload and process a document (PDF/DOCX).
        
        Processing pipeline:
        1. Validate file type (PDF/DOCX)
        2. Extract raw text from document
        3. Normalize text (remove headers, footers, noise)
        4. Detect language
        5. Generate section_map using headings + heuristics
        6. Save file to storage
        7. Persist: raw_text, normalized_text, section_map_json
        8. Return document ID
        
        No intelligence logic - pure text processing and heuristics.
        
        Args:
            user_id: ID of the user uploading the document
            file_content: File content as bytes
            filename: Original filename
            title: Document title (defaults to filename if not provided)
            description: Document description
            document_type: Type of document (proposal, paper, report, etc.)
            
        Returns:
            UUID of the created DocumentArtifact
            
        Raises:
            UnsupportedFileTypeError: If file type is not supported
            DocumentServiceError: If processing fails
        """
        # Validate file type
        if not validate_file_type(filename, self.ALLOWED_TYPES):
            raise UnsupportedFileTypeError(
                f"File type not supported. Allowed types: {', '.join(self.ALLOWED_TYPES)}"
            )
        
        # Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise DocumentServiceError(f"User with ID {user_id} not found")
        
        # Extract file information
        unique_filename, file_extension = generate_unique_filename(filename)
        file_size = get_file_size(file_content)
        
        # Extract raw text from document (PDF/DOCX)
        try:
            raw_text = extract_text(file_content, file_extension)
        except TextExtractionError as e:
            raise DocumentServiceError(f"Text extraction failed: {str(e)}")
        
        # Normalize text (remove headers, footers, noise)
        normalized_text = TextProcessor.normalize_text(raw_text)
        
        # Detect language
        detected_language = TextProcessor.detect_language(normalized_text)
        
        # Generate section_map using headings + heuristics
        section_map = TextProcessor.generate_section_map(normalized_text)
        
        # Count words from normalized text
        word_count = TextProcessor.count_words(normalized_text)
        
        # Save file to storage
        try:
            file_path = save_upload_file(file_content, unique_filename)
        except Exception as e:
            raise DocumentServiceError(f"File storage failed: {str(e)}")
        
        # Create DocumentArtifact record
        # Persist: raw_text, normalized_text (as document_text), section_map_json
        document_artifact = DocumentArtifact(
            user_id=user_id,
            title=title or filename,
            description=description,
            file_type=file_extension.replace(".", ""),
            file_path=file_path,
            file_size_bytes=file_size,
            document_type=document_type,
            raw_text=raw_text,  # Raw extracted text
            document_text=normalized_text,  # Normalized text
            word_count=word_count,
            detected_language=detected_language,
            section_map_json=section_map,  # Section map with headings + heuristics
            document_metadata={
                "original_filename": filename,
                "processing_timestamp": str(self.db.execute("SELECT NOW()").scalar())
            }
        )
        
        self.db.add(document_artifact)
        self.db.commit()
        self.db.refresh(document_artifact)
        
        return document_artifact.id
    
    def get_document(self, document_id: UUID) -> Optional[DocumentArtifact]:
        """
        Get a document by ID.
        
        Args:
            document_id: Document ID
            
        Returns:
            DocumentArtifact or None if not found
        """
        return self.db.query(DocumentArtifact).filter(
            DocumentArtifact.id == document_id
        ).first()
    
    def get_user_documents(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100
    ) -> list[DocumentArtifact]:
        """
        Get all documents for a user.
        
        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of DocumentArtifacts
        """
        return self.db.query(DocumentArtifact).filter(
            DocumentArtifact.user_id == user_id
        ).offset(skip).limit(limit).all()
    
    def get_extracted_text(self, document_id: UUID) -> Optional[str]:
        """
        Get normalized extracted text from a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Normalized document text or None if document not found
        """
        document = self.get_document(document_id)
        if document:
            return document.document_text
        return None
    
    def get_raw_text(self, document_id: UUID) -> Optional[str]:
        """
        Get raw extracted text from a document (before normalization).
        
        Args:
            document_id: Document ID
            
        Returns:
            Raw document text or None if document not found
        """
        document = self.get_document(document_id)
        if document:
            return document.raw_text
        return None
    
    def get_section_map(self, document_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get section map from a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Section map dictionary or None if document not found
        """
        document = self.get_document(document_id)
        if document:
            return document.section_map_json
        return None
    
    def get_document_metadata(self, document_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive document metadata.
        
        Args:
            document_id: Document ID
            
        Returns:
            Dictionary with all document metadata
        """
        document = self.get_document(document_id)
        if not document:
            return None
        
        return {
            "id": str(document.id),
            "title": document.title,
            "description": document.description,
            "file_type": document.file_type,
            "file_size_bytes": document.file_size_bytes,
            "document_type": document.document_type,
            "word_count": document.word_count,
            "detected_language": document.detected_language,
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "has_section_map": document.section_map_json is not None,
            "section_count": document.section_map_json.get("total_sections", 0) if document.section_map_json else 0,
        }
    
    def delete_document(self, document_id: UUID) -> bool:
        """
        Delete a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            True if deleted, False if not found
        """
        document = self.get_document(document_id)
        if document:
            self.db.delete(document)
            self.db.commit()
            return True
        return False
