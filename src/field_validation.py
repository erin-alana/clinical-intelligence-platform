import pandas as pd

REQUIRED_COLUMNS = [
   "patient_id",
   "age_at_diagnosis",
   "sex",
   "primary_site",
   "histology",
   "stage",
   "vital_status",
]
ALLOWED_VALUES = {
   "sex": {"F", "M", "U", "Unknown"},
   "stage": {"I", "II", "III", "IV"},
   "vital_status": {"Alive", "Dead", "Unknown"},
}
ERROR_COLUMNS = [
   "row_number",
   "patient_id",
   "field",
   "rule",
   "severity",
   "invalid_value",
   "message",
]

def is_missing(value):
   """Return True when a field contains no usable value."""
   return pd.isna(value) or (isinstance(value, str) and not value.strip())

def add_error(
   errors,
   *,
   row_number,
   patient_id,
   field,
   rule,
   invalid_value,
   message,
):
   """Append one consistently structured validation error."""
   errors.append(
       {
           "row_number": row_number,
           "patient_id": patient_id,
           "field": field,
           "rule": rule,
           "severity": "error",
           "invalid_value": invalid_value,
           "message": message,
       }
   )

def validate_numeric_field(
   errors,
   *,
   value,
   row_number,
   patient_id,
   field,
   minimum,
   maximum,
):
   """Validate a required field as a whole number within a range."""
   numeric_value = pd.to_numeric(value, errors="coerce")
   if pd.isna(numeric_value) or not float(numeric_value).is_integer():
       add_error(
           errors,
           row_number=row_number,
           patient_id=patient_id,
           field=field,
           rule="data_type",
           invalid_value=value,
           message=f"{field} must be a whole number; received {value!r}.",
       )
       return
   if not minimum <= numeric_value <= maximum:
       add_error(
           errors,
           row_number=row_number,
           patient_id=patient_id,
           field=field,
           rule="range",
           invalid_value=value,
           message=(
               f"{field} must be between {minimum} and {maximum}; "
               f"received {value!r}."
           ),
       )

def validate_fields(dataframe):
   """Validate required columns, field values, types, and ranges."""
   errors = []
   missing_columns = [
       column for column in REQUIRED_COLUMNS if column not in dataframe.columns
   ]
   for column in missing_columns:
       add_error(
           errors,
           row_number=None,
           patient_id=None,
           field=column,
           rule="required_column",
           invalid_value=None,
           message=f"Required column '{column}' is missing from the dataset.",
       )
   available_columns = [
       column for column in REQUIRED_COLUMNS if column in dataframe.columns
   ]
   for row_number, (_, row) in enumerate(dataframe.iterrows(), start=2):
       raw_patient_id = row.get("patient_id")
       patient_id = None if is_missing(raw_patient_id) else raw_patient_id
       missing_fields = set()
       for field in available_columns:
           if is_missing(row[field]):
               missing_fields.add(field)
               add_error(
                   errors,
                   row_number=row_number,
                   patient_id=patient_id,
                   field=field,
                   rule="required_value",
                   invalid_value=None,
                   message=f"Required field '{field}' is missing.",
               )
       for field in ("patient_id", "primary_site"):
           if field in available_columns and field not in missing_fields:
               value = row[field]
               if not isinstance(value, str):
                   add_error(
                       errors,
                       row_number=row_number,
                       patient_id=patient_id,
                       field=field,
                       rule="data_type",
                       invalid_value=value,
                       message=f"{field} must be text; received {value!r}.",
                   )
       if (
           "age_at_diagnosis" in available_columns
           and "age_at_diagnosis" not in missing_fields
       ):
           validate_numeric_field(
               errors,
               value=row["age_at_diagnosis"],
               row_number=row_number,
               patient_id=patient_id,
               field="age_at_diagnosis",
               minimum=0,
               maximum=120,
           )
       if "histology" in available_columns and "histology" not in missing_fields:
           validate_numeric_field(
               errors,
               value=row["histology"],
               row_number=row_number,
               patient_id=patient_id,
               field="histology",
               minimum=8000,
               maximum=9999,
           )
       for field, allowed_values in ALLOWED_VALUES.items():
           if field not in available_columns or field in missing_fields:
               continue
           value = row[field]
           if value not in allowed_values:
               allowed_text = ", ".join(sorted(allowed_values))
               add_error(
                   errors,
                   row_number=row_number,
                   patient_id=patient_id,
                   field=field,
                   rule="allowed_value",
                   invalid_value=value,
                   message=(
                       f"{field} must be one of: {allowed_text}; "
                       f"received {value!r}."
                   ),
               )
   return pd.DataFrame(errors, columns=ERROR_COLUMNS)

def main():
   """Run field validation against the repository's sample dataset."""
   try:
       from .ingest import RAW_DATA_PATH, load_data
   except ImportError:
       from ingest import RAW_DATA_PATH, load_data
   dataframe = load_data(RAW_DATA_PATH)
   errors = validate_fields(dataframe)
   if errors.empty:
       print("Field validation passed with no errors.")
       return
   print(f"Field validation found {len(errors)} error(s).")
   print(errors.to_string(index=False))

if __name__ == "__main__":
   main()
