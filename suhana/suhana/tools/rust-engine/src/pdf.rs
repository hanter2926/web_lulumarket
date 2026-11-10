use std::fs;
use std::path::Path;
use std::time::{Duration, Instant};

use base64::Engine;
use image::{DynamicImage, ImageFormat, RgbaImage};
use pdfium_render::prelude::*;
use serde_json::{Value, json};

const MAX_FILE_BYTES: u64 = 25 * 1024 * 1024;
const MAX_PAGES: usize = 100;
const MAX_DPI: f32 = 150.0;
const MAX_PAGE_DIMENSION: u32 = 8_192;
const MAX_PAGE_PIXELS: u64 = 20_000_000;
const MAX_PIXELS_PER_DOCUMENT: u64 = 80_000_000;
const MAX_COMBINED_PIXELS: u64 = 160_000_000;
const MAX_OVERLAY_BYTES: usize = 1_000_000;
const MAX_TOTAL_OVERLAY_BYTES: usize = 5_000_000;
const PROCESSING_BUDGET: Duration = Duration::from_secs(20);

struct PageInfo {
    index: usize,
    text: String,
    width: u32,
    height: u32,
}

fn normalize_text(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn read_pdf(path: &Path) -> Result<Vec<u8>, String> {
    let metadata = fs::metadata(path).map_err(|_| "The PDF could not be read.")?;
    if metadata.len() > MAX_FILE_BYTES {
        return Err("Each comparison file must be 25 MB or smaller.".to_owned());
    }
    let bytes = fs::read(path).map_err(|_| "The PDF could not be read.")?;
    if !bytes.starts_with(b"%PDF-") {
        return Err("The uploaded file is not a valid PDF.".to_owned());
    }
    Ok(bytes)
}

fn bind_pdfium(library_path: &Path) -> Result<Pdfium, String> {
    let bindings = Pdfium::bind_to_library(library_path)
        .map_err(|_| "The PDFium library could not be loaded.")?;
    Ok(Pdfium::new(bindings))
}

fn open_document<'a>(pdfium: &'a Pdfium, bytes: &'a [u8]) -> Result<PdfDocument<'a>, String> {
    pdfium
        .load_pdf_from_byte_slice(bytes, None)
        .map_err(|_| "The PDF is malformed, encrypted, or unsupported.".to_owned())
}

fn inspect_document(
    document: &PdfDocument<'_>,
    started: Instant,
    dpi: f32,
) -> Result<(Vec<PageInfo>, bool, u64), String> {
    let page_count = document.pages().len() as usize;
    if page_count > MAX_PAGES {
        return Err(format!("PDFs may contain at most {MAX_PAGES} pages."));
    }

    let mut pages = Vec::with_capacity(page_count);
    let mut total_pixels = 0u64;
    let mut has_text = false;
    for (index, page) in document.pages().iter().enumerate() {
        if started.elapsed() > PROCESSING_BUDGET {
            return Err("PDF comparison exceeded the 20-second processing budget.".to_owned());
        }
        let width_points = page.width().value;
        let height_points = page.height().value;
        if !width_points.is_finite() || !height_points.is_finite() {
            return Err("A PDF page has invalid dimensions.".to_owned());
        }
        let width = (width_points * dpi / 72.0).round().max(1.0) as u32;
        let height = (height_points * dpi / 72.0).round().max(1.0) as u32;
        let page_pixels = u64::from(width) * u64::from(height);
        if width > MAX_PAGE_DIMENSION
            || height > MAX_PAGE_DIMENSION
            || page_pixels > MAX_PAGE_PIXELS
        {
            return Err("A PDF page exceeds the maximum rendered dimensions.".to_owned());
        }
        total_pixels = total_pixels
            .checked_add(page_pixels)
            .ok_or_else(|| "A PDF exceeds the rendered pixel budget.".to_owned())?;
        if total_pixels > MAX_PIXELS_PER_DOCUMENT {
            return Err("A PDF exceeds the rendered pixel budget.".to_owned());
        }
        let text = normalize_text(
            &page
                .text()
                .map_err(|_| "The PDF text layer could not be read.")?
                .all(),
        );
        has_text |= !text.is_empty();
        pages.push(PageInfo {
            index: index + 1,
            text,
            width,
            height,
        });
    }
    Ok((pages, has_text, total_pixels))
}

fn render_page(
    document: &PdfDocument<'_>,
    index: usize,
    width: u32,
    height: u32,
) -> Result<RgbaImage, String> {
    let page = document
        .pages()
        .get(index as i32)
        .map_err(|_| "A PDF page could not be opened.")?;
    let bitmap = page
        .render_with_config(&PdfRenderConfig::new().set_fixed_size(width as i32, height as i32))
        .map_err(|_| "A PDF page could not be rendered.")?;
    bitmap
        .as_image()
        .map(|image| image.into_rgba8())
        .map_err(|_| "A PDF page could not be rendered.".to_owned())
}

fn overlay_data_url(
    width: u32,
    height: u32,
    changed: &[u8],
    max_bytes: usize,
) -> Option<(String, usize)> {
    let mut pixels = Vec::with_capacity(changed.len() * 4);
    for pixel_changed in changed {
        pixels.extend_from_slice(if *pixel_changed != 0 {
            &[255, 0, 0, 180]
        } else {
            &[0, 0, 0, 0]
        });
    }
    let overlay = RgbaImage::from_raw(width, height, pixels)?;
    let mut output = std::io::Cursor::new(Vec::new());
    DynamicImage::ImageRgba8(overlay)
        .write_to(&mut output, ImageFormat::Png)
        .ok()?;
    let bytes = output.into_inner();
    if bytes.len() > max_bytes.min(MAX_OVERLAY_BYTES) {
        return None;
    }
    let size = bytes.len();
    Some((
        format!(
            "data:image/png;base64,{}",
            base64::engine::general_purpose::STANDARD.encode(bytes)
        ),
        size,
    ))
}

fn compare_page(first: &RgbaImage, second: &RgbaImage, preview_budget: usize) -> (Value, usize) {
    if first.dimensions() != second.dimensions() {
        return (
            json!({
                "same_dimensions": false,
                "differing_pixels": null,
                "difference_percentage": 100.0,
                "bounding_box": null,
                "overlay_png": null
            }),
            0,
        );
    }

    let mut changed = Vec::with_capacity((first.width() * first.height()) as usize);
    let mut differing_pixels = 0u64;
    let mut min_x = first.width();
    let mut min_y = first.height();
    let mut max_x = None;
    let mut max_y = None;
    for (index, (left, right)) in first.pixels().zip(second.pixels()).enumerate() {
        let different = left != right;
        changed.push(u8::from(different));
        if different {
            differing_pixels += 1;
            let x = index as u32 % first.width();
            let y = index as u32 / first.width();
            min_x = min_x.min(x);
            min_y = min_y.min(y);
            max_x = Some(max_x.map_or(x, |current: u32| current.max(x)));
            max_y = Some(max_y.map_or(y, |current: u32| current.max(y)));
        }
    }

    let total_pixels = u64::from(first.width()) * u64::from(first.height());
    let (overlay_png, preview_size) =
        overlay_data_url(first.width(), first.height(), &changed, preview_budget)
            .map(|(data_url, size)| (Some(data_url), size))
            .unwrap_or((None, 0));
    let bounding_box = match (max_x, max_y) {
        (Some(right), Some(bottom)) => json!({
            "left": min_x,
            "top": min_y,
            "right": right,
            "bottom": bottom
        }),
        _ => Value::Null,
    };

    (
        json!({
            "same_dimensions": true,
            "differing_pixels": differing_pixels,
            "difference_percentage": ((differing_pixels as f64 * 100.0 / total_pixels as f64) * 1_000_000.0).round() / 1_000_000.0,
            "bounding_box": bounding_box,
            "overlay_png": overlay_png
        }),
        preview_size,
    )
}

fn validate_dpi(dpi: f32) -> Result<(), String> {
    if !dpi.is_finite() || dpi <= 0.0 || dpi > MAX_DPI {
        return Err(format!(
            "PDF rendering DPI must be between 1 and {MAX_DPI:.0}."
        ));
    }
    Ok(())
}

pub fn inspect(library_path: &Path, pdf_path: &Path, dpi: f32) -> Result<Value, String> {
    validate_dpi(dpi)?;
    let started = Instant::now();
    let pdfium = bind_pdfium(library_path)?;
    let bytes = read_pdf(pdf_path)?;
    let document = open_document(&pdfium, &bytes)?;
    let (pages, has_text, _) = inspect_document(&document, started, dpi)?;
    Ok(json!({
        "page_count": pages.len(),
        "has_text": has_text,
        "pages": pages.iter().map(|page| json!({
            "index": page.index,
            "text": page.text,
            "width": page.width,
            "height": page.height
        })).collect::<Vec<_>>()
    }))
}

pub fn compare(
    library_path: &Path,
    dpi: f32,
    first_path: &Path,
    second_path: &Path,
) -> Result<Value, String> {
    validate_dpi(dpi)?;
    let started = Instant::now();
    let pdfium = bind_pdfium(library_path)?;
    let first_bytes = read_pdf(first_path)?;
    let second_bytes = read_pdf(second_path)?;
    let first_document = open_document(&pdfium, &first_bytes)?;
    let second_document = open_document(&pdfium, &second_bytes)?;
    let (first_pages, first_has_text, first_pixels) =
        inspect_document(&first_document, started, dpi)?;
    let (second_pages, second_has_text, second_pixels) =
        inspect_document(&second_document, started, dpi)?;
    if first_pixels + second_pixels > MAX_COMBINED_PIXELS {
        return Err("The PDF pair exceeds the combined rendered pixel budget.".to_owned());
    }

    let mut page_results = Vec::with_capacity(first_pages.len().max(second_pages.len()));
    let mut preview_bytes = 0;
    for index in 0..first_pages.len().min(second_pages.len()) {
        if started.elapsed() > PROCESSING_BUDGET {
            return Err("PDF comparison exceeded the 20-second processing budget.".to_owned());
        }
        let first = &first_pages[index];
        let second = &second_pages[index];
        let first_image = render_page(&first_document, index, first.width, first.height)?;
        let second_image = render_page(&second_document, index, second.width, second.height)?;
        let (visual, used) = compare_page(
            &first_image,
            &second_image,
            MAX_TOTAL_OVERLAY_BYTES - preview_bytes,
        );
        preview_bytes += used;
        page_results.push(json!({
            "page": index + 1,
            "text_same": first.text == second.text,
            "first_text": first.text,
            "second_text": second.text,
            "visual": visual
        }));
    }
    for page in first_pages.iter().skip(second_pages.len()) {
        page_results.push(json!({
            "page": page.index,
            "status": "removed",
            "text_same": false,
            "visual": null
        }));
    }
    for page in second_pages.iter().skip(first_pages.len()) {
        page_results.push(json!({
            "page": page.index,
            "status": "added",
            "text_same": false,
            "visual": null
        }));
    }

    Ok(json!({
        "renderer": "pdfium-render",
        "dpi": dpi,
        "first": {
            "page_count": first_pages.len(),
            "has_text_layer": first_has_text,
            "scanned_likely": !first_has_text
        },
        "second": {
            "page_count": second_pages.len(),
            "has_text_layer": second_has_text,
            "scanned_likely": !second_has_text
        },
        "page_results": page_results,
        "text_differences": page_results.iter().filter(|page| page["text_same"] == false).count(),
        "visual_differences": page_results.iter().filter(|page| {
            page["visual"].as_object().is_some_and(|visual| {
                visual["difference_percentage"].as_f64().unwrap_or(0.0) > 0.0
            })
        }).count(),
        "overlays_are_temporary": true
    }))
}

pub fn compress(
    library_path: &Path,
    input_path: &Path,
    output_path: &Path,
) -> Result<Value, String> {
    let started = Instant::now();
    let input = read_pdf(input_path)?;
    let pdfium = bind_pdfium(library_path)?;
    let source = open_document(&pdfium, &input)?;
    let page_count = source.pages().len() as usize;
    if page_count == 0 || page_count > MAX_PAGES {
        return Err(format!(
            "PDFs must contain between 1 and {MAX_PAGES} pages."
        ));
    }
    if !source.signatures().is_empty() {
        return Err(
            "Digitally signed PDFs cannot be compressed because rewriting invalidates signatures."
                .to_owned(),
        );
    }
    drop(source);

    let mut document = lopdf::Document::load_mem(&input)
        .map_err(|_| "The PDF is malformed, encrypted, or unsupported.".to_owned())?;
    if document.is_encrypted() {
        return Err("Password-protected PDFs cannot be compressed.".to_owned());
    }
    document.compress();
    let mut output = Vec::new();
    document
        .save_to(&mut output)
        .map_err(|_| "The PDF could not be optimized.".to_owned())?;
    if output.is_empty() || output.len() as u64 > MAX_FILE_BYTES {
        return Err("The optimized PDF exceeds the 25 MB output limit.".to_owned());
    }
    if started.elapsed() > PROCESSING_BUDGET {
        return Err("PDF compression exceeded the 20-second processing budget.".to_owned());
    }

    let optimized = open_document(&pdfium, &output)?;
    if optimized.pages().len() as usize != page_count {
        return Err("PDF optimization changed the page count.".to_owned());
    }
    fs::write(output_path, &output).map_err(|_| "The optimized PDF could not be saved.")?;
    Ok(json!({
        "input_bytes": input.len(),
        "output_bytes": output.len(),
        "page_count": page_count
    }))
}
