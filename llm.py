import os
from groq import Groq
from dotenv import load_dotenv
from utils.schema_inspector import get_schema_string, get_sample_values

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL  = "llama-3.3-70b-versatile"


# ── System Prompt Builder ─────────────────────────────────────────────────────

def build_system_prompt() -> str:
    """
    Constructs the full system prompt by injecting the live database schema.
    Called once per query — always reflects current schema state.
    """
    schema  = get_schema_string()
    samples = get_sample_values()

    return f"""You are an expert SQL assistant for a retail analytics database.
Your only job is to convert natural language questions into valid SQLite SQL queries.

## Database Schema
{schema}

## {samples}

## Rules You Must Follow
1. Output ONLY the raw SQL query. No explanations, no markdown, no code fences.
2. Always use proper JOIN syntax — never implicit comma joins.
3. For revenue calculations, always use: order_items.quantity * order_items.unit_price
4. Only query 'completed' orders for revenue metrics unless the user asks otherwise.
5. Use SQLite date functions: strftime('%Y', order_date), strftime('%m', order_date)
6. Always alias aggregated columns with clear names (e.g., AS total_revenue, AS order_count).
7. Limit results to 50 rows unless the user specifies otherwise.
8. If the question is ambiguous or unanswerable with the given schema, output exactly:
   CANNOT_ANSWER

## Date Context
Today's date is 2025-01-01. Use this as reference for relative time questions.

## Examples
Q: How many customers are in each region?
A: SELECT region, COUNT(*) AS customer_count FROM customers GROUP BY region ORDER BY customer_count DESC;

Q: What is the total revenue by product category?
A: SELECT p.category, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
   FROM order_items oi
   JOIN orders o ON oi.order_id = o.order_id
   JOIN products p ON oi.product_id = p.product_id
   WHERE o.status = 'completed'
   GROUP BY p.category
   ORDER BY total_revenue DESC;

Q: Who are the top 5 customers by total spend?
A: SELECT c.name, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_spend
   FROM customers c
   JOIN orders o ON c.customer_id = o.customer_id
   JOIN order_items oi ON o.order_id = oi.order_id
   WHERE o.status = 'completed'
   GROUP BY c.customer_id, c.name
   ORDER BY total_spend DESC
   LIMIT 5;
"""


# ── SQL Extraction Helper ─────────────────────────────────────────────────────

def extract_sql(raw: str) -> str:
    """
    Cleans the LLM response in case it wraps SQL in markdown despite instructions.
    Strips: ```sql ... ```, ``` ... ```, leading/trailing whitespace.
    """
    text = raw.strip()

    # Remove markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first line (```sql or ```) and last line (```)
        lines = lines[1:] if lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        text = "\n".join(lines).strip()

    return text


# ── Main Generation Function ──────────────────────────────────────────────────

def generate_sql(user_question: str) -> dict:
    """
    Takes a natural language question and returns a dict with:
      - sql:      the generated SQL string (or None)
      - error:    error message if something went wrong (or None)
      - raw:      the raw LLM response (for debugging)
    """
    if not user_question.strip():
        return {"sql": None, "error": "Question cannot be empty.", "raw": ""}

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user",   "content": user_question.strip()},
            ],
            temperature=0.0,   # Zero temperature = deterministic, no creativity
            max_tokens=512,
        )

        raw = response.choices[0].message.content.strip()
        sql = extract_sql(raw)

        if sql == "CANNOT_ANSWER":
            return {
                "sql":   None,
                "error": "This question can't be answered with the available data.",
                "raw":   raw,
            }

        return {"sql": sql, "error": None, "raw": raw}

    except Exception as e:
        return {"sql": None, "error": str(e), "raw": ""}