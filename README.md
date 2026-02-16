# Qbit Backend

Production-ready FastAPI backend for the Qbit AI-powered full-stack application generator.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- MongoDB Atlas account (free M0 tier)
- Redis Cloud account (free 30MB tier)
- Groq API keys (free tier: 30 RPM)
- Cerebras API keys (free tier: 60 RPM)
- E2B API key

### Installation

1. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

4. **Run the application**
```bash
# Development
uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Environment Variables

See `.env.example` for all required configuration. Key variables:

- `MONGODB_URI` - MongoDB Atlas connection string
- `REDIS_URL` - Redis Cloud connection URL
- `GROQ_API_KEYS` - Comma-separated Groq API keys for rotation
- `CEREBRAS_API_KEYS` - Comma-separated Cerebras API keys
- `E2B_API_KEY` - E2B sandbox API key
- `JWT_SECRET_KEY` - Secret for JWT token signing
- `GITHUB_CLIENT_ID` - GitHub OAuth client ID
- `GITHUB_CLIENT_SECRET` - GitHub OAuth secret

## 📁 Project Structure

```
backend/
├── main.py                     # FastAPI application entry point
├── config/
│   ├── settings.py            # Pydantic settings management
├── database/
│   ├── connection.py          # MongoDB connection manager
│   ├── redis_client.py        # Redis client
│   └── schemas.py             # Pydantic models for all collections
├── auth/
│   ├── jwt_utils.py           # JWT token creation/validation
│   ├── password.py            # Password hashing with bcrypt
│   ├── github_oauth.py        # GitHub OAuth integration
│   └── dependencies.py        # FastAPI auth dependencies
├── credits/
│   └── credit_manager.py      # Credit deduction and rollback
├── rotation/
│   └── key_manager.py         # API key rotation with health checks
├── hub/
│   ├── hub.py                 # Central Hub orchestrator
│   └── prompts.py             # System prompts
├── agents/
│   └── fullstack_agent/
│       ├── fullstack_agent.py # Full Stack Agent
│       └── prompts.py         # Agent prompts
├── routes/
│   ├── auth_routes.py         # Authentication endpoints
│   ├── user_routes.py         # User profile & credits
│   ├── project_routes.py      # Project management
│   └── generation_routes.py  # WebSocket code generation
├── websocket/
│   └── manager.py             # WebSocket connection manager
├── utils/
│   ├── file_utils.py          # File operations
│   └── patch_utils.py         # Patch application
└── tasks/
    └── celery_tasks.py        # Background tasks
```

## 🔌 API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register with email/password
- `POST /api/v1/auth/login` - Login with email/password
- `GET /api/v1/auth/github/login` - Initiate GitHub OAuth
- `GET /api/v1/auth/github/callback` - GitHub OAuth callback

### User
- `GET /api/v1/user/me` - Get current user profile
- `GET /api/v1/user/credits` - Get credit balance
- `GET /api/v1/user/credits/history` - Get transaction history

### Projects
- `GET /api/v1/projects` - List user projects
- `GET /api/v1/projects/{project_id}` - Get project details
- `DELETE /api/v1/projects/{project_id}` - Delete project
- `GET /api/v1/projects/{project_id}/snapshots` - List snapshots
- `POST /api/v1/projects/{project_id}/rollback` - Rollback to snapshot

### Code Generation (WebSocket)
- `WS /ws/generate?token={jwt}` - Real-time code generation

### Health & Info
- `GET /` - API information
- `GET /health` - Health check (MongoDB + Redis)
- `GET /docs` - OpenAPI documentation (dev only)

## 🏗️ Architecture

### Multi-Agent Orchestration
- **Central Hub** (Groq `openai/gpt-oss-120b`)
  - Intent classification
  - SCP generation
  - Complexity assessment
  
- **Full Stack Agent** (Cerebras `qwen-3-32b`)
  - Code generation
  - Diff/patch creation for follow-ups

### State Management
- **Stateless Agents** - No internal state
- **Stateful System** - State in MongoDB + Redis
- **Single LLM Call per Request** - Efficiency rule

### API Key Rotation
- Round-robin pool with health tracking
- Automatic blacklisting on invalid keys
- RPM limit tracking per key

### Credit System
- Atomic deduction with MongoDB
- Automatic rollback on failure
- Transaction logging

### WebSocket Flow
1. Client connects with JWT token
2. Sends `generate_code` message with prompt
3. Receives real-time progress updates:
   - `orchestration` (10%)
   - `credit_check` (25%)
   - `code_generation` (40%)
   - `database_save` (70%)
   - `complete` (100%)
4. Final `code_generation_complete` event with project details

## 🧪 Development

### Running Tests
```bash
pytest
```

### Code Quality
```bash
# Format code
black .

# Linting
ruff check .
```

### Background Tasks
```bash
# Start Celery worker
celery -A tasks.celery_tasks worker --loglevel=info

# Start Celery beat (scheduler)
celery -A tasks.celery_tasks beat --loglevel=info

# Monitor with Flower
celery -A tasks.celery_tasks flower
```

## 📊 Monitoring

Health check endpoint provides:
- MongoDB connection status
- Redis connection status
- Application version and environment

## 🔒 Security

- JWT authentication with 7-day expiration
- Bcrypt password hashing (12 rounds)
- Rate limiting per user and IP
- CORS configuration
- MongoDB user data isolation
- Sensitive data in environment variables

## 📝 Logging

Structured logging with `structlog`:
- JSON format in production
- Console format in development
- All critical events logged with context

## 🚢 Deployment

1. Set `ENVIRONMENT=production` in `.env`
2. Use production MongoDB and Redis instances
3. Set strong `JWT_SECRET_KEY`
4. Configure CORS for production frontend URL
5. Use process manager (e.g., systemd, PM2)
6. Set up reverse proxy (nginx, Caddy)
7. Enable HTTPS

### Example Production Command
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level info
```

## 📄 License

MIT

## 👥 Contributing

This is a proprietary project. See contribution guidelines in main repository.
