import os

# Tests build their own app on an in-memory DB; skip the module-level app.
os.environ["MATRIX_NO_APP"] = "1"
