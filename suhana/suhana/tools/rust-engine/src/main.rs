use std::env;
use std::fs;
use std::io::{BufReader, Cursor, Write};
use std::path::Path;
use std::process::ExitCode;

use base64::Engine;
use image::codecs::gif::GifDecoder;
use image::codecs::gif::GifEncoder;
use image::codecs::jpeg::JpegEncoder;
use image::codecs::png::{CompressionType, FilterType, PngDecoder, PngEncoder};
use image::codecs::webp::WebPDecoder;
use image::{
    AnimationDecoder, DynamicImage, Frame, ImageDecoder, ImageEncoder, ImageFormat, ImageReader,
    RgbaImage,
};
use serde::Serialize;

mod pdf;

const MAX_FILE_BYTES: u64 = 25 * 1024 * 1024;
const MAX_DIMENSION: u32 = 8_192;
const MAX_FRAME_PIXELS: u64 = 80_000_000;
const MAX_TOTAL_PIXELS_PER_FILE: u64 = 20_000_000;
const MAX_TOTAL_PIXELS_PER_PAIR: u64 = 40_000_000;
const MAX_FRAMES: usize = 100;
const MAX_PREVIEW_BYTES: usize = 1_000_000;
const MAX_TOTAL_PREVIEW_BYTES: usize = 5_000_000;

#[derive(Debug)]
struct EngineError(String);

impl std::fmt::Display for EngineError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for EngineError {}

#[derive(Serialize)]
struct Metadata {
    dimensions: [u32; 2],
    format: &'static str,
    animated: bool,
    frame_count: usize,
    has_alpha: bool,
}

#[derive(Serialize)]
struct ImageComparison {
    first: Metadata,
    second: Metadata,
    first_format: &'static str,
    second_format: &'static str,
    animated: bool,
    frame_count_difference: isize,
    frame_results: Vec<FrameResult>,
    visual_differences: usize,
    same_visual: bool,
}

#[derive(Serialize)]
struct FrameResult {
    frame: usize,
    status: &'static str,
    visual: Option<VisualResult>,
}

#[derive(Serialize)]
struct VisualResult {
    same_dimensions: bool,
    differing_pixels: Option<u64>,
    difference_percentage: f64,
    overlay_png: Option<String>,
}

struct DecodedImage {
    metadata: Metadata,
    frames: Vec<RgbaImage>,
}

fn fail(message: impl Into<String>) -> EngineError {
    EngineError(message.into())
}

fn validate_dimensions(width: u32, height: u32, total_pixels: u64) -> Result<u64, EngineError> {
    let pixels = u64::from(width)
        .checked_mul(u64::from(height))
        .ok_or_else(|| fail("The image dimensions are invalid."))?;
    if width == 0
        || height == 0
        || width > MAX_DIMENSION
        || height > MAX_DIMENSION
        || pixels > MAX_FRAME_PIXELS
    {
        return Err(fail(
            "The image dimensions exceed the supported safety limits.",
        ));
    }
    let total = total_pixels
        .checked_add(pixels)
        .ok_or_else(|| fail("The image dimensions exceed the supported safety limits."))?;
    if total > MAX_TOTAL_PIXELS_PER_FILE {
        return Err(fail(
            "The image exceeds the total decoded pixel safety limit.",
        ));
    }
    Ok(total)
}

fn append_frame(
    frames: &mut Vec<RgbaImage>,
    frame: Frame,
    total_pixels: &mut u64,
) -> Result<(), EngineError> {
    if frames.len() >= MAX_FRAMES {
        return Err(fail("Animated images may contain at most 100 frames."));
    }
    let mut image = frame.into_buffer();
    *total_pixels = validate_dimensions(image.width(), image.height(), *total_pixels)?;
    for pixel in image.pixels_mut() {
        if pixel[3] == 0 {
            pixel[0] = 0;
            pixel[1] = 0;
            pixel[2] = 0;
        }
    }
    frames.push(image);
    Ok(())
}

