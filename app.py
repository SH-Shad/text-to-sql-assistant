import io
import os
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

from core.llm import generate_sql
from core.executor import execute_query
from utils.schema_inspector import get_schema_string

# ── Page config ───────────────────────────────────────────────────────────────
# Must be the very first Streamlit call — nothing st.* before this line
st.set_page_config(
    page_title="Text-to-SQL Analytics Assistant",
    page_icon="🔍",
    layout="wide",
)


# ── Auto-chart engine ─────────────────────────────────────────────────────────
def auto_chart(df: pd.DataFrame):
    """
    Inspects the DataFrame's column types and names to pick the best chart.
    Returns a Plotly figure, or None if no good chart is possible.

    Decision logic (checked in order):
      1. Date/time column + numeric column  → Line chart  (time series)
      2. String column   + numeric column   → Bar chart   (category comparison)
      3. Two numeric columns                → Scatter plot (correlation)
      4. Anything else                      → None
    """
    if df is None or df.empty or len(df.columns) < 2:
        return None

    num_cols = df.select_dtypes(include="number").columns.tolist()
    str_cols = df.select_dtypes(include="object").columns.tolist()

    # Detect time-series columns by name keyword
    date_cols = [
        c for c in str_cols
        if any(kw in c.lower() for kw in ["date", "month", "year", "week", "day", "period", "quarter"])
    ]

    # 1. Line chart ─────────────────────────────────────────────────────────────
    if date_cols and num_cols:
        fig = px.line(
            df,
            x=date_cols[0],
            y=num_cols[0],
            title=f"{num_cols[0].replace('_', ' ').title()} Over Time",
            markers=True,
        )
        fig.update_traces(line_color="#2563EB", marker_color="#2563EB")
        fig.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="#F0F0F0"),
        )
        return fig

    # 2. Bar chart ──────────────────────────────────────────────────────────────
    if str_cols and num_cols:
        fig = px.bar(
            df,
            x=str_cols[0],
            y=num_cols[0],
            title=f"{num_cols[0].replace('_', ' ').title()} by {str_cols[0].replace('_', ' ').title()}",
            color=num_cols[0],
            color_continuous_scale="Blues",
        )
        fig.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            coloraxis_showscale=False,
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="#F0F0F0"),
        )
        return fig

    # 3. Scatter plot ───────────────────────────────────────────────────────────
    if len(num_cols) >= 2:
        fig = px.scatter(
            df,
            x=num_cols[0],
            y=num_cols[1],
            title=f"{num_cols[0].replace('_', ' ').title()} vs {num_cols[1].replace('_', ' ').title()}",
        )
        fig.update_traces(marker_color="#2563EB")
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white")
        return fig

    return None


