#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


URI_SEGMENT_PATTERN = re.compile(r"(/URI/\d{4}-\d{2}-\d{2})([^-]*?)(-)")
XML_DECLARATION_PATTERN = re.compile(
    br"^\s*<\?xml[^>]*encoding=[\"'](?P<encoding>[^\"']+)[\"'][^>]*\?>",
    re.IGNORECASE,
)


@dataclass
class MatchResult:
    original: str
    fixed: str


@dataclass
class FileProcessResult:
    matches: list[MatchResult]
    wrote_file: bool


@dataclass
class AppConfig:
    input_dir: Path
    output_dir: Path
    xml_extensions: tuple[str, ...]
    recursive: bool
    copy_unmodified_xml: bool
    clear_output_before_run: bool
    zip_output: bool
    zip_file_name: str
    delete_input_after_success: bool
    continue_on_xml_error: bool
    print_each_change: bool
    summary_file: str | None


DEFAULT_CONFIG: dict[str, Any] = {
    "input_dir": "in",
    "output_dir": "out",
    "xml_extensions": [".xml"],
    "recursive": True,
    "copy_unmodified_xml": True,
    "clear_output_before_run": False,
    "zip_output": False,
    "zip_file_name": "out.zip",
    "delete_input_after_success": False,
    "continue_on_xml_error": True,
    "print_each_change": True,
    "summary_file": "run_summary.json",
}


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
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Percorso del file di configurazione JSON. Default: ./config.json",
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        type=Path,
        help="Override della cartella input definita nel config",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Override della cartella output definita nel config",
    )
    return parser.parse_args()


def local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


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


def write_tree(
    tree: ET.ElementTree,
    destination: Path,
    encoding: str,
    has_declaration: bool,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree.write(
        destination,
        encoding=encoding,
        xml_declaration=has_declaration,
    )


def iter_xml_files(input_dir: Path, recursive: bool, extensions: tuple[str, ...]) -> list[Path]:
    matcher = input_dir.rglob if recursive else input_dir.glob
    allowed_extensions = {extension.lower() for extension in extensions}
    return sorted(
        path
        for path in matcher("*")
        if path.is_file() and path.suffix.lower() in allowed_extensions
    )


def process_file(
    xml_path: Path,
    output_path: Path,
    copy_unmodified_xml: bool,
) -> FileProcessResult:
    register_namespaces(xml_path)
    output_encoding, has_declaration = detect_xml_output_settings(xml_path)
    tree = ET.parse(xml_path)
    matches = analyze_tree(tree)
    wrote_file = False

    if matches or copy_unmodified_xml:
        write_tree(tree, output_path, output_encoding, has_declaration)
        wrote_file = True

    return FileProcessResult(matches=matches, wrote_file=wrote_file)


def load_json_file(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("Il config JSON deve contenere un oggetto.")

    unknown_keys = sorted(set(data) - set(DEFAULT_CONFIG))
    if unknown_keys:
        raise ValueError(
            f"Chiavi sconosciute nel config: {', '.join(unknown_keys)}"
        )

    return data


def ensure_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Il campo '{field_name}' deve essere booleano.")
    return value


def ensure_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Il campo '{field_name}' deve essere una stringa non vuota.")
    return value


def build_config(
    config_path: Path,
    cli_input_dir: Path | None,
    cli_output_dir: Path | None,
) -> AppConfig:
    loaded = load_json_file(config_path)
    raw = DEFAULT_CONFIG | loaded
    base_dir = config_path.resolve().parent

    input_dir_value = cli_input_dir or Path(ensure_string(raw["input_dir"], "input_dir"))
    output_dir_value = cli_output_dir or Path(ensure_string(raw["output_dir"], "output_dir"))
    xml_extensions_raw = raw["xml_extensions"]

    if not isinstance(xml_extensions_raw, list) or not xml_extensions_raw:
        raise ValueError("Il campo 'xml_extensions' deve essere una lista non vuota.")

    xml_extensions = tuple(
        extension if extension.startswith(".") else f".{extension}"
        for extension in (
            ensure_string(item, "xml_extensions[]").lower()
            for item in xml_extensions_raw
        )
    )

    input_dir = (base_dir / input_dir_value).resolve() if not input_dir_value.is_absolute() else input_dir_value.resolve()
    output_dir = (base_dir / output_dir_value).resolve() if not output_dir_value.is_absolute() else output_dir_value.resolve()

    return AppConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        xml_extensions=xml_extensions,
        recursive=ensure_bool(raw["recursive"], "recursive"),
        copy_unmodified_xml=ensure_bool(raw["copy_unmodified_xml"], "copy_unmodified_xml"),
        clear_output_before_run=ensure_bool(raw["clear_output_before_run"], "clear_output_before_run"),
        zip_output=ensure_bool(raw["zip_output"], "zip_output"),
        zip_file_name=ensure_string(raw["zip_file_name"], "zip_file_name"),
        delete_input_after_success=ensure_bool(raw["delete_input_after_success"], "delete_input_after_success"),
        continue_on_xml_error=ensure_bool(raw["continue_on_xml_error"], "continue_on_xml_error"),
        print_each_change=ensure_bool(raw["print_each_change"], "print_each_change"),
        summary_file=(
            ensure_string(raw["summary_file"], "summary_file")
            if raw["summary_file"] is not None
            else None
        ),
    )


def validate_config(config: AppConfig) -> None:
    if not config.input_dir.exists() or not config.input_dir.is_dir():
        raise ValueError(f"Cartella input non valida: {config.input_dir}")

    if config.output_dir == config.input_dir:
        raise ValueError("La cartella di output deve essere diversa dalla cartella di input.")

    if is_relative_to(config.output_dir, config.input_dir) or is_relative_to(config.input_dir, config.output_dir):
        raise ValueError("Le cartelle input e output non devono essere annidate una dentro l'altra.")


def prepare_output_dir(config: AppConfig) -> None:
    if config.clear_output_before_run and config.output_dir.exists():
        shutil.rmtree(config.output_dir)
    config.output_dir.mkdir(parents=True, exist_ok=True)


def create_zip_archive(output_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output_dir.parent))


