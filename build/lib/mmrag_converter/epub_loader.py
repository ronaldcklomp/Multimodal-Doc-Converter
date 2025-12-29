from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import xml.etree.ElementTree as ET


@dataclass
class EpubSpineItem:
    idref: str
    href: str
    media_type: str


def _join_href(base_path: str, href: str) -> str:
    """Join OPF-relative paths in a zip context."""
    if not base_path or "/" not in base_path:
        return href.lstrip("/")
    base_dir = base_path.rsplit("/", 1)[0]
    return f"{base_dir}/{href}".lstrip("/")


def _strip_xhtml_to_text(xhtml: str) -> str:
    """Very lightweight XHTML -> text extraction.

    We keep paragraph-ish boundaries using newlines so downstream structure
    analysis can still work.
    """
    s = xhtml
    # remove scripts/styles
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.I | re.S)

    # Convert common block boundaries to newlines.
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(
        r"</(p|div|h\d|li|tr|table|section|article|blockquote)\s*>",
        "\n",
        s,
        flags=re.I,
    )
    # remove all remaining tags
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    # normalize whitespace but keep newlines
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # collapse spaces on each line
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in s.split("\n")]
    # remove empty lines and join
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def read_epub_metadata(epub_path: Path) -> Dict[str, Any]:
    """Extract basic metadata from EPUB OPF."""
    with zipfile.ZipFile(epub_path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        root_el = container.find(".//{*}rootfile")
        if root_el is None:
            raise ValueError(
                "Invalid EPUB: missing rootfile in container.xml"
            )
        rootfile = root_el.attrib.get("full-path")
        if not rootfile:
            raise ValueError("Invalid EPUB: rootfile has no full-path")
        opf = ET.fromstring(z.read(rootfile))

        # Very tolerant namespace handling
        def _find_text(tag_suffix: str) -> Optional[str]:
            el = opf.find(f".//{{*}}{tag_suffix}")
            if el is None or not el.text:
                return None
            return el.text.strip() or None

        title = _find_text("title")
        creator = _find_text("creator")

        meta: Dict[str, Any] = {
            "format": "EPUB",
        }
        if title:
            meta["title"] = title
        if creator:
            meta["author"] = creator
        meta["rootfile"] = rootfile
        return meta


def load_epub_spine(epub_path: Path) -> Tuple[Dict[str, Any], List[EpubSpineItem]]:
    """Return (metadata, spine_items) from the EPUB."""

    with zipfile.ZipFile(epub_path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        root_el = container.find(".//{*}rootfile")
        if root_el is None:
            raise ValueError(
                "Invalid EPUB: missing rootfile in container.xml"
            )
        rootfile = root_el.attrib.get("full-path")
        if not rootfile:
            raise ValueError("Invalid EPUB: rootfile has no full-path")
        opf = ET.fromstring(z.read(rootfile))

        manifest: Dict[str, Tuple[str, str]] = {}
        for item in opf.findall(".//{*}manifest/{*}item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            media_type = item.attrib.get("media-type", "")
            if item_id and href:
                manifest[item_id] = (href, media_type)

        spine_idrefs = [
            i.attrib.get("idref")
            for i in opf.findall(".//{*}spine/{*}itemref")
        ]
        spine: List[EpubSpineItem] = []
        for idref in spine_idrefs:
            if not idref:
                continue
            if idref not in manifest:
                continue
            href, media_type = manifest[idref]
            spine.append(
                EpubSpineItem(
                    idref=idref,
                    href=_join_href(rootfile, href),
                    media_type=media_type,
                )
            )

        meta = read_epub_metadata(epub_path)
        return meta, spine


def extract_epub_text_by_spine(epub_path: Path) -> List[str]:
    """Return list of extracted text per spine item (in reading order)."""

    _, spine = load_epub_spine(epub_path)

    texts: List[str] = []
    with zipfile.ZipFile(epub_path) as z:
        for item in spine:
            try:
                raw = z.read(item.href).decode("utf-8", errors="replace")
            except KeyError:
                # Some EPUBs may have inconsistent paths. Skip gracefully.
                continue
            txt = _strip_xhtml_to_text(raw)
            texts.append(txt)
    return texts
