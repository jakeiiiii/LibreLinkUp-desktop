__version__ = "1.0.7"


def app_title(config: dict, suffix: str = "") -> str:
    name = "LibreLinkUp"
    if not config.get("hide_version", False):
        name += f" v{__version__}"
    if suffix:
        name += f" {suffix}"
    return name
