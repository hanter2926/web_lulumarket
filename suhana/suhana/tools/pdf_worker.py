import json
import os
import sys
from pathlib import Path

from .pdf_rendering import PdfRenderingError, PdfiumRenderer


def _apply_resource_limits():
    try:
        import resource
    except ImportError:
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
        address_limit = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (address_limit, address_limit))
    except (OSError, ValueError):
        return


def main():
    if len(sys.argv) not in {4, 5}:
        return 2
    operation, first_name, output_name = sys.argv[1:4]
    first = Path(first_name).read_bytes()
    _apply_resource_limits()
    renderer = PdfiumRenderer()
    try:
        if operation == "inspect":
            result = renderer.inspect(first)
        elif operation == "compare" and len(sys.argv) == 5:
            result = renderer.compare(first, Path(sys.argv[4]).read_bytes())
        else:
            return 2
    except (OSError, PdfRenderingError) as error:
        Path(output_name).write_text(
            json.dumps({"error": str(error)}),
            encoding="utf-8",
        )
        return 1

    result["worker_pid"] = os.getpid()
    Path(output_name).write_text(json.dumps(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