fn decode_frames(data: &[u8], format: ImageFormat) -> Result<(Vec<RgbaImage>, bool), EngineError> {
    let mut frames = Vec::new();
    let mut total_pixels = 0;
    let mut source_has_alpha = false;

    match format {
        ImageFormat::Gif => {
            let decoder = GifDecoder::new(BufReader::new(Cursor::new(data)))
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            for frame in decoder.into_frames() {
                let frame =
                    frame.map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
                append_frame(&mut frames, frame, &mut total_pixels)?;
            }
        }
        ImageFormat::WebP => {
            let decoder = WebPDecoder::new(BufReader::new(Cursor::new(data)))
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            source_has_alpha = decoder.color_type().has_alpha();
            if decoder.has_animation() {
                for frame in decoder.into_frames() {
                    let frame = frame
                        .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
                    append_frame(&mut frames, frame, &mut total_pixels)?;
                }
            } else {
                let decoded = DynamicImage::from_decoder(decoder)
                    .map_err(|_| fail("The uploaded image is malformed or unsupported."))?
                    .into_rgba8();
                append_frame(&mut frames, Frame::new(decoded), &mut total_pixels)?;
            }
        }
        ImageFormat::Png => {
            let decoder = PngDecoder::new(BufReader::new(Cursor::new(data)))
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            source_has_alpha = decoder.color_type().has_alpha();
            if decoder
                .is_apng()
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?
            {
                for frame in decoder
                    .apng()
                    .map_err(|_| fail("The uploaded image is malformed or unsupported."))?
                    .into_frames()
                {
                    let frame = frame
                        .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
                    append_frame(&mut frames, frame, &mut total_pixels)?;
                }
            } else {
                let decoded = DynamicImage::from_decoder(decoder)
                    .map_err(|_| fail("The uploaded image is malformed or unsupported."))?
                    .into_rgba8();
                append_frame(&mut frames, Frame::new(decoded), &mut total_pixels)?;
            }
        }
        ImageFormat::Jpeg => {
            let decoded = ImageReader::with_format(Cursor::new(data), ImageFormat::Jpeg)
                .decode()
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?
                .into_rgba8();
            append_frame(&mut frames, Frame::new(decoded), &mut total_pixels)?;
        }
        _ => return Err(fail("The uploaded image format is unsupported.")),
    }

    if frames.is_empty() {
        return Err(fail("The uploaded image is malformed or unsupported."));
    }
    Ok((frames, source_has_alpha))
}

fn format_name(format: ImageFormat) -> Result<&'static str, EngineError> {
    match format {
        ImageFormat::Png => Ok("PNG"),
        ImageFormat::Jpeg => Ok("JPEG"),
        ImageFormat::Gif => Ok("GIF"),
        ImageFormat::WebP => Ok("WEBP"),
        _ => Err(fail("Only PNG, JPEG, GIF, and WEBP images are supported.")),
    }
}

fn decode_image(path: &Path) -> Result<DecodedImage, EngineError> {
    let metadata = fs::metadata(path).map_err(|_| fail("The uploaded image could not be read."))?;
    if metadata.len() > MAX_FILE_BYTES {
        return Err(fail("Each comparison file must be 25 MB or smaller."));
    }
    let data = fs::read(path).map_err(|_| fail("The uploaded image could not be read."))?;
    let format = image::guess_format(&data)
        .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
    let format_name = format_name(format)?;
    let (frames, source_has_alpha) = decode_frames(&data, format)?;
    let first = &frames[0];
    let has_alpha = source_has_alpha || first.pixels().any(|pixel| pixel[3] < 255);

    Ok(DecodedImage {
        metadata: Metadata {
            dimensions: [first.width(), first.height()],
            format: format_name,
            animated: frames.len() > 1,
            frame_count: frames.len(),
            has_alpha,
        },
        frames,
    })
}

