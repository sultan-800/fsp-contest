import mimetypes
import re
from pathlib import Path

from django.http import FileResponse, Http404

SAFE_INLINE = {"application/pdf", "image/png", "image/jpeg", "image/webp"}

ALLOWED_MATERIAL_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md",
                        ".zip", ".png", ".jpg", ".jpeg", ".webp", ".csv", ".odt", ".ods"}
ALLOWED_CODE_EXT = {".py", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".java", ".cs", ".kt", ".go",
                    ".js", ".ts", ".pas", ".dpr", ".rb", ".rs", ".txt", ".php", ".swift", ".scala"}


def safe_filename(name, fallback="file"):
    name = Path(name or "").name
    name = re.sub(r"[^\w.\-() ]+", "_", name, flags=re.UNICODE).strip() or fallback
    return name[:150]


def serve_private(fieldfile, download_name=None, inline=False):
    if not fieldfile:
        raise Http404
    try:
        fh = fieldfile.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404
    name = safe_filename(download_name or Path(fieldfile.name).name)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    as_attachment = not (inline and ctype in SAFE_INLINE)
    if as_attachment:
        ctype = "application/octet-stream"
    resp = FileResponse(fh, as_attachment=as_attachment, filename=name, content_type=ctype)
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Security-Policy"] = "default-src 'none'; sandbox"
    resp["Cache-Control"] = "private, no-store"
    return resp
