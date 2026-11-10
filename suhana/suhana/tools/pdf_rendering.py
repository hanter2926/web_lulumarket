from .rust_engine import (
    ENGINE_TIMEOUT_SECONDS,
    ProcessingEngineError,
    ProcessingInputError,
    compare_pdf,
    inspect_pdf,
)


PDF_MAX_PAGES = 100
PDF_DEFAULT_DPI = 120
PDF_MAX_DPI = 150
PDF_SOFT_TIMEOUT_SECONDS = ENGINE_TIMEOUT_SECONDS


class PdfRenderingError(ValueError):
    """A PDF cannot be safely inspected or rendered within the configured limits."""


class PdfWorkerError(PdfRenderingError, ProcessingEngineError):
    pass


class PDFRenderer:
    def compare(self, first_bytes, second_bytes):
        raise NotImplementedError

    def inspect(self, data):
        raise NotImplementedError


class PdfiumRenderer(PDFRenderer):
    def __init__(self, dpi=PDF_DEFAULT_DPI):
        if dpi <= 0 or dpi > PDF_MAX_DPI:
            raise PdfRenderingError(
                f"PDF rendering DPI must be between 1 and {PDF_MAX_DPI}."
            )
        self.dpi = dpi

    def inspect(self, data):
        try:
            result, _ = inspect_pdf(data, dpi=self.dpi)
        except ProcessingInputError as error:
            raise PdfRenderingError(str(error)) from error
        except ProcessingEngineError as error:
            raise PdfWorkerError(str(error)) from error
        return result

    def compare(self, first_bytes, second_bytes):
        try:
            result, _ = compare_pdf(first_bytes, second_bytes, dpi=self.dpi)
        except ProcessingInputError as error:
            raise PdfRenderingError(str(error)) from error
        except ProcessingEngineError as error:
            raise PdfWorkerError(str(error)) from error
        return result


class IsolatedPdfRendererClient(PdfiumRenderer):
    def __init__(self, timeout_seconds=PDF_SOFT_TIMEOUT_SECONDS, dpi=PDF_DEFAULT_DPI):
        super().__init__(dpi=dpi)
        self.timeout_seconds = timeout_seconds
        self.last_worker_pid = None

    def inspect(self, data):
        try:
            result, self.last_worker_pid = inspect_pdf(
                data,
                dpi=self.dpi,
                timeout_seconds=self.timeout_seconds,
            )
        except ProcessingInputError as error:
            raise PdfRenderingError(str(error)) from error
        except ProcessingEngineError as error:
            raise PdfWorkerError(str(error)) from error
        return result

    def compare(self, first_bytes, second_bytes):
        try:
            result, self.last_worker_pid = compare_pdf(
                first_bytes,
                second_bytes,
                dpi=self.dpi,
                timeout_seconds=self.timeout_seconds,
            )
        except ProcessingInputError as error:
            raise PdfRenderingError(str(error)) from error
        except ProcessingEngineError as error:
            raise PdfWorkerError(str(error)) from error
        return result
