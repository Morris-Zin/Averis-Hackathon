"""Recover Word's logical content without pretending to reproduce page layout.

The reader owns compatibility branches, wrappers, text boxes and table nesting.
Callers receive ordered paragraphs/rows and explicit omissions, never XML nodes.
Paragraph numbers identify the structured preview, not rendered pages.
"""

from dataclasses import dataclass, field
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
_SUPPORTED_NAMESPACES = {W[1:-1], WPS}
_SUPPORTED_CHOICE = "{urn:averis:reader}supported-choice"


@dataclass(frozen=True)
class WordParagraph:
    text: str
    number: int


@dataclass(frozen=True)
class WordItem:
    cells: tuple[tuple[WordParagraph, ...], ...]
    table: bool = False
    boundary: bool = False


@dataclass
class WordContent:
    items: list[WordItem] = field(default_factory=list[WordItem])
    issues: list[str] = field(default_factory=list[str])


def read_word_content(content: bytes) -> WordContent:
    """Read a pre-bounded Office archive; omissions cannot masquerade as complete."""
    reader = _WordReader()
    with ZipFile(BytesIO(content)) as archive:
        root = _parse(archive.read("word/document.xml"))
        body = root.find(W + "body")
        if body is None:
            raise ValueError("Word body is missing")
        if any(
            node.tag in {W + "ins", W + "del", W + "moveFrom", W + "moveTo"}
            for node in body.iter()
        ):
            # Revision marks also occur in row/cell properties, not only text.
            reader.issue("docx_tracked_changes_require_review")
        if "word/styles.xml" in archive.namelist() and _uses_hidden_style(
            root, _parse(archive.read("word/styles.xml"))
        ):
            reader.issue("docx_hidden_text_requires_review")
        reader.read_container(body)
        # These parts are outside the current structured-preview location model.
        # Keep the omission visible rather than folding them into the body.
        for name in archive.namelist():
            if name.startswith(
                ("word/header", "word/footer", "word/footnotes", "word/endnotes")
            ) and name.endswith(".xml"):
                part = _parse(archive.read(name))
                if any((node.text or "").strip() for node in part.iter(W + "t")) or any(
                    node.tag.endswith(("}blip", "}imagedata", "}OLEObject"))
                    for node in part.iter()
                ):
                    reader.issue("docx_external_text_requires_review")
    return reader.result


def _uses_hidden_style(document: ET.Element, styles: ET.Element) -> bool:
    """Detect hidden styling in use; do not claim to render Word's style cascade.

    A hidden property anywhere in a referenced inheritance chain requires
    review, even if another formatting layer might override it. Unused styles
    are not grounds for holding an otherwise supported document.
    """
    definitions = {
        node.get(W + "styleId"): node for node in styles.findall(W + "style")
    }
    pending = [
        node.get(W + "val")
        for node in document.iter()
        if node.tag in {W + "pStyle", W + "rStyle", W + "tblStyle"}
    ]
    pending.extend(
        identifier
        for identifier, node in definitions.items()
        if node.get(W + "default") in {"1", "true", "on"}
    )
    defaults = styles.find(W + "docDefaults")
    if defaults is not None and _has_hidden_property(defaults):
        return True
    visited: set[str | None] = set()
    while pending:
        identifier = pending.pop()
        if identifier in visited or identifier not in definitions:
            continue
        visited.add(identifier)
        style = definitions[identifier]
        if _has_hidden_property(style):
            return True
        parent = style.find(W + "basedOn")
        if parent is not None:
            pending.append(parent.get(W + "val"))
    return False


def _has_hidden_property(node: ET.Element) -> bool:
    return any(
        child.tag in {W + "vanish", W + "webHidden"}
        and child.get(W + "val") not in {"0", "false", "off"}
        for child in node.iter()
    )


def _parse(data: bytes) -> ET.Element:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("DTD/entity declarations are unsupported")
    return ET.fromstring(data, parser=ET.XMLParser(target=_WordTreeBuilder()))


class _WordTreeBuilder(ET.TreeBuilder):
    def __init__(self) -> None:
        super().__init__()
        self.namespaces: dict[str, list[str]] = {}

    def start_ns(self, prefix: str, uri: str) -> None:
        self.namespaces.setdefault(prefix, []).append(uri)

    def end_ns(self, prefix: str) -> None:
        self.namespaces[prefix].pop()

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        node = super().start(tag, attrs)
        # Only this parser may certify a supported representation.
        node.attrib.pop(_SUPPORTED_CHOICE, None)
        if tag == MC + "Choice":
            required = attrs.get("Requires", "").split()
            supported = bool(required) and all(
                self.namespaces.get(prefix)
                and self.namespaces[prefix][-1] in _SUPPORTED_NAMESPACES
                for prefix in required
            )
            if supported:
                node.set(_SUPPORTED_CHOICE, "true")
        return node

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        # Reject declarations after decoding too, including UTF-16 archives.
        raise ValueError("DTD/entity declarations are unsupported")


