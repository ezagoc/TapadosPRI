"""
Build the birthplace dataset from parsed_positions.csv.

Filters to field_type == 'birthplace' and prepares columns for further
variable extraction such as:
  - city
  - state (already extracted)
  - region
  - foreign-born flag

Input:  data/parsed_positions.csv
Output: data/birthplace.csv
"""

import pandas as pd
from config import PARSED_POSITIONS_CSV, BIRTHPLACE_CSV

# ---------------------------------------------------------------------------
# Load and filter
# ---------------------------------------------------------------------------
df = pd.read_csv(PARSED_POSITIONS_CSV)
bp = df[df["field_type"] == "birthplace"].copy()
bp = bp.reset_index(drop=True)

# ---------------------------------------------------------------------------
# Column selection
# ---------------------------------------------------------------------------
cols = [
    "record_id", "person_id", "person_name",
    "role_text_raw",
    "state",
    "birth_date_clean", "birth_date_precision",
]
bp = bp[cols]

# ---------------------------------------------------------------------------
# TODO: variable extraction
# ---------------------------------------------------------------------------
# bp["city"]         = ...  # city of birth
# bp["foreign_born"] = ...  # True if not a Mexican state
# bp["region"]       = ...  # North / Center / South / etc.

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
bp.to_csv(BIRTHPLACE_CSV, index=False)
print(f"Birthplace records: {len(bp)}")
print(f"Saved to {BIRTHPLACE_CSV}")
