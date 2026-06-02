def normalize_user_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("Name cannot be empty")
    return normalized.title()