class _WordReader:
    def __init__(self) -> None:
        self.result = WordContent()
        self.paragraph_number = 0

    def issue(self, code: str) -> None:
        if code not in self.result.issues:
            self.result.issues.append(code)

    def children(self, node: ET.Element) -> list[ET.Element]:
        """Resolve a compatibility representation once, not both visual copies."""
        if node.tag != MC + "AlternateContent":
            return list(node)
        choices = node.findall(MC + "Choice")
        chosen = next(
            (choice for choice in choices if choice.get(_SUPPORTED_CHOICE) == "true"),
            None,
        )
        if chosen is None:
            chosen = node.find(MC + "Fallback")
        if chosen is None:
            self.issue("docx_unsupported_alternate_content")
            return []
        representations = {
            " ".join("".join(text.text or "" for text in branch.iter(W + "t")).split())
            for branch in node
            if branch.tag == MC + "Fallback" or branch.get(_SUPPORTED_CHOICE) == "true"
        }
        if len(representations) > 1:
            self.issue("docx_alternate_content_conflict_requires_review")
        return list(chosen)

    def read_container(self, node: ET.Element, depth: int = 0) -> None:
        if depth > 64:
            raise ValueError("Word structure nesting exceeds supported depth")
        for child in self.children(node):
            if child.tag == W + "p":
                self.read_paragraph(child, depth + 1)
            elif child.tag == W + "tbl":
                self.read_table(child, depth + 1)
            elif child.tag in {W + "del", W + "moveFrom"}:
                self.issue("docx_tracked_changes_require_review")
            elif child.tag in {W + "ins", W + "moveTo"}:
                self.issue("docx_tracked_changes_require_review")
                self.read_container(child, depth + 1)
            elif child.tag in {
                W + "sdt",
                W + "sdtContent",
                W + "customXml",
                MC + "AlternateContent",
            }:
                self.read_container(child, depth + 1)
            elif child.tag == W + "altChunk":
                self.issue("docx_embedded_content_requires_review")
            elif any((text.text or "").strip() for text in child.iter(W + "t")):
                self.issue("docx_unsupported_structure_requires_review")

    def paragraph(self, node: ET.Element) -> tuple[WordParagraph, list[ET.Element]]:
        self.paragraph_number += 1
        number = self.paragraph_number
        pieces: list[str] = []
        boxes: list[ET.Element] = []
        self.inline(node, pieces, boxes)
        return WordParagraph("".join(pieces), number), boxes

    def inline(
        self,
        node: ET.Element,
        pieces: list[str],
        boxes: list[ET.Element],
        depth: int = 0,
    ) -> None:
        if depth > 64:
            raise ValueError("Word inline nesting exceeds supported depth")
        if node.tag == W + "txbxContent":
            boxes.append(node)
            return
        if node.tag in {W + "del", W + "moveFrom"}:
            self.issue("docx_tracked_changes_require_review")
            return
        if node.tag in {W + "ins", W + "moveTo"}:
            self.issue("docx_tracked_changes_require_review")
        if node.tag == W + "t":
            pieces.append(node.text or "")
        elif node.tag == W + "tab":
            pieces.append("\t")
        elif node.tag in {W + "br", W + "cr"}:
            pieces.append("\n")
        elif node.tag == W + "noBreakHyphen":
            pieces.append("\u2011")
        elif node.tag == W + "sym":
            # Preserve a visible unknown-character boundary rather than
            # concatenating digits on either side into an invented number.
            pieces.append("\ufffd")
            self.issue("docx_unsupported_symbol_requires_review")
        elif node.tag.endswith(("}blip", "}imagedata", "}OLEObject")):
            self.issue("docx_embedded_content_requires_review")
        elif node.tag.endswith("}t") and node.tag != W + "t" and node.text:
            self.issue("docx_unsupported_structure_requires_review")
        elif node.tag in {W + "vanish", W + "webHidden"} and node.get(
            W + "val"
        ) not in {"0", "false", "off"}:
            self.issue("docx_hidden_text_requires_review")
        for child in self.children(node):
            self.inline(child, pieces, boxes, depth + 1)

    def read_paragraph(self, node: ET.Element, depth: int) -> None:
        paragraph, boxes = self.paragraph(node)
        self.result.items.append(WordItem(((paragraph,),)))
        for box in boxes:
            # Text boxes are separate logical regions, located at their anchor.
            # Never extend an address from the surrounding body into a box.
            self.result.items.append(WordItem((), boundary=True))
            self.read_container(box, depth + 1)
            self.result.items.append(WordItem((), boundary=True))

    def read_table(self, table: ET.Element, depth: int) -> None:
        if depth > 64:
            raise ValueError("Word table nesting exceeds supported depth")
        if table.find(".//" + W + "vMerge") is not None:
            self.issue("docx_vertical_merge_requires_review")
        # Wrapped rows/cells need a richer table model. Do not silently drop them.
        for child in table:
            if child.tag not in {W + "tr", W + "tblPr", W + "tblGrid"}:
                self.issue("docx_table_structure_requires_review")
        for row in table.findall(W + "tr"):
            for child in row:
                if child.tag not in {W + "tc", W + "trPr"}:
                    self.issue("docx_table_structure_requires_review")
            cells: list[tuple[WordParagraph, ...]] = []
            for cell in row.findall(W + "tc"):
                cells.append(self.read_cell(cell))
                if cell.find(W + "tbl") is not None:
                    # Keep the containing row intact, and nested rows separate.
                    self.issue("docx_nested_table_requires_review")
            self.result.items.append(WordItem(tuple(cells), table=True))
            for cell in row.findall(W + "tc"):
                for nested in cell.findall(W + "tbl"):
                    self.read_table(nested, depth + 1)

    def read_cell(self, cell: ET.Element) -> tuple[WordParagraph, ...]:
        paragraphs: list[WordParagraph] = []
        for child in cell:
            if child.tag == W + "p":
                paragraph, boxes = self.paragraph(child)
                paragraphs.append(paragraph)
                if boxes:
                    self.issue("docx_table_textbox_requires_review")
            elif child.tag not in {W + "tcPr", W + "tbl"}:
                self.issue("docx_table_content_control_requires_review")
        return tuple(paragraphs)
