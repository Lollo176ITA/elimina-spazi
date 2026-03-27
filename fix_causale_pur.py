#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


URI_SEGMENT_PATTERN = re.compile(r"(/URI/\d{4}-\d{2}-\d{2})([^-]*?)(-)")
XML_DECLARATION_PATTERN = re.compile(
    br"^\s*<\?xml[^>]*encoding=[\"'](?P<encoding>[^\"']+)[\"'][^>]*\?>",
    re.IGNORECASE,
)


@dataclass
class MatchResult:
    original: str
    fixed: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scansiona una cartella di file XML, cerca i tag <causale> che "
            "contengono /PUR/, corregge lo spazio extra prima del trattino "
            "successivo alla data nel segmento /URI/ e salva il risultato in "
            "una cartella di output."
        )
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        type=Path,
        default=Path("in"),
        help="Cartella da scansionare. Default: ./in",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Cartella di output. Default: ./out",
    )
    return parser.parse_args()


def local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def register_namespaces(xml_path: Path) -> None:
    for _, node in ET.iterparse(xml_path, events=("start-ns",)):
        prefix, uri = node
        ET.register_namespace(prefix or "", uri)


def detect_xml_output_settings(xml_path: Path) -> tuple[str, bool]:
    header = xml_path.read_bytes()[:256]
    match = XML_DECLARATION_PATTERN.search(header)
    if not match:
        return "utf-8", False
    return match.group("encoding").decode("ascii", errors="replace"), True


def normalize_causale(text: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        between_date_and_dash = match.group(2)
        cleaned = re.sub(r"\s+", "", between_date_and_dash)
        return f"{match.group(1)}{cleaned}{match.group(3)}"

    return URI_SEGMENT_PATTERN.sub(replacer, text)


def analyze_tree(tree: ET.ElementTree) -> list[MatchResult]:
    results: list[MatchResult] = []
    root = tree.getroot()

    for element in root.iter():
        if local_name(element.tag) != "causale":
            continue
        if not element.text or "/PUR/" not in element.text:
            continue

        fixed = normalize_causale(element.text)
        if fixed != element.text:
            results.append(MatchResult(original=element.text, fixed=fixed))
            element.text = fixed

    return results


def iter_xml_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.rglob("*.xml") if path.is_file())


def write_tree(tree: ET.ElementTree, destination: Path, encoding: str, has_declaration: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree.write(
        destination,
        encoding=encoding,
        xml_declaration=has_declaration,
    )


def process_file(xml_path: Path, output_path: Path) -> list[MatchResult]:
    register_namespaces(xml_path)
    output_encoding, has_declaration = detect_xml_output_settings(xml_path)
    tree = ET.parse(xml_path)
    results = analyze_tree(tree)
    write_tree(tree, output_path, output_encoding, has_declaration)

    return results


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir
    output_dir = args.output_dir or Path("out")

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Cartella non valida: {input_dir}", file=sys.stderr)
        return 2
    if output_dir == input_dir:
        print("La cartella di output deve essere diversa dalla cartella di input.", file=sys.stderr)
        return 2

    xml_files = iter_xml_files(input_dir)
    if not xml_files:
        print("Nessun file XML trovato.")
        return 0

    total_matches = 0
    total_files = 0

    for xml_path in xml_files:
        try:
            relative_path = xml_path.relative_to(input_dir)
            output_path = output_dir / relative_path
            matches = process_file(xml_path, output_path)
        except ET.ParseError as exc:
            print(f"[ERRORE] {xml_path}: XML non valido ({exc})", file=sys.stderr)
            continue

        if not matches:
            continue

        total_files += 1
        total_matches += len(matches)
        print(f"\nFile: {xml_path}")

        for index, match in enumerate(matches, start=1):
            print(f"  Occorrenza {index}:")
            print(f"    Prima: {match.original}")
            print(f"    Dopo : {match.fixed}")

    if total_matches == 0:
        print(f"Nessuna anomalia trovata. XML copiati in: {output_dir}")
        return 0

    print(f"\nCartella output: {output_dir}")
    print(f"Ricorrenze cambiate: {total_matches}")
    print(f"File XML con modifiche: {total_files}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