def write_summary(summary_path: Path, payload: dict[str, Any]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def main() -> int:
    args = parse_args()
    config_path = args.config.resolve()

    try:
        config = build_config(config_path, args.input_dir, args.output_dir)
        validate_config(config)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Configurazione non valida: {exc}", file=sys.stderr)
        return 2

    xml_files = iter_xml_files(config.input_dir, config.recursive, config.xml_extensions)
    if not xml_files:
        print("Nessun file XML trovato.")
        return 0

    prepare_output_dir(config)

    total_matches = 0
    total_files_with_changes = 0
    total_files_written = 0
    parse_errors: list[str] = []

    for xml_path in xml_files:
        relative_path = xml_path.relative_to(config.input_dir)
        output_path = config.output_dir / relative_path

        try:
            result = process_file(
                xml_path,
                output_path,
                config.copy_unmodified_xml,
            )
        except ET.ParseError as exc:
            message = f"{xml_path}: XML non valido ({exc})"
            parse_errors.append(message)
            print(f"[ERRORE] {message}", file=sys.stderr)
            if not config.continue_on_xml_error:
                break
            continue

        if result.wrote_file:
            total_files_written += 1

        if not result.matches:
            continue

        total_files_with_changes += 1
        total_matches += len(result.matches)

        if config.print_each_change:
            print(f"\nFile: {xml_path}")
            for index, match in enumerate(result.matches, start=1):
                print(f"  Occorrenza {index}:")
                print(f"    Prima: {match.original}")
                print(f"    Dopo : {match.fixed}")

    success = not parse_errors
    zip_path: Path | None = None
    input_deleted = False

    if config.zip_output:
        zip_path = config.output_dir.parent / config.zip_file_name
        create_zip_archive(config.output_dir, zip_path)

    if success and config.delete_input_after_success:
        shutil.rmtree(config.input_dir)
        input_deleted = True

    summary_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config_file": str(config_path),
        "input_dir": str(config.input_dir),
        "output_dir": str(config.output_dir),
        "zip_output": config.zip_output,
        "zip_file": str(zip_path) if zip_path else None,
        "delete_input_after_success": config.delete_input_after_success,
        "input_deleted": input_deleted,
        "files_scanned": len(xml_files),
        "files_written": total_files_written,
        "files_with_changes": total_files_with_changes,
        "occurrences_changed": total_matches,
        "parse_errors": parse_errors,
        "config": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        },
    }

    if config.summary_file is not None:
        summary_path = Path(config.summary_file)
        if not summary_path.is_absolute():
            summary_path = config_path.parent / summary_path
        write_summary(summary_path.resolve(), summary_payload)

    if total_matches == 0:
        print(f"Nessuna anomalia trovata. XML elaborati in: {config.output_dir}")
    else:
        print(f"\nCartella output: {config.output_dir}")
        print(f"Ricorrenze cambiate: {total_matches}")
        print(f"File XML con modifiche: {total_files_with_changes}")

    if total_files_written:
        print(f"File XML scritti in output: {total_files_written}")

    if zip_path is not None:
        print(f"Archivio ZIP creato: {zip_path}")

    if input_deleted:
        print(f"Cartella input cancellata: {config.input_dir}")

    if parse_errors:
        print(f"Errori XML: {len(parse_errors)}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
