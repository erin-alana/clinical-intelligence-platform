from dataclasses import dataclass
from typing import Callable

import pandas as pd

try:
    from .field_validation import ERROR_COLUMNS, validate_fields
    from .record_validation import validate_records
except ImportError:
    from field_validation import ERROR_COLUMNS, validate_fields
    from record_validation import validate_records


RULE_ERROR_COLUMNS = ["rule_set", "validation_level", *ERROR_COLUMNS]
SUMMARY_COLUMNS = ["rule_set", "validation_level", "error_count", "passed"]


@dataclass(frozen=True)
class ValidationRule:
    """Describe one reusable validation step."""

    name: str
    level: str
    handler: Callable
    description: str


@dataclass
class ValidationResult:
    """Contain the standardized data, errors, and rule summary."""

    data: pd.DataFrame
    errors: pd.DataFrame
    summary: pd.DataFrame

    @property
    def is_valid(self):
        """Return True when no validation errors were produced."""
        return self.errors.empty


def run_record_rules(dataframe):
    """Standardize data and run record-level validation."""
    return validate_records(dataframe)


def run_field_rules(dataframe):
    """Run field-level validation without modifying the data."""
    return dataframe.copy(), validate_fields(dataframe)


DEFAULT_RULES = (
    ValidationRule(
        name="record_validation",
        level="record",
        handler=run_record_rules,
        description=(
            "Standardize terminology and validate duplicates, dates, "
            "and record consistency."
        ),
    ),
    ValidationRule(
        name="field_validation",
        level="field",
        handler=run_field_rules,
        description=(
            "Validate required fields, data types, ranges, and allowed values."
        ),
    ),
)


class ValidationEngine:
    """Run an ordered, extensible collection of validation rules."""

    def __init__(self, rules=None):
        self._rules = []
        for rule in DEFAULT_RULES if rules is None else rules:
            self.register_rule(rule)

    @property
    def rules(self):
        """Expose the registered rules as an immutable tuple."""
        return tuple(self._rules)

    def register_rule(self, rule):
        """Register a validation rule while preventing duplicate names."""
        if not isinstance(rule, ValidationRule):
            raise TypeError("rule must be a ValidationRule instance.")

        if any(existing.name == rule.name for existing in self._rules):
            raise ValueError(f"Validation rule '{rule.name}' is already registered.")

        self._rules.append(rule)

    def validate(self, dataframe):
        """Run registered rules and return one combined validation result."""
        if not isinstance(dataframe, pd.DataFrame):
            raise TypeError("dataframe must be a pandas DataFrame.")

        current_data = dataframe.copy()
        error_frames = []
        summary_rows = []

        for rule in self._rules:
            processed_data, rule_errors = rule.handler(current_data)

            if not isinstance(processed_data, pd.DataFrame):
                raise TypeError(
                    f"Validation rule '{rule.name}' did not return a DataFrame."
                )

            if not isinstance(rule_errors, pd.DataFrame):
                raise TypeError(
                    f"Validation rule '{rule.name}' did not return an error DataFrame."
                )

            current_data = processed_data
            error_count = len(rule_errors)
            summary_rows.append(
                {
                    "rule_set": rule.name,
                    "validation_level": rule.level,
                    "error_count": error_count,
                    "passed": error_count == 0,
                }
            )

            if rule_errors.empty:
                continue

            tagged_errors = rule_errors.copy()
            tagged_errors.insert(0, "validation_level", rule.level)
            tagged_errors.insert(0, "rule_set", rule.name)
            error_frames.append(tagged_errors)

        if error_frames:
            combined_errors = pd.concat(error_frames, ignore_index=True)
            combined_errors = combined_errors.reindex(columns=RULE_ERROR_COLUMNS)
        else:
            combined_errors = pd.DataFrame(columns=RULE_ERROR_COLUMNS)

        summary = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
        return ValidationResult(
            data=current_data,
            errors=combined_errors,
            summary=summary,
        )


def main():
    """Run the default validation engine against the sample dataset."""
    try:
        from .ingest import RAW_DATA_PATH, load_data
    except ImportError:
        from ingest import RAW_DATA_PATH, load_data

    dataframe = load_data(RAW_DATA_PATH)
    result = ValidationEngine().validate(dataframe)

    print("Validation Summary")
    print(result.summary.to_string(index=False))

    if result.is_valid:
        print("\nValidation passed with no errors.")
        return

    print(f"\nValidation found {len(result.errors)} error(s).")
    print(result.errors.to_string(index=False))


if __name__ == "__main__":
    main()
