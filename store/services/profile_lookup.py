import re
from urllib.parse import urlparse


class ProfileLookupError(Exception):
    pass


def is_valid_instagram_username(username):
    """Valida username do Instagram: apenas letras, números, ponto e underline, até 30 caracteres."""
    if not username:
        return False
    return bool(re.match(r"^[A-Za-z0-9._]{1,30}$", username))


def extract_username_from_target(target):
    """Extrai username de @ ou link."""
    value = (target or "").strip()
    if not value:
        return ""
    
    # Se começa com @, remove e retorna
    if value.startswith("@"):
        return value[1:].strip()
    
    # Se é link, extrai username do path
    try:
        parsed = urlparse(value)
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            # O primeiro part do path é geralmente o username
            return path_parts[0].lstrip("@").strip()
    except:
        pass
    
    return ""


def validate_target_for_profile(target):
    """Valida target para serviços de perfil (seguidores).
    
    Aceita:
    - @usuario
    - usuario
    - https://www.instagram.com/usuario/
    - https://instagram.com/usuario/
    - https://www.tiktok.com/@usuario
    
    Rejeita se houver espaços ou formato inválido.
    """
    value = (target or "").strip()
    if not value:
        return False, "invalid"
    
    # Rejeita se houver espaços no conteúdo
    if " " in value:
        return False, "invalid"
    
    # Se é @usuario ou usuario
    if not value.startswith("http"):
        # Remove @ se existir
        username = value[1:] if value.startswith("@") else value
        if is_valid_instagram_username(username):
            return True, "format_valid"
        else:
            return False, "invalid"
    
    # Se é link
    value_lower = value.lower()
    
    # Instagram
    if "instagram.com" in value_lower:
        # Aceita https://www.instagram.com/usuario/ ou https://instagram.com/usuario/
        if re.search(r"instagram\.com/[A-Za-z0-9._]+/?$", value_lower):
            return True, "format_valid"
        return False, "invalid"
    
    # TikTok
    if "tiktok.com" in value_lower:
        # Aceita https://www.tiktok.com/@usuario ou vm.tiktok.com/...
        if re.search(r"tiktok\.com/@[A-Za-z0-9._]+", value_lower) or "vm.tiktok.com" in value_lower or "vt.tiktok.com" in value_lower:
            return True, "format_valid"
        return False, "invalid"
    
    return False, "invalid"


def validate_target_for_likes(target):
    """Valida target para curtidas (rejeita @, aceita links de publicação).
    
    Aceita:
    - https://www.instagram.com/p/ABC123/
    - https://www.instagram.com/reel/ABC123/
    - https://www.instagram.com/reels/ABC123/
    - https://www.instagram.com/tv/ABC123/
    """
    value = (target or "").strip()
    if not value:
        return False, "invalid"
    
    if " " in value:
        return False, "invalid"
    
    # Rejeita @ ou username sozinho
    if value.startswith("@") or not value.startswith("http"):
        return False, "invalid"
    
    value_lower = value.lower()
    
    # Instagram only
    if "instagram.com" not in value_lower:
        return False, "invalid"
    
    # Aceita /p/, /reel/, /reels/, /tv/
    if re.search(r"instagram\.com/(p|reel|reels|tv)/", value_lower):
        return True, "format_valid"
    
    return False, "invalid"


def validate_target_for_views(target):
    """Valida target para visualizações (rejeita @, aceita links de vídeo/reels).
    
    Aceita:
    - https://www.instagram.com/reel/ABC123/
    - https://www.instagram.com/reels/ABC123/
    """
    value = (target or "").strip()
    if not value:
        return False, "invalid"
    
    if " " in value:
        return False, "invalid"
    
    # Rejeita @ ou username sozinho
    if value.startswith("@") or not value.startswith("http"):
        return False, "invalid"
    
    value_lower = value.lower()
    
    # Instagram only
    if "instagram.com" not in value_lower:
        return False, "invalid"
    
    # Aceita apenas /reel/ ou /reels/
    if re.search(r"instagram\.com/reels?/", value_lower):
        return True, "format_valid"
    
    return False, "invalid"


