# Third-party notices

## Python distributions

| Distribution | Version | License | Use |
|---|---:|---|---|
| Django | 5.2.19 | BSD-3-Clause | Backend |
| mysqlclient | 2.3.0 | GPL-2.0 with the mysqlclient linking exception | MySQL driver |
| python-dotenv | 1.2.4 | BSD-3-Clause | Environment configuration |
| pypdfium2 | 5.15.2 | BSD-3-Clause bindings; includes PDFium and third-party notices | Supplies the PDFium native runtime loaded by Rust |
| Pillow | 13.0.0 | HPND-style Pillow license | Test-only image fixture generation (`requirements-dev.txt`) |

Retain the pypdfium2 license directory in deployed environments. In the Windows virtual environment it is:

```text
venv/Lib/site-packages/pypdfium2-5.15.2.dist-info/licenses/
```

The pypdfium2 distribution includes PDFium and conditional-platform third-party notices, including Apache-2.0, BSD-3-Clause, CC-BY-4.0, FreeType, HarfBuzz, ICU, JPEG, OpenJPEG, PNG, TIFF, Brotli, libyuv, zlib, and V8. Preserve and ship the license files supplied by the actual platform wheel rather than relying on this summary as a replacement.

## Rust crates

The direct Rust dependencies, pinned by `tools/rust-engine/Cargo.lock`, are:

| Crate | Version | Declared license |
|---|---:|---|
| base64 | 0.22.1 | MIT OR Apache-2.0 |
| image | 0.25.10 | MIT OR Apache-2.0 |
| pdfium-render | 0.9.5 | MIT OR Apache-2.0 |
| serde | 1.0.229 | MIT OR Apache-2.0 |
| serde_json | 1.0.154 | MIT OR Apache-2.0 |

The following inventory covers every registry crate in the locked Cargo metadata, including target-specific/transitive dependencies. License expressions are reproduced from each crate’s Cargo metadata; retain the corresponding crate license texts and notices when redistributing.

| Crate license expression | Locked crates (`name@version`) |
|---|---|
| (MIT OR Apache-2.0) AND Unicode-3.0 | unicode-ident@1.0.27 |
| 0BSD OR MIT OR Apache-2.0 | adler2@2.0.1 |
| Apache-2.0 OR MIT | autocfg@1.5.1, pin-project-lite@0.2.17 |
| Apache-2.0/MIT | console_error_panic_hook@0.1.7 |
| BSD-3-Clause OR Apache-2.0 | moxcms@0.8.1, pxfm@0.1.30 |
| ISC | libloading@0.9.0 |
| MIT | bytes@1.12.1, color_quant@1.1.0, piston-float@1.0.1, simd-adler32@0.3.10, slab@0.4.12, tokio@1.54.1, vecmath@1.0.0, zmij@1.0.23 |
| MIT OR Apache-2.0 | android_system_properties@0.1.6, base64@0.22.1, bitflags@2.13.2, bumpalo@3.20.3, cc@1.11.1, cfg-if@1.0.5, chrono@0.4.45, core-foundation-sys@0.8.7, crc32fast@1.5.4, either@1.19.0, fdeflate@0.3.7, find-msvc-tools@0.1.15, flate2@1.1.11, futures-core@0.3.34, futures-task@0.3.34, futures-util@0.3.34, gif@0.14.2, iana-time-zone@0.1.65, iana-time-zone-haiku@0.1.2, image@0.25.10, image-webp@0.2.4, itertools@0.15.0, itoa@1.0.19, js-sys@0.3.107, libc@0.2.191, log@0.4.35, maybe-owned@0.3.4, num-traits@0.2.19, once_cell@1.21.4, pdfium-render@0.9.5, png@0.18.1, proc-macro2@1.0.107, quote@1.0.47, rustversion@1.0.23, serde@1.0.229, serde_core@1.0.229, serde_derive@1.0.229, serde_json@1.0.154, shlex@2.0.1, syn@2.0.119, syn@3.0.10, utf16string@0.2.0, wasm-bindgen@0.2.130, wasm-bindgen-futures@0.4.80, wasm-bindgen-macro@0.2.130, wasm-bindgen-macro-support@0.2.130, wasm-bindgen-shared@0.2.130, web-sys@0.3.107, weezl@0.1.12, windows-core@0.62.2, windows-implement@0.60.2, windows-interface@0.59.3, windows-link@0.2.1, windows-result@0.4.1, windows-strings@0.5.1 |
| MIT OR Apache-2.0 OR Zlib | zune-core@0.5.3, zune-jpeg@0.5.15 |
| MIT OR Zlib OR Apache-2.0 | miniz_oxide@0.8.9, miniz_oxide@0.9.1 |
| MIT/Apache-2.0 | console_log@1.1.0, quick-error@2.0.1 |
| Unlicense OR MIT | byteorder@1.5.0, byteorder-lite@0.1.0, memchr@2.8.3 |
| Zlib | zlib-rs@0.6.8 |
| Zlib OR Apache-2.0 OR MIT | bytemuck@1.25.2 |

The exact versions and dependency graph are recorded in `tools/rust-engine/Cargo.lock`. PDFium is a native dependency supplied by pypdfium2, not a Cargo crate; its bundled notices remain applicable.
