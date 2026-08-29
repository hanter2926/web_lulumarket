from typing import List, Dict


def segments_to_srt(segments: List[Dict]) -> str:
    """Convert segments to SRT formatted string.

    segments expected as: {"start": float, "end": float, "text_hindi": str}
    """
    def fmt_time(t: float) -> str:
        hours = int(t // 3600)
        minutes = int((t % 3600) // 60)
        seconds = int(t % 60)
        millis = int((t - int(t)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    lines = []
    for i, seg in enumerate(segments, start=1):
        start = fmt_time(seg.get('start', 0.0))
        end = fmt_time(seg.get('end', seg.get('start', 0.0)))
        text = seg.get('text_hindi', seg.get('text', ''))
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)