fn compress_image(input_path: &Path, output_path: &Path) -> Result<(), EngineError> {
    let metadata =
        fs::metadata(input_path).map_err(|_| fail("The uploaded image could not be read."))?;
    if metadata.len() > MAX_FILE_BYTES {
        return Err(fail("Each compression file must be 25 MB or smaller."));
    }
    let data = fs::read(input_path).map_err(|_| fail("The uploaded image could not be read."))?;
    let format = image::guess_format(&data)
        .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
    format_name(format)?;

    let mut encoded = Cursor::new(Vec::new());
    match format {
        ImageFormat::Png => {
            let decoder = PngDecoder::new(BufReader::new(Cursor::new(&data)))
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            if decoder
                .is_apng()
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?
            {
                return Err(fail("Animated PNG compression is not supported."));
            }
            let (width, height) = decoder.dimensions();
            validate_dimensions(width, height, 0)?;
            let image = DynamicImage::from_decoder(decoder)
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            PngEncoder::new_with_quality(&mut encoded, CompressionType::Best, FilterType::Adaptive)
                .write_image(
                    image.as_bytes(),
                    image.width(),
                    image.height(),
                    image.color().into(),
                )
                .map_err(|_| fail("The image could not be optimized."))?;
        }
        ImageFormat::Jpeg => {
            let mut decoder = image::codecs::jpeg::JpegDecoder::new(Cursor::new(&data))
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            let (width, height) = decoder.dimensions();
            validate_dimensions(width, height, 0)?;
            let orientation = decoder
                .orientation()
                .map_err(|_| fail("The uploaded image has invalid orientation metadata."))?;
            let mut image = DynamicImage::from_decoder(decoder)
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            image.apply_orientation(orientation);
            JpegEncoder::new_with_quality(&mut encoded, 90)
                .encode_image(&image)
                .map_err(|_| fail("The image could not be optimized."))?;
        }
        ImageFormat::Gif => {
            let decoder = GifDecoder::new(BufReader::new(Cursor::new(&data)))
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            let (width, height) = decoder.dimensions();
            validate_dimensions(width, height, 0)?;
            let mut frames = Vec::new();
            let mut total_pixels = 0;
            for frame in decoder.into_frames() {
                if frames.len() >= MAX_FRAMES {
                    return Err(fail("Animated images may contain at most 100 frames."));
                }
                let frame =
                    frame.map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
                let delay = frame.delay();
                let left = frame.left();
                let top = frame.top();
                let buffer = frame.into_buffer();
                total_pixels = validate_dimensions(buffer.width(), buffer.height(), total_pixels)?;
                frames.push(Frame::from_parts(buffer, left, top, delay));
            }
            if frames.is_empty() {
                return Err(fail("The uploaded image is malformed or unsupported."));
            }
            GifEncoder::new_with_speed(&mut encoded, 1)
                .encode_frames(frames)
                .map_err(|_| fail("The image could not be optimized."))?;
        }
        ImageFormat::WebP => {
            let decoder = WebPDecoder::new(BufReader::new(Cursor::new(&data)))
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            if decoder.has_animation() {
                return Err(fail("Animated WEBP compression is not supported."));
            }
            let (width, height) = decoder.dimensions();
            validate_dimensions(width, height, 0)?;
            let mut decoder = decoder;
            let orientation = decoder
                .orientation()
                .map_err(|_| fail("The uploaded image has invalid orientation metadata."))?;
            let mut image = DynamicImage::from_decoder(decoder)
                .map_err(|_| fail("The uploaded image is malformed or unsupported."))?;
            image.apply_orientation(orientation);
            image
                .write_to(&mut encoded, ImageFormat::WebP)
                .map_err(|_| fail("The image could not be optimized."))?;
        }
        _ => return Err(fail("Only PNG, JPEG, GIF, and WEBP images are supported.")),
    }

    let output = encoded.into_inner();
    if output.is_empty() || output.len() as u64 > MAX_FILE_BYTES {
        return Err(fail("The optimized image exceeds the 25 MB output limit."));
    }
    fs::write(output_path, &output).map_err(|_| fail("The optimized image could not be saved."))?;
    let verified = decode_image(output_path)?;
    if verified.metadata.format != format_name(format)? {
        return Err(fail("The optimized image format did not match the input."));
    }
    Ok(())
}

