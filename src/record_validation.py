import pandas as pd

try:
    from .field_validation import ERROR_COLUMNS, add_error, is_missing
except ImportError:
    from field_validation import ERROR_COLUMNS, add_error, is_missing


TERMINOLOGY_MAPS = {
    "sex": {
        "f": "F",
        "female": "F",
        "m": "M",
        "male": "M",
        "u": "Unknown",
        "unk": "Unknown",
        "unknown": "Unknown",
    },
    "stage": {
        "i": "I",
        "1": "I",
        "stage i": "I",
        "stage 1": "I",
        "ii": "II",
        "2": "II",
        "stage ii": "II",
        "stage 2": "II",
        "iii": "III",
        "3": "III",
        "stage iii": "III",
        "stage 3": "III",
        "iv": "IV",
        "4": "IV",
        "stage iv": "IV",
        "stage 4": "IV",
    },
    "vital_status": {
        "alive": "Alive",
        "living": "Alive",
        "dead": "Dead",
        "deceased": "Dead",
        "u": "Unknown",
        "unk": "Unknown",
        "unknown": "Unknown",
    },
}

DATE_COLUMNS = ("birth_date", "diagnosis_date", "death_date")


def standardize_value(value, mapping):
    """Map a terminology variant to its canonical value."""
    if is_missing(value):
        return value

    normalized_value = str(value).strip().casefold()
    fallback = value.strip() if isinstance(value, str) else value
    return mapping.get(normalized_value, fallback)


def standardize_terminology(dataframe):
    """Return a copy with supported clinical terminology standardized."""
    standardized = dataframe.copy()

    for field, mapping in TERMINOLOGY_MAPS.items():
        if field in standardized.columns:
            standardized[field] = standardized[field].map(
                lambda value: standardize_value(value, mapping)
            )

    if "primary_site" in standardized.columns:
        standardized["primary_site"] = standardized["primary_site"].map(
            lambda value: value.strip()
            if isinstance(value, str) and value.strip()
            else value
        )

    return standardized


def patient_id_for(row):
    """Return a usable patient identifier for an error message."""
    patient_id = row.get("patient_id")
    return None if is_missing(patient_id) else patient_id


def validate_duplicates(dataframe, errors):
    """Detect duplicate patient identifiers and exact duplicate records."""
    if "patient_id" in dataframe.columns:
        patient_ids = dataframe["patient_id"]
        usable_ids = patient_ids.map(lambda value: not is_missing(value))
        duplicate_ids = usable_ids & patient_ids.duplicated(keep=False)

        for position, (_, row) in enumerate(dataframe.iterrows()):
            if not duplicate_ids.iloc[position]:
                continue

            patient_id = patient_id_for(row)
            add_error(
                errors,
                row_number=position + 2,
                patient_id=patient_id,
                field="patient_id",
                rule="duplicate_patient_id",
                invalid_value=patient_id,
                message=f"patient_id {patient_id!r} occurs more than once.",
            )

    exact_duplicates = dataframe.duplicated(keep=False)
    for position, (_, row) in enumerate(dataframe.iterrows()):
        if not exact_duplicates.iloc[position]:
            continue

        add_error(
            errors,
            row_number=position + 2,
            patient_id=patient_id_for(row),
            field="record",
            rule="exact_duplicate_record",
            invalid_value=None,
            message="Record exactly duplicates another row in the dataset.",
        )


