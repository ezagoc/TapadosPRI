"""
Build the other positions dataset from parsed_positions.csv.

Filters to field_type == 'other_positions' and prepares columns for further
variable extraction such as:
  - sector (business, academic, military, religious, ...)
  - organization
  - role / title
  - years active

Input:  data/parsed_positions.csv
Output: data/other_positions.csv
"""

import pandas as pd
from config import PARSED_POSITIONS_CSV, OTHER_POSITIONS_CSV

# ---------------------------------------------------------------------------
# Load and filter
# ---------------------------------------------------------------------------
df = pd.read_csv(PARSED_POSITIONS_CSV)
other = df[df["field_type"] == "other_positions"].copy()
other = other.reset_index(drop=True)

# ---------------------------------------------------------------------------
# Column selection
# ---------------------------------------------------------------------------
cols = [
    "record_id", "person_id", "person_name",
    "role_text_raw", "role_text",
    "position_title",
    "organization",
    "state",
    "year_start", "year_end",
    "birth_date_clean", "birth_date_precision",
]
other = other[cols]

# ---------------------------------------------------------------------------
# TODO: variable extraction
# ---------------------------------------------------------------------------
# other["sector"]      = ...  # business / academic / military / media / ...
# other["org_type"]    = ...  # private_company / ngo / university / ...

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
other.to_csv(OTHER_POSITIONS_CSV, index=False)
print(f"Other position records: {len(other)}")
print(f"Saved to {OTHER_POSITIONS_CSV}")
