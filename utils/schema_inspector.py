import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "analytics.db")


def get_schema_string(db_path: str = DB_PATH) -> str:
    """
    Connects to the SQLite database and returns a formatted string
    describing all tables, their columns, types, and foreign keys.
    This string gets injected directly into the LLM system prompt.
    """
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    # Get all user-created tables (excluding SQLite internals)
    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    tables = [row[0] for row in cur.fetchall()]

    schema_parts = []

    for table in tables:
        # Get column info: cid, name, type, notnull, default, pk
        cur.execute(f"PRAGMA table_info({table})")
        columns = cur.fetchall()

        # Get foreign key info
        cur.execute(f"PRAGMA foreign_key_list({table})")
        fkeys = cur.fetchall()
        fkey_map = {fk[3]: (fk[2], fk[4]) for fk in fkeys}
        # fkey_map: { local_col: (referenced_table, referenced_col) }

        col_lines = []
        for col in columns:
            _, name, dtype, notnull, _, is_pk = col
            parts = [f"  {name} {dtype}"]
            if is_pk:
                parts.append("PRIMARY KEY")
            if notnull and not is_pk:
                parts.append("NOT NULL")
            if name in fkey_map:
                ref_table, ref_col = fkey_map[name]
                parts.append(f"REFERENCES {ref_table}({ref_col})")
            col_lines.append(" ".join(parts))

        schema_parts.append(
            f"Table: {table}\n" + "\n".join(col_lines)
        )

    conn.close()

    return "\n\n".join(schema_parts)


def get_sample_values(db_path: str = DB_PATH) -> str:
    """
    Returns a few sample values for key categorical columns.
    Helps the LLM use correct filter values (e.g. 'North' not 'north').
    """
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    samples = {}

    categorical_cols = {
        "customers": ["region"],
        "orders":    ["status"],
        "products":  ["category"],
    }

    for table, cols in categorical_cols.items():
        for col in cols:
            cur.execute(f"SELECT DISTINCT {col} FROM {table} ORDER BY {col}")
            vals = [str(row[0]) for row in cur.fetchall()]
            samples[f"{table}.{col}"] = vals

    conn.close()

    lines = [f"  {col}: {', '.join(vals)}" for col, vals in samples.items()]
    return "Known categorical values:\n" + "\n".join(lines)


if __name__ == "__main__":
    print("=== SCHEMA ===")
    print(get_schema_string())
    print("\n=== SAMPLE VALUES ===")
    print(get_sample_values())