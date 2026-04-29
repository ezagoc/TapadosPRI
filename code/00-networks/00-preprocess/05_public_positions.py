"""
Build the public (elected) positions dataset from parsed_positions.csv.

Filters to field_type == 'public_positions' and prepares columns for further
variable extraction such as:
  - chamber (Senate / Chamber of Deputies / state legislature / ...)
  - role (senator, federal deputy, local deputy, governor, mayor, ...)
  - state represented
  - district / plurality / proportional representation
  - years in office

Input:  data/parsed_positions.csv
Output: data/public_positions.csv
"""

import pandas as pd
from config import PARSED_POSITIONS_CSV, PUBLIC_POSITIONS_CSV

# ---------------------------------------------------------------------------
# Load and filter
# ---------------------------------------------------------------------------
df = pd.read_csv(PARSED_POSITIONS_CSV)
pub = df[df["field_type"] == "public_positions"].copy()
pub = pub.reset_index(drop=True)

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
pub = pub[cols]

# ---------------------------------------------------------------------------
# TODO: variable extraction
# ---------------------------------------------------------------------------
# pub["chamber"]            = ...  # Senate / Chamber of Deputies / state leg / ...
# pub["office"]             = ...  # senator / federal_deputy / governor / mayor / ...
# pub["state_represented"]  = ...  # state (already in state col, but might differ)
# pub["plurinominal"]       = ...  # True if proportional-representation seat

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
pub.to_csv(PUBLIC_POSITIONS_CSV, index=False)
print(f"Public position records: {len(pub)}")
print(f"Saved to {PUBLIC_POSITIONS_CSV}")
