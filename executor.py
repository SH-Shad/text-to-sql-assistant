import sqlite3
import pandas as pd
import os
import re

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "analytics.db")

# ── Security: allowed statement types ────────────────────────────────────────

ALLOWED_STATEMENTS = {"select"}

def is_safe_query(sql: str) -> bool:
    """
    Rejects any SQL that isn't a plain SELECT statement.
    Strips comments first so tricks like `--DROP` don't sneak through.
    Also blocks multiple statements like: SELECT ...; DROP TABLE ...;
    """
    # Remove single-line comments (-- ...)
    sql_clean = re.sub(r"--[^\n]*", "", sql)
    # Remove multi-line comments (/* ... */)
    sql_clean = re.sub(r"/\*.*?\*/", "", sql_clean, flags=re.DOTALL)

    # Block multiple statements (semicolon not at the end)
    if sql_clean.strip().rstrip(";").find(";") != -1:
        return False

    first_word = sql_clean.strip().split()[0].lower() if sql_clean.strip() else ""
    return first_word in ALLOWED_STATEMENTS


# ── Query validation ──────────────────────────────────────────────────────────

def validate_sql(sql: str, db_path: str = DB_PATH) -> dict:
    """
    Uses SQLite's EXPLAIN to validate syntax WITHOUT executing the query.
    Returns { valid: bool, error: str|None }

    Why EXPLAIN? It parses and validates the query plan without touching data.
    Much safer than running the query to check if it works.
    """
    try:
        conn = sqlite3.connect(db_path)
        cur  = conn.cursor()
        cur.execute(f"EXPLAIN {sql}")
        conn.close()
        return {"valid": True, "error": None}
    except sqlite3.Error as e:
        return {"valid": False, "error": str(e)}
    finally:
        conn.close() if 'conn' in dir() else None


# ── Main execution function ───────────────────────────────────────────────────

def execute_query(sql: str, db_path: str = DB_PATH) -> dict:
    """
    Executes a SQL query against the database and returns:
    {
        "df":           pandas DataFrame | None,
        "row_count":    int,
        "col_count":    int,
        "columns":      list[str],
        "error":        str | None,
        "error_type":   str | None,   # 'security', 'syntax', 'runtime', 'empty'
        "sql_executed": str,
    }

    Always returns a dict — never raises an exception to the caller.
    """
    result_template = {
        "df":           None,
        "row_count":    0,
        "col_count":    0,
        "columns":      [],
        "error":        None,
        "error_type":   None,
        "sql_executed": sql,
    }

    # ── Guard 1: empty SQL ────────────────────────────────────────────────────
    if not sql or not sql.strip():
        return {**result_template,
                "error": "No SQL query to execute.",
                "error_type": "runtime"}

    # ── Guard 2: security check ───────────────────────────────────────────────
    if not is_safe_query(sql):
        return {**result_template,
                "error": "Only SELECT queries are allowed for security reasons.",
                "error_type": "security"}

    # ── Guard 3: syntax validation (before touching real data) ────────────────
    validation = validate_sql(sql, db_path)
    if not validation["valid"]:
        return {**result_template,
                "error": f"SQL syntax error: {validation['error']}",
                "error_type": "syntax"}

    # ── Execute ───────────────────────────────────────────────────────────────
    try:
        conn = sqlite3.connect(db_path)

        # Use row_factory for column name access
        conn.row_factory = sqlite3.Row

        df = pd.read_sql_query(sql, conn)
        conn.close()

        # ── Guard 4: empty results ────────────────────────────────────────────
        if df.empty:
            return {**result_template,
                    "error": "The query ran successfully but returned no results.",
                    "error_type": "empty",
                    "sql_executed": sql}

        return {
            "df":           df,
            "row_count":    len(df),
            "col_count":    len(df.columns),
            "columns":      list(df.columns),
            "error":        None,
            "error_type":   None,
            "sql_executed": sql,
        }

    except sqlite3.Error as e:
        return {**result_template,
                "error": f"Database error: {str(e)}",
                "error_type": "runtime"}

    except Exception as e:
        return {**result_template,
                "error": f"Unexpected error: {str(e)}",
                "error_type": "runtime"}