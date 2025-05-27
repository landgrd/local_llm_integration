"""
FastAPI → LangGraph ReAct Agent → Ollama + Oracle Database
Enhanced with Oracle Cloud Database connectivity and table-specific authentication
"""

import os, asyncio, json, uuid, logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

import oracledb
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

from langchain_ollama import ChatOllama
from langchain.agents.react.agent import create_react_agent
from langchain.agents import AgentExecutor
from langchain_core.tools import tool
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.callbacks.base import BaseCallbackHandler
from langchain import hub

# ───────────── 0. ENV & LOGGING ────────────────────────────────────────
load_dotenv()
load_dotenv('.env.oracle')  # Load Oracle-specific config

os.environ["LANGCHAIN_TRACING_V2"] = "false"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
root_log = logging.getLogger()
root_log.setLevel(logging.INFO)

# ───────────── 1. ORACLE DATABASE CONNECTION MANAGER ────────────────────
class OracleConnectionManager:
    def __init__(self):
        self.demo_mode = os.getenv('DEMO_MODE', 'true').lower() == 'true'
        self.host = os.getenv('ORACLE_HOST', 'oracle-demo')
        self.port = int(os.getenv('ORACLE_PORT', '1521'))
        self.service = os.getenv('ORACLE_SERVICE', 'XE')
        
        # Table-specific credentials
        self.table_credentials = {
            'users': {
                'username': 'users_reader',
                'password': os.getenv('ORACLE_TABLE_USERS_PASSWORD', 'UsersTable123')
            },
            'orders': {
                'username': 'orders_reader', 
                'password': os.getenv('ORACLE_TABLE_ORDERS_PASSWORD', 'OrdersTable123')
            },
            'products': {
                'username': 'products_reader',
                'password': os.getenv('ORACLE_TABLE_PRODUCTS_PASSWORD', 'ProductsTable123')
            },
            'analytics': {
                'username': 'analytics_reader',
                'password': os.getenv('ORACLE_TABLE_ANALYTICS_PASSWORD', 'AnalyticsTable123')
            }
        }
        
        root_log.info(f"Oracle Manager initialized - Demo Mode: {self.demo_mode}")

    def get_connection_string(self, table_context: str = 'analytics') -> str:
        """Get Oracle connection string for specific table context."""
        creds = self.table_credentials.get(table_context, self.table_credentials['analytics'])
        
        if self.demo_mode:
            # Use explicit service_name parameter to avoid SID interpretation
            return f"oracle+oracledb://{creds['username']}:{creds['password']}@{self.host}:{self.port}/?service_name={self.service}"
        else:
            # Production would use wallet authentication
            wallet_path = os.getenv('ORACLE_WALLET_PATH', '/app/oracle-wallets/production')
            return f"oracle+oracledb://{creds['username']}:{creds['password']}@{self.host}:{self.port}/?service_name={self.service}&wallet_location={wallet_path}"

    def execute_query(self, sql: str, table_context: str = 'analytics') -> pd.DataFrame:
        """Execute SQL query with appropriate table context."""
        try:
            connection_string = self.get_connection_string(table_context)
            engine = create_engine(connection_string)
            
            root_log.info(f"Executing query on {table_context} context: {sql[:100]}...")
            
            with engine.connect() as conn:
                result = pd.read_sql(text(sql), conn)
                
            root_log.info(f"Query returned {len(result)} rows")
            return result
            
        except Exception as e:
            root_log.error(f"Database query failed: {e}")
            raise e

# Initialize Oracle manager
oracle_manager = OracleConnectionManager()

# ───────────── 2. CONSOLE TRACE CALLBACK ───────────────────────────────
class AgentTrace(BaseCallbackHandler):
    def _log(self, msg: str):
        root_log.info(msg)

    def on_agent_action(self, action, **_):
        self._log(f"🤖 ACTION   → {action.tool} | input={action.tool_input}")

    def on_tool_start(self, *, tool, **_):
        self._log(f"🔧   → running tool '{tool}'")

    def on_tool_end(self, output, **_):
        self._log(f"🔧   ← tool result: {str(output)[:200]}")

    def on_agent_finish(self, finish, **_):
        self._log(f"🏁 FINISH    : {finish.return_values}")

# ───────────── 3. ORACLE DATABASE TOOLS ─────────────────────────────────

