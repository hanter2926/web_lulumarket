use std::env;
use std::fs;
use std::path::Path;

use pdfium_render::prelude::*;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let [_, library_path, pdf_path] = args.as_slice() else {
        return Err("Usage: pdf_benchmark <pdfium-library> <pdf-file>".into());
    };

    let bindings = Pdfium::bind_to_library(Path::new(library_path))?;
    let pdfium = Pdfium::new(bindings);
    let pdf = fs::read(pdf_path)?;
    let document = pdfium.load_pdf_from_byte_slice(&pdf, None)?;
    let dpi = 120.0_f32;
    let mut total_difference = 0_u64;
    let mut text = String::new();

    for page in document.pages().iter() {
        let width = (page.width().value * dpi / 72.0).round() as i32;
        let height = (page.height().value * dpi / 72.0).round() as i32;
        text.push_str(&page.text()?.all());
        let config = PdfRenderConfig::new().set_fixed_size(width, height);
        let first = page.render_with_config(&config)?.as_image()?.into_rgba8();
        let second = page.render_with_config(&config)?.as_image()?.into_rgba8();
        total_difference += first
            .pixels()
            .zip(second.pixels())
            .filter(|(left, right)| left != right)
            .count() as u64;
    }

    let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
    println!(
        "pages={} text={} differences={}",
        document.pages().len(),
        text,
        total_difference
    );
    Ok(())
}
