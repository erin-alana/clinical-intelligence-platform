from pathlib import Path
import pandas as pd
from pandas.errors import EmptyDataError, ParserError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "oncology_sample.csv"
SUPPORTED_FILE_TYPES = {".csv"}

class DataIngestionError(Exception):
   """Raised when a data file cannot be safely ingested."""

def validate_input_file(file_path):
   """Validate an input path before attempting to read its contents."""
   if not isinstance(file_path, (str, Path)):
       raise DataIngestionError("Input file path must be a string or Path object.")
   path = Path(file_path)
   if not path.exists():
       raise FileNotFoundError(f"Input file not found: {path}")
   if not path.is_file():
       raise DataIngestionError(f"Input path is not a file: {path}")
   if path.suffix.lower() not in SUPPORTED_FILE_TYPES:
       raise DataIngestionError(
           f"Unsupported file format '{path.suffix or 'none'}'. "
           "Version 1 supports CSV files only."
       )
   if path.stat().st_size == 0:
       raise DataIngestionError(f"Input file is empty: {path}")
   return path

def load_data(file_path):
   """Load a validated CSV file into a pandas DataFrame."""
   path = validate_input_file(file_path)
   try:
       dataframe = pd.read_csv(path)
   except (EmptyDataError, ParserError, UnicodeDecodeError, OSError) as exc:
       raise DataIngestionError(
           f"Unable to parse CSV file '{path}': {exc}"
       ) from exc
   if dataframe.empty:
       raise DataIngestionError(f"Input file contains no data rows: {path}")
   return dataframe

def main():
   """Run a sample ingestion using the repository's oncology dataset."""
   try:
       dataframe = load_data(RAW_DATA_PATH)
   except (DataIngestionError, FileNotFoundError) as exc:
       raise SystemExit(f"Data ingestion failed: {exc}") from exc
   print("Oncology data loaded successfully.")
   print(f"Rows: {dataframe.shape[0]}")
   print(f"Columns: {dataframe.shape[1]}")
   print("\nColumn names:")
   print(dataframe.columns.tolist())
   print("\nFirst 5 rows:")
   print(dataframe.head())

if __name__ == "__main__":
   main()