@tool
def query_users_table(query_description: str) -> str:
    """
    Query the users table. Use this for questions about users, customers, accounts.
    Args:
        query_description: Natural language description of what you want to find
    """
    try:
        # Simple mapping of common queries to SQL
        if "active users" in query_description.lower():
            sql = "SELECT COUNT(*) as active_count FROM users WHERE status = 'ACTIVE'"
        elif "total users" in query_description.lower() or "count" in query_description.lower():
            sql = "SELECT COUNT(*) as total_users FROM users"
        elif "recent users" in query_description.lower():
            sql = "SELECT username, email, created_date FROM users WHERE created_date >= SYSDATE - 30 ORDER BY created_date DESC"
        else:
            sql = "SELECT user_id, username, email, first_name, last_name, status FROM users"
            
        result = oracle_manager.execute_query(sql, 'users')
        return f"Users Query Result:\n{result.to_string()}"
        
    except Exception as e:
        return f"Error querying users table: {str(e)}"

@tool  
def query_orders_table(query_description: str) -> str:
    """
    Query the orders table. Use this for questions about orders, sales, transactions.
    Args:
        query_description: Natural language description of what you want to find
    """
    try:
        if "recent orders" in query_description.lower():
            sql = "SELECT order_id, user_id, total_amount, order_date, status FROM orders WHERE order_date >= SYSDATE - 7 ORDER BY order_date DESC"
        elif "total sales" in query_description.lower() or "revenue" in query_description.lower():
            sql = "SELECT SUM(total_amount) as total_revenue, COUNT(*) as order_count FROM orders WHERE status = 'COMPLETED'"
        elif "pending orders" in query_description.lower():
            sql = "SELECT order_id, user_id, total_amount, order_date FROM orders WHERE status = 'PENDING'"
        else:
            sql = "SELECT order_id, user_id, product_id, quantity, total_amount, status FROM orders"
            
        result = oracle_manager.execute_query(sql, 'orders')
        return f"Orders Query Result:\n{result.to_string()}"
        
    except Exception as e:
        return f"Error querying orders table: {str(e)}"

@tool
def query_products_table(query_description: str) -> str:
    """
    Query the products table. Use this for questions about products, inventory, catalog.
    Args:
        query_description: Natural language description of what you want to find
    """
    try:
        if "low stock" in query_description.lower():
            sql = "SELECT product_name, stock_quantity, price FROM products WHERE stock_quantity < 20"
        elif "expensive" in query_description.lower() or "highest price" in query_description.lower():
            sql = "SELECT product_name, price, category FROM products ORDER BY price DESC"
        elif "category" in query_description.lower():
            sql = "SELECT category, COUNT(*) as product_count FROM products GROUP BY category"
        else:
            sql = "SELECT product_id, product_name, category, price, stock_quantity FROM products"
            
        result = oracle_manager.execute_query(sql, 'products')
        return f"Products Query Result:\n{result.to_string()}"
        
    except Exception as e:
        return f"Error querying products table: {str(e)}"

@tool
def query_analytics_dashboard(query_description: str) -> str:
    """
    Query analytics and business intelligence data. Use this for metrics, KPIs, business insights.
    Can also join across multiple tables for comprehensive reporting.
    Args:
        query_description: Natural language description of the analytics you need
    """
    try:
        if "revenue" in query_description.lower():
            sql = "SELECT metric_name, metric_value, metric_date FROM sales_analytics WHERE metric_name = 'Daily Revenue'"
        elif "conversion" in query_description.lower():
            sql = "SELECT metric_name, metric_value, metric_date FROM sales_analytics WHERE metric_name = 'Conversion Rate'"
        elif "user stats" in query_description.lower():
            sql = "SELECT metric_name, metric_value FROM sales_analytics WHERE category = 'USERS'"
        elif "comprehensive" in query_description.lower() or "full report" in query_description.lower():
            # Multi-table analytics (using synonyms created in init script)
            sql = """
            SELECT 
                'Total Users' as metric, COUNT(u.user_id) as value FROM users u
            UNION ALL
            SELECT 
                'Active Users' as metric, COUNT(u.user_id) as value FROM users u WHERE u.status = 'ACTIVE'
            UNION ALL
            SELECT 
                'Total Orders' as metric, COUNT(o.order_id) as value FROM orders o
            UNION ALL
            SELECT 
                'Total Revenue' as metric, SUM(o.total_amount) as value FROM orders o WHERE o.status = 'COMPLETED'
            """
        else:
            sql = "SELECT metric_name, metric_value, metric_date, category FROM sales_analytics"
            
        result = oracle_manager.execute_query(sql, 'analytics')
        return f"Analytics Query Result:\n{result.to_string()}"
        
    except Exception as e:
        return f"Error querying analytics: {str(e)}"

