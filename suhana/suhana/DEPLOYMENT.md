# Deployment checklist

## Build and configuration

1. Create a Python 3.14 environment and install `requirements.txt`. Install `requirements-dev.txt` when running the test suite.
2. Install Rust 1.88 or newer with the target matching the deployment OS and architecture. The current development toolchain is rustc/cargo 1.99.1 on `x86_64-pc-windows-msvc`; only that Windows target is installed in this development environment. CI and production should build from `Cargo.lock`.
3. Build the isolated processing engine from the project root:

   ```powershell
   cargo build --manifest-path tools/rust-engine/Cargo.toml --release --locked
   ```

   Use the same command in Linux shells. The default executable is `tools/rust-engine/target/release/suhana-image-engine.exe` on Windows and `tools/rust-engine/target/release/suhana-image-engine` on Linux. Set `SUHANA_IMAGE_ENGINE` when the executable is installed elsewhere.
4. The Rust PDF integration loads the PDFium native library distributed with `pypdfium2`. Set `SUHANA_PDFIUM_LIBRARY` to the full library path only when automatic discovery is not suitable (`pdfium.dll` on Windows, `libpdfium.so` on Linux). Retain the native distribution’s license files as described in `THIRD_PARTY_NOTICES.md`.
5. Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and all `MYSQL_*` variables. Configure `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` for the Gmail SMTP account, and optionally set `EMAIL_TIMEOUT` (seconds; defaults to 10). SMTP is configured for STARTTLS on port 587, with implicit SSL disabled.
6. Set `PROCESSING_JOB_ROOT` to a dedicated private temporary directory when the operating system’s default temp directory is not private to the application account. The default is a `suhana-processing-jobs` directory under the OS temp directory. POSIX permissions are restricted to the service account; on Windows, use a service account whose temp directory ACL is private.
7. Set `DJANGO_SECURE_SSL_REDIRECT=true` only when the reverse proxy terminates HTTPS and forwards the correct protocol.

## Database and worker

Run `python manage.py check --deploy` before releasing. Migrations `tools.0002_comparisonqueuecontrol_comparisonjob` and `tools.0003_comparisonjob_job_type` create the async job queue and distinguish comparison from compression jobs. Apply them only after explicit database-change approval and during an approved deployment window. Do not reset the database or remove existing migrations.

After the migration is approved and applied, run the worker under a process supervisor, separately from Django web workers:

```text
python manage.py run_comparison_worker --workers 2
```

Use a Windows service manager or Task Scheduler on Windows and systemd or a container orchestrator on Linux. Configure the supervisor to restart a failed worker and to stop it cleanly. The database queue lock enforces a global maximum of two concurrent jobs across worker processes; the queue admits at most 100 active jobs, with at most three active jobs per authenticated user or anonymous requester. Do not run `--once` in production; it is intended for tests and controlled operations.

The worker claims comparison and compression jobs from the database, stages uploads and validated compression outputs outside `MEDIA_ROOT`, and launches one Rust process per operation. Each child has a 20-second wall timeout, 25-second CPU-time limit, 512 MiB memory limit, and one-process limit. Windows uses Job Objects; POSIX uses CPU/address-space limits and a separate process group. Cancellation terminates the child process or process group. Deploy on a supported Windows or POSIX host; unsupported platforms fail closed rather than processing in-process. Additional service/container limits are recommended as defense in depth.

The upload and decoder limits are deliberately strict: 25 MiB per file; images up to 8,192 pixels per dimension, 100 animation frames, 20 million decoded pixels per image and 40 million per pair; PDFs up to 100 pages and 150 DPI, 20 million pixels per page, 80 million per document and 160 million combined. The default PDF render resolution is 120 DPI. Limits may reject files accepted by the former Python implementation.

Comparison submission keeps the existing `POST /api/tools/compare/` path but now returns HTTP 202 with a job ID and capability token. Compression is submitted as `POST /api/tools/compress/` using the `file` multipart field; it uses the same queue, status, cancellation, and capability-token rules. Its download URL requires the same job token and serves only output validated by the Rust worker. Temporary compression files are removed by the one-day job cleanup.

Image compression can preserve the input format or convert between the supported output formats exposed by the UI. JPEG quality is configurable; PNG and WEBP use lossless encoding, and GIF animation is retained when using its animation-preserving option. Animated PNG and animated WEBP are explicitly rejected. PDF stream compression preserves pages and is validated by PDFium before a job can complete. The API reports actual input/output byte counts; clients must treat output that is not smaller as a valid result with no size reduction, not as a claimed optimization. The frontend implements progress polling, cancellation, output validation, and downloading.

The storage API enforces user ownership, a 25 MiB per-file limit, and the configured storage quota; it supports nested folders, file rename and move, authenticated downloads, and deletion. The dashboard aggregates current storage usage, recent files, and saved comparison/compression activity. Comparison reports and successful compression records are available in account history; private processing records and output files expire after one day. Image analysis is performed locally in the browser and is not saved to account history. The unit-conversion endpoint accepts an optional `standard` value of `decimal` or `binary` (default `decimal`).

## Web server and cleanup

Serve static files through the web server or object storage. Do not expose `MEDIA_ROOT` or `PROCESSING_JOB_ROOT` publicly. Terminal job records and private staged files expire after one day; the worker periodically removes expired records and orphaned job directories. Monitor worker logs as well as `GET /health/`. A healthy response is `{"status":"ok","database":"ok"}`; database failure returns HTTP 503.

Run the application behind a production WSGI/ASGI server and reverse proxy. Do not deploy until the Linux release binary, PDFium discovery, OS limits, and service configuration have been tested on the actual production image.
