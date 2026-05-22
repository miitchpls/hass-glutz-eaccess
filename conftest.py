"""Root conftest: inject local integration into the installed HA package namespace."""
from pathlib import Path
import homeassistant.components

homeassistant.components.__path__.append(
    str(Path(__file__).parent / "homeassistant" / "components")
)
