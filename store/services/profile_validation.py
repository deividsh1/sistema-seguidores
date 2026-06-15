import re
from urllib.parse import urlparse


USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}


def _service_kind(service):
    name = service.name.lower()
    if service.requires_comments or "coment" in name:
        return "comments"
    if "curtida" in name:
        return "likes"
    if "visualiza" in name:
        return "views"
    return "profile"


def _parse_http_url(target):
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.hostname:
        return None
    return parsed, [part for part in parsed.path.split("/") if part]


def _valid_profile_target(platform_slug, target):
    if not target.startswith(("http://", "https://")):
        return target.startswith("@") and bool(USERNAME_RE.fullmatch(target[1:]))

    parsed_target = _parse_http_url(target)
    if not parsed_target:
        return False
    parsed, path_parts = parsed_target
    hostname = parsed.hostname.lower()
    if platform_slug == "instagram":
        return (
            hostname in INSTAGRAM_HOSTS
            and len(path_parts) == 1
            and bool(USERNAME_RE.fullmatch(path_parts[0]))
        )
    if platform_slug == "tiktok":
        return (
            hostname in TIKTOK_HOSTS
            and len(path_parts) == 1
            and path_parts[0].startswith("@")
            and bool(USERNAME_RE.fullmatch(path_parts[0][1:]))
        )
    return False


def _valid_instagram_content_target(kind, parsed, path_parts):
    if parsed.hostname.lower() not in INSTAGRAM_HOSTS or len(path_parts) < 2:
        return False
    allowed_types = {"reel", "reels"} if kind == "views" else {"p", "reel", "reels", "tv"}
    return path_parts[0].lower() in allowed_types and bool(path_parts[1])


def _valid_tiktok_video_target(parsed, path_parts):
    hostname = parsed.hostname.lower()
    if hostname in {"vm.tiktok.com", "vt.tiktok.com"}:
        return bool(path_parts)
    return (
        hostname in {"tiktok.com", "www.tiktok.com"}
        and len(path_parts) >= 3
        and path_parts[0].startswith("@")
        and bool(USERNAME_RE.fullmatch(path_parts[0][1:]))
        and path_parts[1].lower() == "video"
        and bool(path_parts[2])
    )


def validate_target_for_service(service, target):
    value = (target or "").strip()
    if not value or len(value) > 500 or re.search(r"\s", target or ""):
        return False

    platform_slug = service.platform.slug.lower()
    kind = _service_kind(service)
    if kind == "profile":
        return _valid_profile_target(platform_slug, value)

    parsed_target = _parse_http_url(value)
    if not parsed_target:
        return False
    parsed, path_parts = parsed_target
    if platform_slug == "instagram":
        return _valid_instagram_content_target(kind, parsed, path_parts)
    if platform_slug == "tiktok" and kind in {"likes", "views"}:
        return _valid_tiktok_video_target(parsed, path_parts)
    return False


def normalize_target_for_service(service, target):
    """Normaliza o target para salvar e enviar ao fornecedor sem querystring/fragments."""
    value = (target or "").strip()
    if not value:
        return value

    platform_slug = service.platform.slug.lower()
    kind = _service_kind(service)

    if kind == "profile" and not value.startswith(("http://", "https://")):
        username = value[1:] if value.startswith("@") else value
        if platform_slug == "instagram":
            return f"https://www.instagram.com/{username}/"
        if platform_slug == "tiktok":
            return f"https://www.tiktok.com/@{username}"
        return value

    parsed_target = _parse_http_url(value)
    if not parsed_target:
        return value

    parsed, path_parts = parsed_target
    hostname = parsed.hostname.lower()

    if platform_slug == "instagram":
        if kind == "profile" and path_parts:
            username = path_parts[0].strip().strip("/")
            return f"https://www.instagram.com/{username}/"

        if len(path_parts) >= 2:
            content_type = path_parts[0].lower().strip()
            if content_type == "reels":
                content_type = "reel"
            code = path_parts[1].strip().strip("/")
            return f"https://www.instagram.com/{content_type}/{code}/"

    if platform_slug == "tiktok":
        if kind == "profile" and path_parts:
            username = path_parts[0].strip().strip("/")
            if not username.startswith("@"):
                username = f"@{username}"
            return f"https://www.tiktok.com/{username}"

        if hostname in {"vm.tiktok.com", "vt.tiktok.com"} and path_parts:
            code = path_parts[0].strip().strip("/")
            return f"https://{hostname}/{code}/"

        if len(path_parts) >= 3 and path_parts[1].lower() == "video":
            username = path_parts[0].strip().strip("/")
            video_id = path_parts[2].strip().strip("/")
            return f"https://www.tiktok.com/{username}/video/{video_id}"

    return value
