"""
F1 Pit Wall Agent - Flask Web Application (FIXED VERSION)
"""

import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
import anthropic
import secrets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates')

# ============================================================================
# COMPREHENSIVE PERMISSION & SECURITY FIX
# ============================================================================

# 1. CORS - Allow Everything
CORS(app, 
     origins="*",
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
     methods=["GET", "POST", "OPTIONS", "PUT", "DELETE", "PATCH"],
     supports_credentials=True,
     max_age=86400)

# 2. Session Config
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True

Session(app)

# ============================================================================
# GLOBAL SECURITY HEADERS
# ============================================================================

@app.before_request
def handle_preflight():
    """Handle CORS preflight"""
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response, 200


@app.after_request
def apply_security_headers(response):
    """Apply security headers"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Expose-Headers'] = 'Content-Type, Content-Length'
    
    response.headers['Content-Security-Policy'] = (
        "default-src *; "
        "script-src * 'unsafe-inline' 'unsafe-eval'; "
        "style-src * 'unsafe-inline'; "
        "img-src * data: blob:; "
        "font-src * data:; "
        "connect-src * wss: ws:; "
        "frame-src *; "
        "object-src 'none'; "
    )
    
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'no-referrer-when-downgrade'
    response.headers['Permissions-Policy'] = 'geolocation=*, microphone=*, camera=*'
    
    return response


# ============================================================================
# ANTHROPIC CLIENT - FIX
# ============================================================================

api_key = os.environ.get('ANTHROPIC_API_KEY')

logger.info(f"🔑 API Key Status: {'✅ Set' if api_key else '❌ NOT SET'}")

client = None
if api_key:
    try:
        client = anthropic.Anthropic(api_key=api_key)
        logger.info("✅ Anthropic client initialized successfully")
    except Exception as e:
        logger.error(f"❌ Error initializing Anthropic: {e}")
else:
    logger.warning("⚠️ ANTHROPIC_API_KEY environment variable not set!")

SYSTEM_PROMPT = """You are "Pit Wall", an expert F1 race weekend summarizer AI agent. Your job is to fetch the latest F1 race weekend information and present it in a clear, structured, exciting way.

When asked about a day or session:
- FRIDAY: Cover FP1 and FP2 — pace leaders, fastest times, any incidents, tire compounds tried, team notes
- SATURDAY: Cover FP3 (if standard weekend) and Qualifying — pole sitter, front row, top 10 grid, any eliminated drivers, lap times, key moments
- SUNDAY: Cover the full race — winner, podium top 3, full race story, key battles, safety cars, retirements, fastest lap, championship points impact
- FULL WEEKEND: Combine all of the above in a structured narrative

Format your responses with clear sections, use emojis for visual scanning (🥇🥈🥉🏎️⚡🔧🚨🏆), and include key lap times and gaps where relevant. Be enthusiastic but precise. Always mention the most recent race that has happened.