@tool
def execute_custom_sql(sql_query: str, table_context: str = "analytics") -> str:
    """
    Execute a custom SQL query. Use with caution and only for complex queries.
    Args:
        sql_query: The SQL query to execute
        table_context: Which table context to use (users, orders, products, analytics)
    """
    try:
        # Basic SQL injection protection
        dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE']
        if any(keyword in sql_query.upper() for keyword in dangerous_keywords):
            return "Error: Only SELECT queries are allowed"
            
        result = oracle_manager.execute_query(sql_query, table_context)
        return f"Custom Query Result:\n{result.to_string()}"
        
    except Exception as e:
        return f"Error executing custom SQL: {str(e)}"

@tool
def get_weather(location: str) -> str:
    """Return a (fake) weather report for the given location."""
    return f"It's always sunny in {location}."

# ───────────── 4. MODEL & AGENT SETUP ──────────────────────────────────
OLLAMA_BASE = "http://ollama:11434"
OLLAMA_MODEL = "mistral"

llm = ChatOllama(base_url=OLLAMA_BASE, model=OLLAMA_MODEL, verbose=True)
prompt = hub.pull("hwchase17/react")

# All available tools
tools = [
    get_weather,
    query_users_table,
    query_orders_table, 
    query_products_table,
    query_analytics_dashboard,
    execute_custom_sql
]

agent_runnable = create_react_agent(llm, tools, prompt)

agent = AgentExecutor(
    agent=agent_runnable,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=5,  # Increased for complex queries
)

# ───────────── 5. FASTAPI SERVICE ──────────────────────────────────────
app = FastAPI(title="Ollama-Oracle ReAct Gateway")

def wrap_openai(answer: str) -> Dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "model": OLLAMA_MODEL,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": answer},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

def run_agent(user_prompt: str) -> str:
    """Run agent with Oracle database tools; fallback to raw LLM if needed."""
    try:
        result = agent.invoke(
            {"input": user_prompt},
            callbacks=[AgentTrace(), StreamingStdOutCallbackHandler()],
        )
        text = result["output"] if isinstance(result, dict) else str(result)

        if any(k in text.lower() for k in ("unable to answer", "cannot")):
            root_log.info("Agent declined – retrying with direct LLM")
            text = llm.invoke(user_prompt).content
        return text

    except Exception as e:
        root_log.exception("Agent error, using raw LLM instead: %s", e)
        return (
            "⚠️ _Agent failed – showing raw LLM reply_\n\n"
            + llm.invoke(user_prompt).content
        )

@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    root_log.info("📥 Incoming body: %s", json.dumps(body, indent=2)[:1000])

    messages: List[Dict[str, str]] = body.get("messages", [])
    if not messages:
        raise HTTPException(400, "Missing 'messages' array")

    user_prompt = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if not user_prompt:
        raise HTTPException(400, "No user message")

    stream = bool(body.get("stream", False))
    answer_text = await asyncio.get_event_loop().run_in_executor(
        None, lambda: run_agent(user_prompt)
    )

    if not stream:
        return JSONResponse(wrap_openai(answer_text))

    # Simple SSE stream
    async def event_stream():
        for token in answer_text.split():
            chunk = {
                "id": None,
                "object": "chat.completion.chunk",
                "model": OLLAMA_MODEL,
                "choices": [{
                    "index": 0,
                    "delta": {"content": token + " "},
                    "finish_reason": None,
                }],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0)

        yield "data: " + json.dumps({
            "id": None,
            "object": "chat.completion.chunk",
            "model": OLLAMA_MODEL,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
        }) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/health")
def health():
    return {"status": "ok", "demo_mode": oracle_manager.demo_mode}

@app.get("/v1/models")
def list_models():
    """Minimal OpenAI-compatible model list (LibreChat uses this)."""
    models = [
        {"id": "openchat", "object": "model", "owned_by": "local"},
        {"id": "mistral", "object": "model", "owned_by": "local"},
    ]
    return {"object": "list", "data": models}

# Database health check endpoint
@app.get("/db-health")
def db_health():
    try:
        # Test connection to analytics context
        test_query = "SELECT 1 as test FROM dual"
        oracle_manager.execute_query(test_query, 'analytics')
        return {"status": "ok", "database": "connected", "demo_mode": oracle_manager.demo_mode}
    except Exception as e:
        return {"status": "error", "database": "disconnected", "error": str(e)}