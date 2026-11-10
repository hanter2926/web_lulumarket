import importlib.util
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

from .process_runner import (
    ProcessCancelledError,
    ProcessLimitError,
    ProcessTimeoutError,
    run_limited_process,
)


ENGINE_TIMEOUT_SECONDS = 20
ENGINE_PROCESS_LIMIT = 2
_PROCESS_SLOTS = threading.BoundedSemaphore(ENGINE_PROCESS_LIMIT)
_CANCEL_CHECK = threading.local()


class ProcessingEngineError(RuntimeError):
    pass


class ProcessingInputError(ValueError):
    pass


class ProcessingCancelledError(ProcessingEngineError):
    pass


@contextmanager
def cancellation_check(check):
    previous = getattr(_CANCEL_CHECK, "check", None)
    _CANCEL_CHECK.check = check
    try:
        yield
    finally:
        _CANCEL_CHECK.check = previous


def _engine_path():
    configured = os.environ.get("SUHANA_IMAGE_ENGINE")
    if configured:
        return Path(configured).expanduser().resolve()

    binary_name = "suhana-image-engine.exe" if os.name == "nt" else "suhana-image-engine"
    return Path(__file__).resolve().parent / "rust-engine" / "target" / "release" / binary_name


def _pdfium_library_path():
    configured = os.environ.get("SUHANA_PDFIUM_LIBRARY")
    if configured:
        return Path(configured).expanduser().resolve()

    module_spec = importlib.util.find_spec("pypdfium2_raw")
    if module_spec is None or module_spec.submodule_search_locations is None:
        raise ProcessingEngineError(
            "The PDFium runtime is unavailable. Install pypdfium2 or set SUHANA_PDFIUM_LIBRARY."
        )
    library_name = {
        "nt": "pdfium.dll",
        "posix": "libpdfium.so",
    }.get(os.name)
    if library_name is None:
        raise ProcessingEngineError(
            "Set SUHANA_PDFIUM_LIBRARY to the installed PDFium runtime."
        )
    library_path = Path(next(iter(module_spec.submodule_search_locations))) / library_name
    if not library_path.is_file():
        raise ProcessingEngineError(
            "The PDFium runtime is unavailable. Set SUHANA_PDFIUM_LIBRARY explicitly."
        )
    return library_path


def _run(
    operation,
    first_data,
    second_data=None,
    timeout_seconds=ENGINE_TIMEOUT_SECONDS,
    engine_args=(),
    output_file=False,
):
    if not _PROCESS_SLOTS.acquire(timeout=timeout_seconds):
        raise ProcessingEngineError("Processing capacity is currently exhausted.")
    try:
        executable = _engine_path()
        if not executable.is_file():
            raise ProcessingEngineError(
                "The Rust processing engine is not built or configured. "
                "Build tools/rust-engine or set SUHANA_IMAGE_ENGINE."
            )

        with tempfile.TemporaryDirectory(prefix="suhana-processing-") as directory:
            job_directory = Path(directory)
            command = [str(executable), operation]
            if operation.startswith("pdf-"):
                command.append(str(_pdfium_library_path()))
            command.extend(engine_args)
            first_path = job_directory / "first"
            first_path.write_bytes(first_data)
            command.append(str(first_path))
            if second_data is not None:
                second_path = job_directory / "second"
                second_path.write_bytes(second_data)
                command.append(str(second_path))
            output_path = None
            if output_file:
                output_path = job_directory / "output"
                command.append(str(output_path))

            try:
                process = run_limited_process(
                    command,
                    cwd=Path(__file__).resolve().parents[1],
                    timeout_seconds=timeout_seconds,
                    cancel_check=getattr(_CANCEL_CHECK, "check", None),
                )
            except ProcessCancelledError as error:
                raise ProcessingCancelledError(
                    "The processing job was cancelled."
                ) from error
            except ProcessTimeoutError as error:
                if operation.startswith("pdf-"):
                    raise ProcessingEngineError(
                        "PDF comparison exceeded the hard worker timeout."
                    ) from error
                raise ProcessingEngineError(
                    "Image processing exceeded the 20-second worker timeout."
                ) from error
            except ProcessLimitError as error:
                raise ProcessingEngineError(str(error)) from error
            except OSError as error:
                raise ProcessingEngineError(
                    "The Rust processing engine could not be started."
                ) from error

            if process.returncode != 0:
                message = process.stderr.strip()
                if message and (
                    "uploaded image" in message
                    or "image dimensions" in message
                    or "decoded pixel" in message
                    or "image pair" in message
                    or "25 MB" in message
                    or "100 frames" in message
                    or "image format" in message
                    or "uploaded file is not a valid PDF" in message
                    or "PDF is malformed" in message
                    or "PDFs may contain" in message
                    or "PDF page" in message
                    or "PDF exceeds" in message
                    or "PDF pair" in message
                    or "compression" in message.lower()
                    or "compressed" in message.lower()
                    or "optimized image" in message.lower()
                    or "unsupported" in message.lower()
                    or "animated" in message.lower()
                ):
                    raise ProcessingInputError(message)
                raise ProcessingEngineError("The isolated Rust processing engine failed.")

            try:
                result = json.loads(process.stdout)
            except json.JSONDecodeError as error:
                raise ProcessingEngineError(
                    "The Rust processing engine returned invalid output."
                ) from error
            if not isinstance(result, dict):
                raise ProcessingEngineError("The Rust processing engine returned invalid output.")
            if output_path is not None:
                try:
                    result["output_data"] = output_path.read_bytes()
                except OSError as error:
                    raise ProcessingEngineError(
                        "The Rust processing engine did not produce an output file."
                    ) from error
                if not result["output_data"]:
                    raise ProcessingEngineError(
                        "The Rust processing engine produced an empty output file."
                    )
            return result, process.pid
    finally:
        _PROCESS_SLOTS.release()


def inspect_image(data):
    result, _ = _run("inspect", data)
    return result


def compare_image_pair(first_data, second_data):
    result, _ = _run("compare", first_data, second_data)
    try:
        first_metadata = result.pop("first")
        second_metadata = result.pop("second")
    except KeyError as error:
        raise ProcessingEngineError(
            "The Rust processing engine returned incomplete image output."
        ) from error
    return result, first_metadata, second_metadata


def inspect_pdf(data, dpi=120, timeout_seconds=ENGINE_TIMEOUT_SECONDS):
    result, process_id = _run(
        "pdf-inspect",
        data,
        timeout_seconds=timeout_seconds,
        engine_args=(str(dpi),),
    )
    return result, process_id


def compare_pdf(
    first_data,
    second_data,
    dpi=120,
    timeout_seconds=ENGINE_TIMEOUT_SECONDS,
):
    return _run(
        "pdf-compare",
        first_data,
        second_data,
        timeout_seconds=timeout_seconds,
        engine_args=(str(dpi),),
    )


def _compression_result(data, result):
    output = result.pop("output_data", None)
    if (
        not isinstance(output, bytes)
        or result.get("input_bytes") != len(data)
        or result.get("output_bytes") != len(output)
    ):
        raise ProcessingEngineError(
            "The Rust processing engine returned invalid compression output."
        )
    return result, output


def compress_image(data):
    result, _ = _run("compress-image", data, output_file=True)
    return _compression_result(data, result)


def compress_pdf(data, timeout_seconds=ENGINE_TIMEOUT_SECONDS):
    result, _ = _run(
        "pdf-compress",
        data,
        timeout_seconds=timeout_seconds,
        output_file=True,
    )
    return _compression_result(data, result)
