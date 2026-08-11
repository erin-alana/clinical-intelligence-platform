from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

try:
    from .validation_engine import ValidationEngine, ValidationResult
except ImportError:
    from validation_engine import ValidationEngine, ValidationResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "data" / "exports"


class ExportIntegrityError(Exception):
    """Raised when an exported file fails an integrity check."""


@dataclass(frozen=True)
class ExportResult:
    """Describe the files and record counts produced by an export."""

    clean_path: Path
    quarantine_path: Path
    errors_path: Path
    manifest_path: Path
    clean_records: int
    quarantined_records: int
    validation_errors: int


def file_sha256(file_path):
    """Calculate the SHA-256 checksum for a file."""
    digest = sha256()
    with Path(file_path).open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def invalid_record_positions(errors, record_count):
    """Convert validation row numbers into zero-based record positions."""
    if errors.empty:
        return set()

    if "row_number" not in errors.columns:
        raise ExportIntegrityError("Validation errors do not include row_number.")

    if errors["row_number"].isna().any():
        return set(range(record_count))

    positions = set()
    for row_number in errors["row_number"]:
        numeric_row = pd.to_numeric(row_number, errors="coerce")
        if pd.isna(numeric_row) or not float(numeric_row).is_integer():
            raise ExportIntegrityError(
                f"Invalid validation row number: {row_number!r}."
            )

        position = int(numeric_row) - 2
        if not 0 <= position < record_count:
            raise ExportIntegrityError(
                f"Validation row number {row_number!r} is outside the dataset."
            )
        positions.add(position)

    return positions


def split_valid_and_quarantined(validation_result):
    """Split standardized data using the validation error row numbers."""
    data = validation_result.data
    invalid_positions = invalid_record_positions(
        validation_result.errors,
        len(data),
    )
    valid_positions = [
        position for position in range(len(data)) if position not in invalid_positions
    ]
    quarantined_positions = sorted(invalid_positions)

    clean_data = data.iloc[valid_positions].reset_index(drop=True).copy()
    quarantined_data = data.iloc[quarantined_positions].reset_index(drop=True).copy()

    if quarantined_positions:
        quarantined_data.insert(
            0,
            "source_row_number",
            [position + 2 for position in quarantined_positions],
        )
    else:
        quarantined_data.insert(0, "source_row_number", pd.Series(dtype="int64"))

    return clean_data, quarantined_data


def verify_csv_export(expected, file_path):
    """Verify an exported CSV's columns, rows, and serialized values."""
    exported = pd.read_csv(file_path)

    if list(exported.columns) != list(expected.columns):
        raise ExportIntegrityError(
            f"Column mismatch detected in exported file: {file_path}."
        )

    if len(exported) != len(expected):
        raise ExportIntegrityError(
            f"Row-count mismatch detected in exported file: {file_path}."
        )

    expected_text = expected.to_csv(index=False, lineterminator="\n")
    exported_text = exported.to_csv(index=False, lineterminator="\n")
    if exported_text != expected_text:
        raise ExportIntegrityError(
            f"Value mismatch detected in exported file: {file_path}."
        )


def safe_export_name(base_name):
    """Return a filename-safe base name without directories or extensions."""
    name = Path(str(base_name)).name
    stem = Path(name).stem.strip()
    if not stem or stem in {".", ".."}:
        raise ValueError("base_name must contain a usable filename.")
    return stem


def export_validation_results(
    validation_result,
    output_dir=DEFAULT_EXPORT_DIR,
    base_name="oncology",
    source_path=None,
):
    """Export clean, quarantined, and error data with integrity metadata."""
    if not isinstance(validation_result, ValidationResult):
        raise TypeError("validation_result must be a ValidationResult instance.")

    export_dir = Path(output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    export_name = safe_export_name(base_name)

    clean_path = export_dir / f"{export_name}_clean.csv"
    quarantine_path = export_dir / f"{export_name}_quarantine.csv"
    errors_path = export_dir / f"{export_name}_validation_errors.csv"
    manifest_path = export_dir / f"{export_name}_export_manifest.json"
    output_paths = (clean_path, quarantine_path, errors_path, manifest_path)

    source = Path(source_path).resolve() if source_path is not None else None
    if source is not None:
        if not source.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")
        if any(path.resolve() == source for path in output_paths):
            raise ValueError("Export paths cannot overwrite the source file.")
        source_checksum_before = file_sha256(source)
    else:
        source_checksum_before = None

    clean_data, quarantined_data = split_valid_and_quarantined(validation_result)
    validation_errors = validation_result.errors.reset_index(drop=True).copy()

    clean_data.to_csv(clean_path, index=False)
    quarantined_data.to_csv(quarantine_path, index=False)
    validation_errors.to_csv(errors_path, index=False)

    verify_csv_export(clean_data, clean_path)
    verify_csv_export(quarantined_data, quarantine_path)
    verify_csv_export(validation_errors, errors_path)

    if source is not None and file_sha256(source) != source_checksum_before:
        raise ExportIntegrityError("The source file changed during export.")

    manifest = {
        "source": {
            "path": str(source) if source is not None else None,
            "sha256": source_checksum_before,
            "record_count": len(validation_result.data),
        },
        "exports": {
            "clean": {
                "path": clean_path.name,
                "record_count": len(clean_data),
                "sha256": file_sha256(clean_path),
            },
            "quarantine": {
                "path": quarantine_path.name,
                "record_count": len(quarantined_data),
                "sha256": file_sha256(quarantine_path),
            },
            "validation_errors": {
                "path": errors_path.name,
                "record_count": len(validation_errors),
                "sha256": file_sha256(errors_path),
            },
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    return ExportResult(
        clean_path=clean_path,
        quarantine_path=quarantine_path,
        errors_path=errors_path,
        manifest_path=manifest_path,
        clean_records=len(clean_data),
        quarantined_records=len(quarantined_data),
        validation_errors=len(validation_errors),
    )


def main():
    """Export validation results for the repository's sample dataset."""
    try:
        from .ingest import RAW_DATA_PATH, load_data
    except ImportError:
        from ingest import RAW_DATA_PATH, load_data

    dataframe = load_data(RAW_DATA_PATH)
    validation_result = ValidationEngine().validate(dataframe)
    export_result = export_validation_results(
        validation_result,
        base_name="oncology",
        source_path=RAW_DATA_PATH,
    )

    print(f"Clean records exported: {export_result.clean_records}")
    print(f"Records quarantined: {export_result.quarantined_records}")
    print(f"Validation errors exported: {export_result.validation_errors}")
    print(f"Export manifest: {export_result.manifest_path}")


if __name__ == "__main__":
    main()
