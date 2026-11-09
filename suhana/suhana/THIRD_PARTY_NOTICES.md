# Third-party notices

The backend uses these pinned distributions:

- Django 5.2.19: BSD 3-Clause
- mysqlclient 2.3.0: GNU General Public License with exception
- python-dotenv 1.2.4: BSD 3-Clause
- pypdfium2 5.15.2: BSD 3-Clause bindings and bundled PDFium notices
- Pillow 13.0.0: HPND-style Pillow license

The pypdfium2 Windows installation includes PDFium and dependency notices under:

`venv/Lib/site-packages/pypdfium2-5.15.2.dist-info/licenses/`

Those installed license files must be retained in deployed environments. The distribution includes PDFium, Apache-2.0, BSD-3-Clause, CC-BY-4.0, FreeType, HarfBuzz, ICU, JPEG, OpenJPEG, PNG, TIFF, Brotli, libyuv, zlib, V8 and other conditional-platform notices.
