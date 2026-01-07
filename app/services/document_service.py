import re
import pymupdf
import pytesseract
from PIL import Image
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, cast


from app.config.settings import settings
from app.schemas.citi_cert_schemas import DocExtractionResult, PyMuPDFMetadata


class DocumentService:
    """Service for extracting text and metadata from submitted documents. Currently supports only PDF files."""

    def __init__(self):
        self.supported_extensions = {"pdf"}
        self.tesseract_config = r"--oem 1 --psm 3"

    async def extract_text(
        self, file_content: bytes, filename: str
    ) -> DocExtractionResult:
        """Extract text from file content asynchronously."""
        file_extension = Path(filename).suffix.lower().lstrip(".")

        try:
            if file_extension not in self.supported_extensions:
                raise Exception(f"Unsupported file format .{file_extension}")
            else:
                # First try PyMuPDF extraction
                result = await self._extract_with_pymupdf(file_content)
                if result.text and len(result.text.strip()) > 50:
                    return result
                else:
                    # Fallback to Tesseract OCR extraction
                    result = await self._extract_with_tesseract(file_content)
                    return result
        except Exception as e:
            raise Exception(str(e))

    def _clean_text(self, text: str) -> str:
        """Clean and normalize the OCR text."""
        # Remove extra whitespace and normalize line breaks
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n+", "\n", text)
        return text.strip()

    async def _extract_with_pymupdf(self, pdf_data: bytes) -> DocExtractionResult:
        """Extract text using PyMuPDF from digital PDFs."""

        try:
            doc = pymupdf.open(stream=pdf_data, filetype="pdf")
            metadata = PyMuPDFMetadata(**cast(Dict[str, Any], doc.metadata))
            all_text = []
            page_count = len(doc)

            for page_num in range(page_count):
                page = doc.load_page(page_num)
                text = page.get_textpage().extractTEXT()
                if text.strip():
                    all_text.append(text.strip())

            full_text = "\n\n".join(all_text)
            full_text = self._clean_text(full_text)
            doc.close()

            return DocExtractionResult(
                method="pymupdf",
                pages=page_count,
                text=full_text,
                confidence=99.00 if full_text.strip() else 0.00,
                metadata=metadata,
            )

        except Exception as e:
            raise Exception(str(e))

    async def _extract_with_tesseract(self, file_data: bytes) -> DocExtractionResult:
        """Extract text using Tesseract OCR from scanned PDFs."""

        try:
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

            doc = pymupdf.open(stream=file_data, filetype="pdf")
            metadata = PyMuPDFMetadata(**cast(Dict[str, Any], doc.metadata))
            pdf_page = doc.load_page(0)
            pixmap = pdf_page.get_pixmap(dpi=300)  # type: ignore
            pixmap = pymupdf.Pixmap(pixmap, 0) if pixmap.alpha else pixmap

            img_data = pixmap.pil_tobytes(format="png")
            pil_img_data = Image.open(BytesIO(img_data))
            doc.close()
            pdf_page = None  # Free memory
            pixmap = None  # Free memory

            # Get OCR results as a DataFrame
            df = pytesseract.image_to_data(
                pil_img_data,
                output_type=pytesseract.Output.DATAFRAME,
                config=self.tesseract_config,
            )
            df = df.loc[df["conf"] > 70, ["text", "conf"]]
            text = " ".join(df["text"].fillna("").str.strip())
            confidence = df["conf"].mean()

            return DocExtractionResult(
                method="tesseract",
                pages=1,
                text=self._clean_text(text),
                confidence=float(confidence.round(2)),
                metadata=metadata,
            )

        except Exception as e:
            raise Exception(str(e))


def get_document_service() -> DocumentService:
    """Dependency to get Document service instance."""
    return DocumentService()
