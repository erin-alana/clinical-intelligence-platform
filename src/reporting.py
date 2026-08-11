from pathlib import Path

import pandas as pd

try:
    from .field_validation import is_missing
    from .validation_engine import ValidationEngine
except ImportError:
    from field_validation import is_missing
    from validation_engine import ValidationEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = PROJECT_ROOT / "outputs" / "data_quality_report.md"


def calculate_quality_metrics(dataframe, errors):
    """Calculate dataset-level quality metrics from validation results."""
    total_records = len(dataframe)
    total_cells = dataframe.shape[0] * dataframe.shape[1]
    missing_cells = sum(
        int(dataframe[column].map(is_missing).sum()) for column in dataframe.columns
    )

    if "row_number" in errors.columns:
        invalid_row_numbers = pd.to_numeric(
            errors["row_number"], errors="coerce"
        ).dropna()
        invalid_records = int(invalid_row_numbers.nunique())
    else:
        invalid_records = 0

    invalid_records = min(invalid_records, total_records)
    valid_records = total_records - invalid_records
    completeness_percent = (
        ((total_cells - missing_cells) / total_cells) * 100 if total_cells else 100.0
    )
    valid_record_percent = (
        (valid_records / total_records) * 100 if total_records else 100.0
    )

    return {
        "status": "PASS" if errors.empty else "FAIL",
        "total_records": total_records,
        "valid_records": valid_records,
        "invalid_records": invalid_records,
        "valid_record_percent": round(valid_record_percent, 2),
        "total_errors": len(errors),
        "missing_cells": missing_cells,
        "completeness_percent": round(completeness_percent, 2),
    }


def summarize_missing_data(dataframe):
    """Summarize missing values for every field in the dataset."""
    rows = []
    total_records = len(dataframe)

    for field in dataframe.columns:
        missing_count = int(dataframe[field].map(is_missing).sum())
        missing_percent = (
            (missing_count / total_records) * 100 if total_records else 0.0
        )
        rows.append(
            {
                "field": field,
                "missing_count": missing_count,
                "missing_percent": round(missing_percent, 2),
            }
        )

    return pd.DataFrame(
        rows,
        columns=["field", "missing_count", "missing_percent"],
    )


def summarize_errors(errors):
    """Count validation errors by level, field, rule, and severity."""
    columns = [
        "validation_level",
        "field",
        "rule",
        "severity",
        "error_count",
    ]

    if errors.empty:
        return pd.DataFrame(columns=columns)

    return (
        errors.groupby(
            ["validation_level", "field", "rule", "severity"],
            dropna=False,
        )
        .size()
        .reset_index(name="error_count")
        .sort_values(
            ["error_count", "validation_level", "field"],
            ascending=[False, True, True],
        )
        .reset_index(drop=True)
    )


def format_cell(value):
    """Format one value for safe display in a Markdown table."""
    if pd.isna(value):
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).replace("|", "\\|").replace("\n", " ")


def dataframe_to_markdown(dataframe):
    """Render a DataFrame as a GitHub-compatible Markdown table."""
    headers = [format_cell(column) for column in dataframe.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]

    for row in dataframe.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(format_cell(value) for value in row) + " |")

    return "\n".join(lines)


def generate_quality_report(dataframe, validation_result, source_name="dataset"):
    """Generate a readable Markdown data-quality report."""
    metrics = calculate_quality_metrics(dataframe, validation_result.errors)
    missing_summary = summarize_missing_data(dataframe)
    error_summary = summarize_errors(validation_result.errors)

    metric_table = pd.DataFrame(
        [
            ("Validation status", metrics["status"]),
            ("Total records", metrics["total_records"]),
            ("Valid records", metrics["valid_records"]),
            ("Invalid records", metrics["invalid_records"]),
            ("Valid record rate", f'{metrics["valid_record_percent"]:.2f}%'),
            ("Total validation errors", metrics["total_errors"]),
            ("Missing cells", metrics["missing_cells"]),
            ("Field completeness", f'{metrics["completeness_percent"]:.2f}%'),
        ],
        columns=["metric", "value"],
    )

    invalid_records = metrics["invalid_records"]
    total_records = metrics["total_records"]
    if metrics["status"] == "PASS":
        interpretation = "All records passed the configured validation rules."
    else:
        interpretation = (
            f"{invalid_records} of {total_records} records failed at least one "
            f"validation rule. Review the error summary before using this dataset "
            f"for analytics or AI workflows."
        )

    sections = [
        "# Data Quality Report",
        f"**Source:** `{source_name}`",
        "## Executive Summary",
        dataframe_to_markdown(metric_table),
        "## Rule Results",
        dataframe_to_markdown(validation_result.summary),
        "## Missing Data by Field",
        dataframe_to_markdown(missing_summary),
        "## Validation Error Summary",
        (
            dataframe_to_markdown(error_summary)
            if not error_summary.empty
            else "No validation errors detected."
        ),
        "## Interpretation",
        interpretation,
    ]

    return "\n\n".join(sections) + "\n"


def save_quality_report(report, output_path=DEFAULT_REPORT_PATH):
    """Save a Markdown quality report and return its path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return path


def main():
    """Generate a quality report for the repository's sample dataset."""
    try:
        from .ingest import RAW_DATA_PATH, load_data
    except ImportError:
        from ingest import RAW_DATA_PATH, load_data

    dataframe = load_data(RAW_DATA_PATH)
    validation_result = ValidationEngine().validate(dataframe)
    report = generate_quality_report(
        dataframe,
        validation_result,
        source_name=RAW_DATA_PATH.name,
    )
    report_path = save_quality_report(report)

    print(report)
    print(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