fn overlay_data_url(
    width: u32,
    height: u32,
    changed: &[u8],
    max_bytes: usize,
) -> Option<(String, usize)> {
    let mut rgba = Vec::with_capacity(changed.len() * 4);
    for pixel_changed in changed {
        if *pixel_changed != 0 {
            rgba.extend_from_slice(&[255, 0, 0, 180]);
        } else {
            rgba.extend_from_slice(&[0, 0, 0, 0]);
        }
    }
    let overlay = RgbaImage::from_raw(width, height, rgba)?;
    let mut encoded = Cursor::new(Vec::new());
    DynamicImage::ImageRgba8(overlay)
        .write_to(&mut encoded, ImageFormat::Png)
        .ok()?;
    let bytes = encoded.into_inner();
    if bytes.len() > max_bytes.min(MAX_PREVIEW_BYTES) {
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

fn compare_frame(
    first: &RgbaImage,
    second: &RgbaImage,
    preview_budget: usize,
) -> (VisualResult, usize) {
    if first.dimensions() != second.dimensions() {
        return (
            VisualResult {
                same_dimensions: false,
                differing_pixels: None,
                difference_percentage: 100.0,
                overlay_png: None,
            },
            0,
        );
    }

    let mut differing = 0u64;
    let mut changed = Vec::with_capacity((first.width() * first.height()) as usize);
    for (left, right) in first.pixels().zip(second.pixels()) {
        let is_changed = left != right;
        changed.push(u8::from(is_changed));
        differing += u64::from(is_changed);
    }

    let total = u64::from(first.width()) * u64::from(first.height());
    let (overlay_png, preview_size) =
        overlay_data_url(first.width(), first.height(), &changed, preview_budget)
            .map(|(data_url, size)| (Some(data_url), size))
            .unwrap_or((None, 0));
    (
        VisualResult {
            same_dimensions: true,
            differing_pixels: Some(differing),
            difference_percentage: ((differing as f64 * 100.0 / total as f64) * 1_000_000.0)
                .round()
                / 1_000_000.0,
            overlay_png,
        },
        preview_size,
    )
}

fn compare_images(
    first: DecodedImage,
    second: DecodedImage,
) -> Result<ImageComparison, EngineError> {
    let total_pixels = first
        .frames
        .iter()
        .chain(second.frames.iter())
        .try_fold(0u64, |total, frame| {
            total.checked_add(u64::from(frame.width()) * u64::from(frame.height()))
        })
        .ok_or_else(|| fail("The image pair exceeds the supported safety limits."))?;
    if total_pixels > MAX_TOTAL_PIXELS_PER_PAIR {
        return Err(fail(
            "The image pair exceeds the total decoded pixel safety limit.",
        ));
    }

    let first_count = first.frames.len();
    let second_count = second.frames.len();
    let mut frame_results = Vec::with_capacity(first_count.max(second_count));
    let mut preview_bytes = 0;
    for index in 0..first_count.max(second_count) {
        let result = if index >= first_count {
            FrameResult {
                frame: index + 1,
                status: "added",
                visual: None,
            }
        } else if index >= second_count {
            FrameResult {
                frame: index + 1,
                status: "removed",
                visual: None,
            }
        } else {
            let (visual, used) = compare_frame(
                &first.frames[index],
                &second.frames[index],
                MAX_TOTAL_PREVIEW_BYTES - preview_bytes,
            );
            preview_bytes += used;
            FrameResult {
                frame: index + 1,
                status: "compared",
                visual: Some(visual),
            }
        };
        frame_results.push(result);
    }

    let visual_differences = frame_results
        .iter()
        .filter(|result| {
            result
                .visual
                .as_ref()
                .is_none_or(|visual| visual.difference_percentage > 0.0)
        })
        .count();
    let first_format = first.metadata.format;
    let second_format = second.metadata.format;

    Ok(ImageComparison {
        first: first.metadata,
        second: second.metadata,
        first_format,
        second_format,
        animated: first_count > 1 || second_count > 1,
        frame_count_difference: first_count as isize - second_count as isize,
        frame_results,
        visual_differences,
        same_visual: visual_differences == 0,
    })
}

fn run() -> Result<(), EngineError> {
    let args: Vec<String> = env::args().collect();
    match args.as_slice() {
        [_, operation, first] if operation == "inspect" => {
            let image = decode_image(Path::new(first))?;
            println!(
                "{}",
                serde_json::to_string(&image.metadata)
                    .map_err(|_| fail("Could not encode image metadata."))?
            );
        }
        [_, operation, first, second] if operation == "compare" => {
            let first = decode_image(Path::new(first))?;
            let second = decode_image(Path::new(second))?;
            let result = compare_images(first, second)?;
            println!(
                "{}",
                serde_json::to_string(&result)
                    .map_err(|_| fail("Could not encode image comparison."))?
            );
        }
        [_, operation, input, output] if operation == "compress-image" => {
            compress_image(Path::new(input), Path::new(output))?;
            let input_bytes = fs::metadata(input)
                .map_err(|_| fail("The uploaded image could not be read."))?
                .len();
            let output_bytes = fs::metadata(output)
                .map_err(|_| fail("The optimized image could not be read."))?
                .len();
            println!(
                "{}",
                serde_json::json!({
                    "input_bytes": input_bytes,
                    "output_bytes": output_bytes
                })
            );
        }
        [_, operation, library_path, dpi, pdf_path] if operation == "pdf-inspect" => {
            let dpi = dpi
                .parse::<f32>()
                .map_err(|_| fail("Invalid PDF rendering DPI."))?;
            let result =
                pdf::inspect(Path::new(library_path), Path::new(pdf_path), dpi).map_err(fail)?;
            println!(
                "{}",
                serde_json::to_string(&result)
                    .map_err(|_| fail("Could not encode PDF metadata."))?
            );
        }
        [_, operation, library_path, dpi, first_path, second_path]
            if operation == "pdf-compare" =>
        {
            let dpi = dpi
                .parse::<f32>()
                .map_err(|_| fail("Invalid PDF rendering DPI."))?;
            let result = pdf::compare(
                Path::new(library_path),
                dpi,
                Path::new(first_path),
                Path::new(second_path),
            )
            .map_err(fail)?;
            println!(
                "{}",
                serde_json::to_string(&result)
                    .map_err(|_| fail("Could not encode PDF comparison."))?
            );
        }
        [_, operation, library_path, input, output] if operation == "pdf-compress" => {
            let result =
                pdf::compress(Path::new(library_path), Path::new(input), Path::new(output))
                    .map_err(fail)?;
            println!(
                "{}",
                serde_json::to_string(&result)
                    .map_err(|_| fail("Could not encode PDF compression metadata."))?
            );
        }
        _ => return Err(fail("Invalid image engine command.")),
    }
    std::io::stdout()
        .flush()
        .map_err(|_| fail("Could not write image engine output."))?;
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}
