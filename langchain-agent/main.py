"""
FastAPI → Simple Oracle Database Query Handler → Ollama + Oracle Database
Fixed version with reliable query handling instead of problematic ReAct agent
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
from langchain_core.tools import tool
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

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
        self.service = os.getenv('ORACLE_SERVICE', 'XEPDB1')
        
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

# ───────────── 2. ORACLE DATABASE TOOLS ─────────────────────────────────

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
def get_weather(location: str) -> str:
    """Return a (fake) weather report for the given location."""
    return f"It's always sunny in {location}."

# ───────────── 3. SIMPLE QUERY HANDLER (REPLACES COMPLEX AGENT) ──────────

def simple_query_handler(user_prompt: str) -> str:
    """Simple rule-based query handler that works reliably."""
    prompt_lower = user_prompt.lower()
    
    try:
        # Products queries
        if any(word in prompt_lower for word in ['product', 'inventory', 'catalog', 'sell', 'stock', 'item']):
            if 'low stock' in prompt_lower:
                result = query_products_table("low stock products")
            elif 'category' in prompt_lower or 'categories' in prompt_lower:
                result = query_products_table("products by category")  
            else:
                result = query_products_table("show all products")
            return f"Here are our products:\n\n{result}"
        
        # Orders/Revenue queries  
        elif any(word in prompt_lower for word in ['order', 'sales', 'revenue', 'completed', 'money', 'total']):
            if 'revenue' in prompt_lower or 'total' in prompt_lower or 'money' in prompt_lower:
                result = query_orders_table("total revenue from completed orders")
            elif 'pending' in prompt_lower:
                result = query_orders_table("pending orders")
            elif 'recent' in prompt_lower:
                result = query_orders_table("recent orders")
            else:
                result = query_orders_table("show all orders")
            return f"Here are our orders:\n\n{result}"
        
        # Users queries
        elif any(word in prompt_lower for word in ['user', 'customer', 'account', 'client']):
            if 'active' in prompt_lower:
                result = query_users_table("active users")
            elif 'count' in prompt_lower or 'how many' in prompt_lower:
                result = query_users_table("total users") 
            elif 'recent' in prompt_lower:
                result = query_users_table("recent users")
            else:
                result = query_users_table("show all users")
            return f"Here are our users:\n\n{result}"
        
        # Analytics queries
        elif any(word in prompt_lower for word in ['analytics', 'metrics', 'report', 'dashboard', 'business', 'kpi']):
            if 'comprehensive' in prompt_lower or 'full' in prompt_lower:
                result = query_analytics_dashboard("comprehensive business report")
            else:
                result = query_analytics_dashboard("key metrics")
            return f"Here's your business analytics:\n\n{result}"
        
        # Weather queries (for testing)
        elif 'weather' in prompt_lower:
            location = "your location"
            if 'in' in prompt_lower:
                parts = prompt_lower.split('in')
                if len(parts) > 1:
                    location = parts[-1].strip()
            result = get_weather(location)
            return result
        
        # Default: try to determine context and provide helpful response
        else:
            return f"""I can help you with business data queries! Try asking:

📦 **Products**: "What products do we sell?", "Show me low stock items", "List products by category"
💰 **Sales**: "What's our total revenue?", "Show pending orders", "Recent sales"
👥 **Users**: "How many customers do we have?", "Show active users", "Recent user registrations"
📊 **Analytics**: "Give me a business report", "Show key metrics", "Comprehensive analytics"
🌤️ **Weather**: "What's the weather in Tokyo?" (demo feature)

Your Oracle database is connected and ready with real data!"""
            
    except Exception as e:
        root_log.error(f"Query handler error: {e}")
        return f"Error accessing database: {str(e)}\n\nPlease try a simpler query or check the database connection."

# ───────────── 4. FALLBACK LLM FOR NON-DATA QUERIES ───────────────────────

OLLAMA_BASE = "http://ollama:11434"
OLLAMA_MODEL = "mistral"

try:
    llm = ChatOllama(base_url=OLLAMA_BASE, model=OLLAMA_MODEL, verbose=False)
except Exception as e:
    root_log.warning(f"Could not initialize Ollama LLM: {e}")
    llm = None

def run_agent(user_prompt: str) -> str:
    """Main query handler - tries database first, falls back to LLM."""
    
    # Check if this looks like a data query
    data_keywords = ['product', 'order', 'user', 'customer', 'revenue', 'sales', 'analytics', 'report', 'inventory', 'stock']
    prompt_lower = user_prompt.lower()
    
    if any(keyword in prompt_lower for keyword in data_keywords):
        # This looks like a database query
        return simple_query_handler(user_prompt)
    else:
        # This looks like a general conversation - try LLM if available
        if llm:
            try:
                response = llm.invoke(user_prompt)
                return response.content
            except Exception as e:
                root_log.warning(f"LLM error: {e}")
                return simple_query_handler(user_prompt)  # Fallback to data handler
        else:
            return simple_query_handler(user_prompt)  # No LLM available

# ───────────── 5. FASTAPI SERVICE ──────────────────────────────────────
app = FastAPI(title="Oracle Database Query API")

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

@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    root_log.info("📥 Incoming query")

    messages: List[Dict[str, str]] = body.get("messages", [])
    if not messages:
        raise HTTPException(400, "Missing 'messages' array")

    user_prompt = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if not user_prompt:
        raise HTTPException(400, "No user message")

    stream = bool(body.get("stream", False))
    
    # Process the query
    answer_text = await asyncio.get_event_loop().run_in_executor(
        None, lambda: run_agent(user_prompt)
    )

    if not stream:
        return JSONResponse(wrap_openai(answer_text))

    # Simple SSE stream
    async def event_stream():
        words = answer_text.split()
        for i, word in enumerate(words):
            chunk = {
                "id": None,
                "object": "chat.completion.chunk",
                "model": OLLAMA_MODEL,
                "choices": [{
                    "index": 0,
                    "delta": {"content": word + " "},
                    "finish_reason": None,
                }],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0.01)  # Small delay for streaming effect

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

# Debug endpoints to test tools directly
@app.get("/test-products")
def test_products():
    try:
        result = query_products_table("show all products")
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/test-orders") 
def test_orders():
    try:
        result = query_orders_table("show all orders")
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/test-users")
def test_users():
    try:
        result = query_users_table("show all users")
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/test-analytics")
def test_analytics():
    try:
        result = query_analytics_dashboard("comprehensive business report")
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}