# ── Session state initialization ──────────────────────────────────────────────
# Only sets default values on first load — never overwrites existing state
defaults = {
    "sql":         None,
    "exec_result": None,
    "question":    "",
    "history":     [],
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:

    st.header("📋 Schema Reference")
    st.markdown("""
**customers**
`customer_id`, `name`, `email`, `region`, `signup_date`

**products**
`product_id`, `name`, `category`, `unit_price`

**orders**
`order_id`, `customer_id`, `order_date`, `status`

**order_items**
`item_id`, `order_id`, `product_id`, `quantity`, `unit_price`

---
**Regions:** North, South, East, West
**Statuses:** completed, returned, pending
**Categories:** Electronics, Clothing, Home, Sports
""")

    st.divider()

    st.header("💡 Try These Questions")

    example_questions = [
        "What are the top 5 products by total revenue?",
        "How many customers are in each region?",
        "Show monthly revenue for 2024",
        "What percentage of orders were returned?",
        "Which category sells the most units?",
        "Who are the top 10 customers by total spend?",
        "What is the average order value by region?",
        "How many orders were placed each quarter in 2023?",
    ]

    for q in example_questions:
        if st.button(q, use_container_width=True, key=f"ex_{q}"):
            st.session_state["question"]    = q
            st.session_state["sql"]         = None
            st.session_state["exec_result"] = None
            st.rerun()

    st.divider()

    if st.session_state["history"]:
        st.header("🕘 Recent Queries")
        for item in reversed(st.session_state["history"][-8:]):
            st.caption(f"• {item}")

        if st.button("Clear History", use_container_width=True):
            st.session_state["history"] = []
            st.rerun()


# ── Main header ───────────────────────────────────────────────────────────────
st.title("🔍 Text-to-SQL Analytics Assistant")
st.caption(
    "Ask a plain English question about the retail database — "
    "get SQL, a results table, and a chart automatically."
)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_query, tab_schema, tab_about = st.tabs(["💬 Query", "🗂️ Schema Explorer", "ℹ️ About"])


# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — QUERY
# ════════════════════════════════════════════════════════════════════════════════
with tab_query:

    st.divider()

    # Empty state — shown before any query is run
    if not st.session_state["sql"]:
        st.markdown("""
        <div style='text-align: center; padding: 3rem 0; color: #888;'>
            <h3 style='color: #555;'>Ask anything about your retail data</h3>
            <p>Try an example from the sidebar, or type your own question below.</p>
        </div>
        """, unsafe_allow_html=True)

    # Question input row
    col_input, col_button = st.columns([5, 1])

    with col_input:
        question = st.text_input(
            label="question",
            value=st.session_state["question"],
            placeholder="e.g. What were the top 3 revenue-generating categories in 2024?",
            label_visibility="collapsed",
        )

    with col_button:
        run_clicked = st.button("Run Query ▶", type="primary", use_container_width=True)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    if run_clicked and question.strip():

        st.session_state["question"] = question

        # Step 1 — Generate SQL
        with st.spinner("🤖 Generating SQL with Llama 3.3 70B..."):
            llm_result = generate_sql(question)

        if llm_result["error"]:
            st.error(f"⚠️ {llm_result['error']}")
            st.session_state["sql"]         = None
            st.session_state["exec_result"] = None
            st.stop()

        st.session_state["sql"] = llm_result["sql"]

        # Step 2 — Execute SQL
        with st.spinner("⚡ Running query against database..."):
            exec_result = execute_query(llm_result["sql"])

        st.session_state["exec_result"] = exec_result

        # Add to history (no duplicates)
        if question not in st.session_state["history"]:
            st.session_state["history"].append(question)

    # ── Results ───────────────────────────────────────────────────────────────
    if st.session_state["sql"]:

        with st.expander("📝 Generated SQL", expanded=True):
            st.code(st.session_state["sql"], language="sql")

        exec_result = st.session_state["exec_result"]

        if exec_result is None:
            st.stop()

        # Error states
        if exec_result["error"]:
            error_type = exec_result["error_type"]

            if error_type == "empty":
                st.info("ℹ️ Query ran successfully but returned no results. Try broadening your question.")
            elif error_type == "security":
                st.error("🔒 Security: only SELECT queries are permitted.")
            elif error_type == "syntax":
                st.warning("⚠️ The generated SQL had a syntax error. Try rephrasing your question.")
                with st.expander("Technical details"):
                    st.caption(exec_result["error"])
            else:
                st.error(f"❌ {exec_result['error']}")

        # Success
        else:
            df = exec_result["df"]

            # Metrics strip
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Rows returned", exec_result["row_count"])
            m2.metric("Columns",       exec_result["col_count"])
            m3.metric("Query status",  "✅ Success")
            m4.metric("Model",         "Llama 3.3 70B")

            st.divider()

            chart = auto_chart(df)

            # Side-by-side table + chart
            if chart:
                col_table, col_chart = st.columns([1, 1])

                with col_table:
                    st.subheader("Results")
                    st.dataframe(df, use_container_width=True, hide_index=True)

                    # Download button
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="⬇️ Download CSV",
                        data=csv_buffer.getvalue(),
                        file_name="query_results.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

                with col_chart:
                    st.subheader("Chart")
                    st.plotly_chart(chart, use_container_width=True)

            # Full-width table (no chart)
            else:
                st.subheader("Results")
                st.dataframe(df, use_container_width=True, hide_index=True)

                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                st.download_button(
                    label="⬇️ Download CSV",
                    data=csv_buffer.getvalue(),
                    file_name="query_results.csv",
                    mime="text/csv",
                )
                st.caption("No chart generated — try a question with a numeric result grouped by a category.")


# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — SCHEMA EXPLORER
# ════════════════════════════════════════════════════════════════════════════════
with tab_schema:

    st.subheader("🗂️ Live Schema Explorer")
    st.caption("This is the exact schema injected into the LLM prompt on every query.")

    st.divider()

    # Raw schema string from your inspector
    schema_str = get_schema_string()
    st.code(schema_str, language="sql")

    st.divider()

    # Table relationship diagram
    st.subheader("Table Relationships")
    st.markdown("""
```
customers (1) ──── (many) orders (1) ──── (many) order_items (many) ──── (1) products
```
- One **customer** can have many **orders**
- One **order** can have many **order_items** (line items)
- Each **order_item** references one **product**
- Revenue = `order_items.quantity × order_items.unit_price`
""")

    st.divider()

    # Live row counts from database
    st.subheader("Dataset Summary")

    db_path = os.path.join("database", "analytics.db")
    conn    = sqlite3.connect(db_path)
    cur     = conn.cursor()

    summary_cols          = st.columns(4)
    tables_and_icons = [
        ("customers",   "👤"),
        ("products",    "📦"),
        ("orders",      "🛒"),
        ("order_items", "📋"),
    ]

    for col, (table, icon) in zip(summary_cols, tables_and_icons):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        col.metric(f"{icon} {table}", f"{count:,} rows")

    conn.close()


# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — ABOUT
# ════════════════════════════════════════════════════════════════════════════════
with tab_about:

    st.subheader("About This Project")
    st.markdown("""
**Text-to-SQL Analytics Assistant** converts plain English questions into SQL queries
and executes them against a retail analytics database — returning results and charts automatically.

---

### Tech Stack
| Layer      | Technology                          |
|------------|-------------------------------------|
| LLM        | Groq API — Llama 3.3 70B            |
| Database   | SQLite (500 orders, 100 customers, 16 products) |
| Backend    | Python — pandas, sqlite3            |
| Frontend   | Streamlit                           |
| Charts     | Plotly Express                      |

---

### How It Works
1. User types a plain English question
2. The app dynamically extracts the live database schema at runtime
3. Schema + question are sent to Llama 3.3 70B via Groq API (temperature = 0)
4. Generated SQL passes through a 4-stage security + validation pipeline
5. Results are returned as a pandas DataFrame
6. Chart type (line / bar / scatter) is auto-selected based on result data shape

---

### Security Pipeline
| Stage | What It Catches |
|-------|----------------|
| 1. Statement allowlist | Blocks DROP, DELETE, INSERT, UPDATE, ALTER |
| 2. Multi-statement check | Blocks `SELECT ...; DROP TABLE ...` injection |
| 3. EXPLAIN pre-validation | Catches SQL syntax errors before execution |
| 4. Empty result handling | Graceful message instead of blank UI |

---

Built by Sajid · UT Arlington Information Systems
""")