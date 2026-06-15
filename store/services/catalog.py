import unicodedata

from store.models import Package, Service


def _normalized(value):
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()


def _service_kind(service):
    identity = _normalized(f"{service.slug} {service.name}")
    if service.requires_comments or "coment" in identity:
        return "comments"
    if "curtida" in identity or "like" in identity:
        return "likes"
    if "visualiza" in identity or "view" in identity:
        return "views"
    return "profile"


_BONUS_KINDS = {
    "likes": ["profile", "views"],
    "views": ["likes", "profile"],
    "profile": ["likes", "views"],
    "comments": ["likes", "views"],
}

_BONUS_TARGET_CONFIG = {
    "profile": {"label": "Perfil", "placeholder": "@usuario ou link do perfil"},
    "likes": {"label": "Post ou Reels", "placeholder": "Cole o link do post ou Reels"},
    "views": {"label": "Vídeo/Reels", "placeholder": "Cole o link de um vídeo/Reels"},
}


def _active_packages_by_level(service):
    packages = list(
        Package.objects.filter(
            service=service,
            active=True,
            price_brl__gt=0,
        ).select_related("service", "service__platform")
    )
    positions = [package.position for package in packages]
    positions_are_reliable = (
        bool(positions)
        and all(position > 0 for position in positions)
        and len(positions) == len(set(positions))
    )
    if positions_are_reliable:
        return [
            (package.position, package)
            for package in sorted(
                packages,
                key=lambda package: (
                    package.position,
                    package.quantity,
                    package.price_brl,
                    package.pk,
                ),
            )
        ]
    ordered_packages = sorted(
        packages,
        key=lambda package: (
            package.quantity,
            package.price_brl,
            package.position,
            package.pk,
        ),
    )
    return list(enumerate(ordered_packages, start=1))


def get_bonus_options_for_package(selected_package):
    """Return up to two optional free bonus dicts for the selected package.

    Each dict has: package, kind, label, placeholder, enabled_field, target_field, idx.
    The last three are populated by OrderForm.__init__ after adding form fields.
    """
    main_kind = _service_kind(selected_package.service)
    desired_kinds = _BONUS_KINDS.get(main_kind, [])
    if not desired_kinds:
        return []

    main_packages = _active_packages_by_level(selected_package.service)
    try:
        selected_level = next(
            level for level, pkg in main_packages if pkg.pk == selected_package.pk
        )
    except StopIteration:
        selected_level = 1

    services = list(
        Service.objects.filter(
            platform=selected_package.service.platform,
            active=True,
            requires_comments=False,
            provider_service_id__gt="",
        )
        .exclude(pk=selected_package.service_id)
        .order_by("position", "name", "id")
    )

    bonuses = []
    for desired_kind in desired_kinds:
        for service in services:
            if _service_kind(service) != desired_kind:
                continue
            packages = _active_packages_by_level(service)
            if not packages:
                continue
            matching = [pkg for lvl, pkg in packages if lvl == selected_level]
            chosen_pkg = matching[0] if matching else packages[-1][1]
            config = _BONUS_TARGET_CONFIG[desired_kind]
            bonuses.append({
                "package": chosen_pkg,
                "kind": desired_kind,
                "label": config["label"],
                "placeholder": config["placeholder"],
            })
            break

    return bonuses


def get_checkout_complements(selected_package):
    """Return at most three paid complements matching the selected package level."""
    main_packages = _active_packages_by_level(selected_package.service)
    try:
        selected_level = next(
            level for level, package in main_packages if package.pk == selected_package.pk
        )
    except StopIteration:
        selected_level = 1

    main_kind = _service_kind(selected_package.service)
    complementary_kinds = {
        "profile": {"likes", "views"},
        "likes": {"views"},
        "views": {"likes"},
        "comments": {"likes", "views"},
    }[main_kind]
    services = (
        Service.objects.filter(
            platform=selected_package.service.platform,
            active=True,
            requires_comments=False,
            provider_service_id__gt="",
        )
        .exclude(pk=selected_package.service_id)
        .order_by("position", "name", "id")
    )

    complements = []
    for service in services:
        if _service_kind(service) not in complementary_kinds:
            continue
        packages = _active_packages_by_level(service)
        if not packages:
            continue
        eligible_packages = [
            (level, package) for level, package in packages if level <= selected_level
        ]
        if not eligible_packages:
            continue
        complements.append(max(eligible_packages, key=lambda item: item[0])[1])
        if len(complements) == 3:
            break
    return complements
