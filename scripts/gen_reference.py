"""Generate the reference section at mkdocs build time.

Driver pages come from the live ``flex_drivers.CATALOG`` and integration pages
from ``catalog.json``, so a new driver or integration shows up on the site
without touching the docs. Also publishes ``install.ps1`` at the site root so
``irm flex.levylab.org/install.ps1 | iex`` works.
"""

from pathlib import Path

import mkdocs_gen_files

from flex.components import load_ref
from flex.pkgmanager.catalog import load_catalog
from flex_drivers import CATALOG

ROOT = Path(__file__).resolve().parents[1]

# -- install.ps1 at the site root -------------------------------------------

with mkdocs_gen_files.open("install.ps1", "w", encoding="utf-8", newline="") as f:
    f.write((ROOT / "install.ps1").read_text(encoding="utf-8"))

# -- drivers -----------------------------------------------------------------

drivers: dict[str, list[tuple[str, str, type]]] = {}  # vendor -> [(name, ref, cls)]
for name, ref in sorted(CATALOG.items()):
    vendor = name.split(".", 1)[0]
    drivers.setdefault(vendor, []).append((name, ref, load_ref(ref)))


def summary(obj) -> str:
    doc = (obj.__doc__ or "").strip()
    return doc.splitlines()[0] if doc else ""


with mkdocs_gen_files.open("reference/drivers/index.md", "w") as f:
    f.write("# Drivers\n\n")
    f.write(
        "Every driver in `flex-drivers`, generated from the package's live\n"
        "`CATALOG` at build time. The **name** column is what goes in a\n"
        "station's `driver = ...` key and in `flex enable`.\n\n"
    )
    for vendor, entries in sorted(drivers.items()):
        f.write(f"## {vendor}\n\n")
        f.write("| Name | Class | Summary |\n|---|---|---|\n")
        for name, _ref, cls in entries:
            page = name.replace(".", "-")
            f.write(f"| [`{name}`]({page}.md) | `{cls.__name__}` | {summary(cls)} |\n")
        f.write("\n")

nav_lines = ["- [Overview](index.md)"]
for _vendor, entries in sorted(drivers.items()):
    for name, ref, cls in entries:
        page = f"{name.replace('.', '-')}.md"
        module, _, _ = ref.partition(":")
        with mkdocs_gen_files.open(f"reference/drivers/{page}", "w") as f:
            f.write(f"# `{name}`\n\n")
            lv_class = getattr(cls, "lv_class", None)
            if lv_class:
                f.write(f"LabVIEW class: `{lv_class}` (auto-connected by `CESession`)\n\n")
            f.write(f"::: {module}.{cls.__name__}\n")
        nav_lines.append(f"- [{name}]({page})")

with mkdocs_gen_files.open("reference/drivers/SUMMARY.md", "w") as f:
    f.write("\n".join(nav_lines) + "\n")

# -- integrations -------------------------------------------------------------

catalog = load_catalog()
integrations = {k: v for k, v in catalog.items() if v.get("group") == "Integrations"}

with mkdocs_gen_files.open("reference/integrations/index.md", "w") as f:
    f.write("# Integrations\n\n")
    f.write("Generated from the package catalog at build time.\n\n")
    f.write("| Package | Provides | Summary |\n|---|---|---|\n")
    for pkg, meta in sorted(integrations.items()):
        provides = ", ".join(
            f"`{kind}: {', '.join(names)}`" for kind, names in meta.get("provides", {}).items()
        ) or "hooks"
        f.write(f"| [`{pkg}`]({pkg}.md) | {provides} | {meta.get('summary', '')} |\n")

nav_lines = ["- [Overview](index.md)"]
for pkg, meta in sorted(integrations.items()):
    with mkdocs_gen_files.open(f"reference/integrations/{pkg}.md", "w") as f:
        f.write(f"# `{pkg}`\n\n{meta.get('summary', '')}\n\n")
        if not meta.get("default"):
            f.write(f"```\nflex install {pkg}\n```\n\n")
        refs = [
            (name, ref)
            for registry in meta.get("registries", {}).values()
            for name, ref in sorted(load_ref(registry).items())
        ]
        for name, ref in refs:
            module, _, cls_name = ref.partition(":")
            f.write(f"## `{name}`\n\n::: {module}.{cls_name}\n\n")
        if not refs:  # hook-only package: document its hooks module
            module = pkg.replace("-", "_")
            f.write(f"::: {module}.hooks\n")
    nav_lines.append(f"- [{pkg}]({pkg}.md)")

with mkdocs_gen_files.open("reference/integrations/SUMMARY.md", "w") as f:
    f.write("\n".join(nav_lines) + "\n")
