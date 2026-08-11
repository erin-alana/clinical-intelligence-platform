# Version 1 Validation Rules
## Purpose
This document defines the validation rules applied by Version 1 of the Clinical
Intelligence Platform. The rules protect downstream analytics and AI workflows
from structurally invalid, clinically implausible, or internally inconsistent
records.
All current validation failures use `error` severity. A record with one or more
row-level errors is quarantined rather than included in the clean export.
## Error Structure
Every validation error contains the following information:
| Field | Description |
| --- | --- |
| `rule_set` | Validation module that produced the error |
| `validation_level` | File, field, or record level |
| `row_number` | Source CSV row, including the header as row 1 |
| `patient_id` | Patient identifier when available |
| `field` | Field or record component that failed |
| `rule` | Machine-readable rule name |
| `severity` | Current severity classification |
| `invalid_value` | Value that caused the failure, when applicable |
| `message` | Human-readable explanation |
## File-Ingestion Rules
| Rule ID | Rule | Failure behavior |
| --- | --- | --- |
| `FILE-001` | The input path must be a string or `Path` object. | Stop ingestion with a descriptive error. |
| `FILE-002` | The input path must exist and identify a file. | Stop ingestion without creating outputs. |
| `FILE-003` | Version 1 accepts `.csv` files only. | Reject unsupported file extensions. |
| `FILE-004` | The input file must not be empty. | Stop ingestion before parsing. |
| `FILE-005` | The CSV must be readable and structurally parseable. | Reject malformed or unreadable CSV content. |
| `FILE-006` | The CSV must contain at least one data row. | Reject header-only datasets. |
## Required Schema
The following columns are required:
- `patient_id`
- `age_at_diagnosis`
- `sex`
- `primary_site`
- `histology`
- `stage`
- `vital_status`
| Rule ID | Machine rule | Requirement |
| --- | --- | --- |
| `FIELD-001` | `required_column` | Every required column must be present. |
| `FIELD-002` | `required_value` | Required fields must not be null, empty, or whitespace-only. |
A missing required column is a dataset-level error. Because the schema cannot be
trusted, all records are quarantined during export.
## Field-Level Rules
| Rule ID | Field | Machine rule | Requirement |
| --- | --- | --- | --- |
| `FIELD-003` | `patient_id` | `data_type` | Must be text. |
| `FIELD-004` | `primary_site` | `data_type` | Must be text. |
| `FIELD-005` | `age_at_diagnosis` | `data_type` | Must be a whole number. |
| `FIELD-006` | `age_at_diagnosis` | `range` | Must be between 0 and 120, inclusive. |
| `FIELD-007` | `histology` | `data_type` | Must be a whole number. |
| `FIELD-008` | `histology` | `range` | Must be between 8000 and 9999, inclusive. |
| `FIELD-009` | `sex` | `allowed_value` | Must be `F`, `M`, `U`, or `Unknown`. |
| `FIELD-010` | `stage` | `allowed_value` | Must be `I`, `II`, `III`, or `IV`. |
| `FIELD-011` | `vital_status` | `allowed_value` | Must be `Alive`, `Dead`, or `Unknown`. |
## Terminology Standardization
Terminology is standardized before allowed-value validation. Unrecognized values
remain unchanged so the field validator can identify them instead of silently
converting them.
### Sex
| Input variants | Standard value |
| --- | --- |
| `f`, `female` | `F` |
| `m`, `male` | `M` |
| `u`, `unk`, `unknown` | `Unknown` |
### Stage
| Input variants | Standard value |
| --- | --- |
| `i`, `1`, `stage i`, `stage 1` | `I` |
| `ii`, `2`, `stage ii`, `stage 2` | `II` |
| `iii`, `3`, `stage iii`, `stage 3` | `III` |
| `iv`, `4`, `stage iv`, `stage 4` | `IV` |
### Vital Status
| Input variants | Standard value |
| --- | --- |
| `alive`, `living` | `Alive` |
| `dead`, `deceased` | `Dead` |
| `u`, `unk`, `unknown` | `Unknown` |
Leading and trailing whitespace is removed from `primary_site`. Other
unrecognized terminology is preserved for explicit validation.
## Record-Level Rules
| Rule ID | Machine rule | Requirement |
| --- | --- | --- |
| `RECORD-001` | `duplicate_patient_id` | A nonmissing `patient_id` must not occur more than once. |
| `RECORD-002` | `exact_duplicate_record` | An entire record must not exactly duplicate another row. |
Both occurrences are flagged when duplicates are detected. This prevents the
pipeline from selecting one record arbitrarily.
## Optional Date Rules
The current sample CSV does not contain date fields. When `birth_date`,
`diagnosis_date`, or `death_date` is supplied, the record validator applies the
following rules:
| Rule ID | Machine rule | Requirement |
| --- | --- | --- |
| `DATE-001` | `invalid_date` | A populated date must be parseable. |
| `DATE-002` | `future_date` | A clinical date must not occur in the future. |
| `DATE-003` | `date_sequence` | `diagnosis_date` must not precede `birth_date`. |
| `DATE-004` | `date_sequence` | `death_date` must not precede `diagnosis_date`. |
## Cross-Field Consistency Rules
These rules apply only when `death_date` is included:
| Rule ID | Machine rule | Requirement |
| --- | --- | --- |
| `CONSISTENCY-001` | `record_consistency` | A patient marked `Alive` must not have a `death_date`. |
| `CONSISTENCY-002` | `record_consistency` | A patient marked `Dead` must have a `death_date`. |
## Rule Execution Order
The validation engine runs rule sets in this order:
1. Record-level terminology standardization and validation
2. Field-level validation of the standardized data
3. Combined error reporting and rule-level summaries
This order allows recognized variants such as `stage 4` to become `IV` before
allowed-value validation occurs.
## Extending the Rules
Additional validation logic should be implemented as a function that accepts a
Pandas DataFrame and returns the processed DataFrame plus a structured error
DataFrame. The function can then be registered with `ValidationEngine` as a
`ValidationRule`.
New or revised clinical rules should include:
1. A stable rule identifier
2. A documented clinical or operational rationale
3. A descriptive error message
4. Automated tests for passing and failing examples
5. A documentation update in this file