def validate_target_for_comments(target):
    """Valida target para comentários (rejeita @, aceita links de publicação/reels).
    
    Aceita:
    - https://www.instagram.com/p/ABC123/
    - https://www.instagram.com/reel/ABC123/
    - https://www.instagram.com/reels/ABC123/
    - https://www.instagram.com/tv/ABC123/
    """
    value = (target or "").strip()
    if not value:
        return False, "invalid"
    
    if " " in value:
        return False, "invalid"
    
    # Rejeita @ ou username sozinho
    if value.startswith("@") or not value.startswith("http"):
        return False, "invalid"
    
    value_lower = value.lower()
    
    # Instagram only
    if "instagram.com" not in value_lower:
        return False, "invalid"
    
    # Aceita /p/, /reel/, /reels/, /tv/
    if re.search(r"instagram\.com/(p|reel|reels|tv)/", value_lower):
        return True, "format_valid"
    
    return False, "invalid"


def validate_target_for_tiktok_likes_or_views(target):
    """Valida target para curtidas/visualizações TikTok (rejeita @, aceita links de vídeo).
    
    Aceita:
    - https://www.tiktok.com/@usuario/video/ABC123
    - https://vm.tiktok.com/...
    - https://vt.tiktok.com/...
    """
    value = (target or "").strip()
    if not value:
        return False, "invalid"
    
    if " " in value:
        return False, "invalid"
    
    # Rejeita @ ou username sozinho
    if value.startswith("@") or not value.startswith("http"):
        return False, "invalid"
    
    value_lower = value.lower()
    
    # TikTok only
    if "tiktok.com" not in value_lower:
        return False, "invalid"
    
    # Aceita vm.tiktok.com, vt.tiktok.com ou tiktok.com/@usuario/video/
    if ("vm.tiktok.com" in value_lower or 
        "vt.tiktok.com" in value_lower or
        re.search(r"tiktok\.com/@[A-Za-z0-9._]+/video/", value_lower)):
        return True, "format_valid"
    
    return False, "invalid"


def validate_target_by_service_name(service_name, target):
    """Valida target de acordo com o nome do serviço.
    
    Retorna (is_valid, status) onde:
    - is_valid: bool
    - status: "format_valid" ou "invalid"
    """
    service_lower = (service_name or "").lower()
    
    # Seguidores
    if "seguidor" in service_lower:
        return validate_target_for_profile(target)
    
    # Curtidas Instagram
    if "curtida" in service_lower and "tiktok" not in service_lower:
        return validate_target_for_likes(target)
    
    # Visualizações Instagram Reels
    if "visualiza" in service_lower and "reel" in service_lower:
        return validate_target_for_views(target)
    
    # Comentários
    if "coment" in service_lower:
        return validate_target_for_comments(target)
    
    # Curtidas/Visualizações TikTok
    if ("curtida" in service_lower or "visualiza" in service_lower) and "tiktok" in service_lower:
        return validate_target_for_tiktok_likes_or_views(target)
    
    # Default: profile validation
    return validate_target_for_profile(target)


def lookup_profile(platform, target):
    """Valida apenas o formato do target.
    
    Retorna:
    - status="format_valid" se o formato é válido
    - status="invalid" se o formato é inválido
    
    Nunca afirma que o perfil foi encontrado ou que é público.
    """
    value = (target or "").strip()
    if not value or len(value) > 500:
        return {
            "ok": False,
            "status": "invalid",
            "username": "",
            "profile_picture_url": "",
            "is_public": None,
            "message": "Formato inválido. Não use espaços. Informe apenas @usuario ou um link válido.",
        }
    
    # Rejeita espaços
    if " " in value:
        return {
            "ok": False,
            "status": "invalid",
            "username": "",
            "profile_picture_url": "",
            "is_public": None,
            "message": "Formato inválido. Não use espaços. Informe apenas @usuario ou um link válido.",
        }
    
    is_valid, status = validate_target_for_profile(value)
    
    if not is_valid:
        return {
            "ok": False,
            "status": "invalid",
            "username": "",
            "profile_picture_url": "",
            "is_public": None,
            "message": "Formato inválido. Não use espaços. Informe apenas @usuario ou um link válido.",
        }
    
    # Extrai username para confirmação
    username = extract_username_from_target(value)
    
    return {
        "ok": True,
        "status": "format_valid",
        "username": username,
        "profile_picture_url": "",
        "is_public": None,
        "message": "O perfil precisa estar público para receber o pedido.",
    }


def list_recent_media(platform, username):
    """Compatibilidade: sempre retorna lista vazia."""
    return {"ok": True, "items": [], "message": "Cole o link da publicação manualmente."}