def parse_dates(dataframe, errors):
    """Parse supported date fields and report invalid or future dates."""
    parsed_dates = {}
    today = pd.Timestamp.today().normalize()

    for field in DATE_COLUMNS:
        if field not in dataframe.columns:
            continue

        parsed_values = []
        for position, (_, row) in enumerate(dataframe.iterrows()):
            value = row[field]

            if is_missing(value):
                parsed_values.append(pd.NaT)
                continue

            parsed_value = pd.to_datetime(value, errors="coerce")
            if not pd.isna(parsed_value) and parsed_value.tzinfo is not None:
                parsed_value = parsed_value.tz_localize(None)
            parsed_values.append(parsed_value)

            if pd.isna(parsed_value):
                add_error(
                    errors,
                    row_number=position + 2,
                    patient_id=patient_id_for(row),
                    field=field,
                    rule="invalid_date",
                    invalid_value=value,
                    message=f"{field} contains an invalid date: {value!r}.",
                )
            elif parsed_value.normalize() > today:
                add_error(
                    errors,
                    row_number=position + 2,
                    patient_id=patient_id_for(row),
                    field=field,
                    rule="future_date",
                    invalid_value=value,
                    message=f"{field} cannot occur in the future: {value!r}.",
                )

        parsed_dates[field] = pd.Series(parsed_values, index=dataframe.index)

    return parsed_dates


def validate_date_sequence(dataframe, parsed_dates, errors):
    """Validate chronological relationships between clinical dates."""
    date_pairs = (
        ("birth_date", "diagnosis_date"),
        ("diagnosis_date", "death_date"),
    )

    for earlier_field, later_field in date_pairs:
        if earlier_field not in parsed_dates or later_field not in parsed_dates:
            continue

        for position, (_, row) in enumerate(dataframe.iterrows()):
            earlier_date = parsed_dates[earlier_field].iloc[position]
            later_date = parsed_dates[later_field].iloc[position]

            if pd.isna(earlier_date) or pd.isna(later_date):
                continue

            if later_date < earlier_date:
                add_error(
                    errors,
                    row_number=position + 2,
                    patient_id=patient_id_for(row),
                    field=later_field,
                    rule="date_sequence",
                    invalid_value=row[later_field],
                    message=(
                        f"{later_field} cannot occur before {earlier_field}."
                    ),
                )


def validate_vital_status(dataframe, parsed_dates, errors):
    """Validate consistency between vital status and death date."""
    if "vital_status" not in dataframe.columns or "death_date" not in dataframe.columns:
        return

    death_dates = parsed_dates.get("death_date")
    if death_dates is None:
        return

    for position, (_, row) in enumerate(dataframe.iterrows()):
        status = row["vital_status"]
        death_date = death_dates.iloc[position]

        if status == "Alive" and not pd.isna(death_date):
            add_error(
                errors,
                row_number=position + 2,
                patient_id=patient_id_for(row),
                field="vital_status",
                rule="record_consistency",
                invalid_value=status,
                message="A patient marked Alive cannot have a death_date.",
            )
        elif status == "Dead" and is_missing(row["death_date"]):
            add_error(
                errors,
                row_number=position + 2,
                patient_id=patient_id_for(row),
                field="death_date",
                rule="record_consistency",
                invalid_value=None,
                message="A patient marked Dead must have a death_date.",
            )


def validate_records(dataframe):
    """Standardize records and return structured record-level errors."""
    standardized = standardize_terminology(dataframe)
    errors = []

    validate_duplicates(standardized, errors)
    parsed_dates = parse_dates(standardized, errors)
    validate_date_sequence(standardized, parsed_dates, errors)
    validate_vital_status(standardized, parsed_dates, errors)

    return standardized, pd.DataFrame(errors, columns=ERROR_COLUMNS)


def main():
    """Run record validation against the repository's sample dataset."""
    try:
        from .ingest import RAW_DATA_PATH, load_data
    except ImportError:
        from ingest import RAW_DATA_PATH, load_data

    dataframe = load_data(RAW_DATA_PATH)
    standardized, errors = validate_records(dataframe)

    print(f"Standardized {len(standardized)} record(s).")
    if errors.empty:
        print("Record validation passed with no errors.")
        return

    print(f"Record validation found {len(errors)} error(s).")
    print(errors.to_string(index=False))


if __name__ == "__main__":
    main()
