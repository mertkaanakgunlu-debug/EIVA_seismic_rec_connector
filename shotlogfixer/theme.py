"""Small dependency-free light/dark token set for the tkinter UI."""

THEMES = {
    "Light": {
        "background": "#F5F7F9", "panel": "#FFFFFF", "panel_secondary": "#F0F2F4",
        "border": "#D8DEE4", "text": "#24292F", "secondary": "#57606A", "accent": "#0969DA",
        "selected": "#DDF4FF", "matched": "#2DA44E", "eiva_only": "#CF222E",
        "review": "#BF8700", "recorder_invalid": "#B45F06",
    },
    "Dark": {
        "background": "#0D1117", "panel": "#161B22", "panel_secondary": "#21262D",
        "border": "#30363D", "text": "#F0F6FC", "secondary": "#8B949E", "accent": "#2F81F7",
        "selected": "#1F3A5A", "matched": "#3FB950", "eiva_only": "#F85149",
        "review": "#D29922", "recorder_invalid": "#E3B341",
    },
}


def get_theme(name: str) -> dict[str, str]:
    return THEMES.get(name, THEMES["Light"]).copy()