Today is {today_date}. Always search for the LATEST/MOST RECENT F1 race weekend results.""".format(
    today_date=datetime.now().strftime("%A, %B %d, %Y")
)


class F1Agent:
    """F1 Pit Wall Agent"""
    
    def __init__(self):
        self.conversation_history = []
        self.current_day = "weekend"
        self.session_map = {
            "friday": "Friday practice sessions (FP1, FP2)",
            "saturday": "Saturday qualifying (and FP3 if standard weekend)",
            "sunday": "Sunday's race",
            "weekend": "Full race weekend — Friday, Saturday, and Sunday"
        }
    
    def set_day(self, day: str) -> bool:
        if day.lower() in self.session_map:
            self.current_day = day.lower()
            return True
        return False
    
    def query(self, user_input: str) -> dict:
        if not client:
            return {
                "success": False,
                "error": "❌ API client not initialized. ANTHROPIC_API_KEY is not set. Please add it to environment variables."
            }
        
        if not user_input or not user_input.strip():
            return {
                "success": False,
                "error": "❌ Query cannot be empty. Please type something."
            }
        
        try:
            logger.info(f"🎯 Processing query for: {self.current_day}")
            
            day_context = f"[Session: {self.session_map[self.current_day]}]\n\n"
            contextualized = day_context + user_input.strip()
            
            self.conversation_history.append({
                "role": "user",
                "content": contextualized
            })
            
            logger.info(f"📡 Calling Claude API...")
            
            response = client.messages.create(
                model="claude-opus-4-1-20250805",
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=self.conversation_history
            )
            
            logger.info(f"✅ Got response from Claude")
            
            reply_text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    reply_text += block.text
            
            if not reply_text:
                reply_text = "🔄 Claude didn't return a text response. Please try again."
            
            self.conversation_history.append({
                "role": "assistant",
                "content": reply_text
            })
            
            return {
                "success": True,
                "response": reply_text,
                "day": self.current_day
            }
        
        except anthropic.APIError as e:
            error_msg = f"❌ Anthropic API Error: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}


# ============================================================================
# ROUTES
# ============================================================================

@app.route('/')
def index():
    """Home page"""
    logger.info(f"📄 Serving index page")
    return render_template('index.html')


@app.route('/api/query', methods=['POST', 'OPTIONS'])
def api_query():
    """API endpoint for queries"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        # Get JSON data
        data = request.get_json(silent=True)
        
        if data is None:
            logger.warning("⚠️ No JSON data received")
            return jsonify({"success": False, "error": "❌ No data sent. Please send JSON."}), 400
        
        user_input = data.get('query', '').strip()
        
        if not user_input:
            logger.warning("⚠️ Empty query received")
            return jsonify({"success": False, "error": "❌ Query is empty"}), 400
        
        logger.info(f"🎤 Query received: {user_input[:50]}...")
        
        # Get or create agent
        agent_data = session.get('agent_data', {'history': [], 'day': 'weekend'})
        
        agent = F1Agent()
        agent.conversation_history = agent_data.get('history', [])
        agent.current_day = agent_data.get('day', 'weekend')
        
        # Query
        result = agent.query(user_input)
        
        # Save state
        if result['success']:
            session['agent_data'] = {
                'history': agent.conversation_history,
                'day': agent.current_day
            }
            logger.info(f"💾 Session saved")
        
        return jsonify(result)
    
    except Exception as e:
        error_msg = f"❌ Server error: {str(e)}"
        logger.error(error_msg)
        return jsonify({"success": False, "error": error_msg}), 500


@app.route('/api/set-day', methods=['POST', 'OPTIONS'])
def api_set_day():
    """Set day focus"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json(silent=True)
        
        if not data:
            return jsonify({"success": False, "error": "❌ No data"}), 400
        
        day = data.get('day', '').lower()
        logger.info(f"📍 Setting day to: {day}")
        
        agent_data = session.get('agent_data', {'history': [], 'day': 'weekend'})
        agent = F1Agent()
        
        if agent.set_day(day):
            agent_data['day'] = day
            session['agent_data'] = agent_data
            return jsonify({"success": True, "day": day})
        
        return jsonify({"success": False, "error": f"❌ Invalid day: {day}"}), 400
    
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/reset', methods=['POST', 'OPTIONS'])
def api_reset():
    """Reset conversation"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        session['agent_data'] = {'history': [], 'day': 'weekend'}
        logger.info("🔄 Conversation reset")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    """Health check"""
    if request.method == 'OPTIONS':
        return '', 204
    
    return jsonify({
        "status": "healthy",
        "service": "F1 Pit Wall Agent",
        "api_ready": bool(client),
        "api_key_set": bool(api_key)
    })


@app.route('/api/status', methods=['GET', 'OPTIONS'])
def status():
    """API status"""
    if request.method == 'OPTIONS':
        return '', 204
    
    return jsonify({
        "status": "ready",
        "api_configured": bool(client),
        "timestamp": datetime.now().isoformat()
    })


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(400)
def bad_request(e):
    logger.error(f"400 Bad Request: {e}")
    return jsonify({"error": "❌ Bad request"}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "❌ Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "❌ Method not allowed"}), 405

@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 Server Error: {e}")
    return jsonify({"error": "❌ Internal server error"}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    logger.info(f"\n{'='*50}")
    logger.info(f"🚀 F1 PIT WALL STARTING")
    logger.info(f"{'='*50}")
    logger.info(f"Port: {port}")
    logger.info(f"Debug: {debug}")
    logger.info(f"API Key: {'✅ SET' if api_key else '❌ NOT SET'}")
    logger.info(f"{'='*50}\n")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        use_reloader=False,
        threaded=True
    )