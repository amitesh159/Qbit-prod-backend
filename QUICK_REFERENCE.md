# Qbit Render Deployment - Quick Reference

## 🚀 Quick Deploy Commands

### 1. Verify Requirements
```bash
python --version  # Should be 3.11+
pip install -r requirements.txt
```

### 2. Test Locally Before Deploy
```bash
# Set environment variables
cp .env.example .env
# Edit .env with your credentials

# Run locally
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Test health endpoint
curl http://localhost:8000/health
```

### 3. Push to GitHub
```bash
git add .
git commit -m "Ready for Render deployment"
git push origin main
```

---

## 🔑 Required Environment Variables

### Critical (Must Set in Render Dashboard)

| Variable | Example | Where to Get |
|----------|---------|--------------|
| `MONGODB_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/` | MongoDB Atlas → Connect |
| `REDIS_URL` | `redis://default:pass@host:port` | Redis Cloud → Database Details |
| `GROQ_API_KEYS` | `gsk_key1,gsk_key2,gsk_key3` | console.groq.com → API Keys |
| `CEREBRAS_API_KEYS` | `csk_key1,csk_key2` | cerebras.ai → API Keys |
| `E2B_API_KEY` | `e2b_xxxxx` | e2b.dev → Dashboard |
| `JWT_SECRET_KEY` | `64-char-hex-string` | `openssl rand -hex 32` |

### Important (Update for Production)

| Variable | Production Value | Default |
|----------|------------------|---------|
| `ENVIRONMENT` | `production` | `development` |
| `DEBUG` | `false` | `true` |
| `CORS_ORIGINS` | `https://your-frontend.com` | `http://localhost:3000` |
| `SHOW_ERROR_DETAILS` | `false` | `true` |

---

## 📋 Pre-Deployment Checklist

### External Services Setup
- [ ] **MongoDB Atlas**: Free M0 cluster created
  - [ ] Database user created
  - [ ] IP whitelist: `0.0.0.0/0` added
  - [ ] Connection string copied
  
- [ ] **Redis Cloud**: Free 30MB instance created
  - [ ] Connection URL copied
  
- [ ] **E2B Sandbox**: Account created
  - [ ] API key generated
  - [ ] Template ID noted (if custom)
  
- [ ] **Groq Cloud**: Account created
  - [ ] 3-5 API keys generated
  
- [ ] **Cerebras Cloud**: Account created
  - [ ] 2-3 API keys generated

### Code Repository
- [ ] GitHub repository created
- [ ] Code pushed to `main` branch
- [ ] `.env` file NOT committed (in `.gitignore`)
- [ ] `render.yaml` committed

### Render Configuration
- [ ] Render account created
- [ ] Web service created or Blueprint applied
- [ ] All environment variables set
- [ ] Health check path: `/health`
- [ ] Python version: `3.11.0`

---

## 🔍 Verification Steps

### 1. Check Service Status
```bash
# In Render Dashboard
# Status should be: "Live" (green)
```

### 2. Test Health Endpoint
```bash
curl https://your-service.onrender.com/health

# Expected response:
# {
#   "status": "healthy",
#   "mongodb": "connected",
#   "redis": "connected"
# }
```

### 3. Test API Docs
```
https://your-service.onrender.com/docs
```

### 4. Check Logs
```bash
# In Render Dashboard → Logs
# Look for:
# - "mongodb_initialized"
# - "redis_initialized"
# - "central_hub_initialized_with_memory"
# - "fullstack_agent_initialized_with_tools"
# - "application_started"
```

---

## 🐛 Common Issues & Quick Fixes

### Issue: Build Fails
```bash
# Check Python version in Render
# Environment → PYTHON_VERSION = 3.11.0
```

### Issue: MongoDB Connection Error
```bash
# Verify:
# 1. IP whitelist includes 0.0.0.0/0
# 2. Connection string format is correct
# 3. Password doesn't have special chars (or URL encode)
```

### Issue: Redis Connection Error
```bash
# Verify:
# 1. Redis URL format: redis://default:password@host:port
# 2. Redis instance is running
# 3. Password is correct
```

### Issue: Application Crashes
```bash
# Check logs for missing environment variables
# Verify all REQUIRED variables are set
```

### Issue: 502 Bad Gateway
```bash
# Verify start command:
# uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
```

---

## 📊 Monitoring

### Render Dashboard Metrics
- **CPU Usage**: Should be < 70%
- **Memory Usage**: Should be < 80%
- **Response Time**: Should be < 500ms
- **Error Rate**: Should be < 1%

### Health Check
Render pings `/health` every 30 seconds automatically.

### Logs
Real-time logs available in Dashboard → Logs

---

## 🔄 Update Deployment

### Auto-Deploy (Enabled by Default)
```bash
# Just push to main branch
git add .
git commit -m "Update feature"
git push origin main

# Render will automatically deploy
```

### Manual Deploy
```bash
# In Render Dashboard
# Click "Manual Deploy" → "Deploy latest commit"
```

---

## 🎯 Production URLs

| Endpoint | URL |
|----------|-----|
| **API Root** | `https://your-service.onrender.com/` |
| **Health Check** | `https://your-service.onrender.com/health` |
| **API Docs** | `https://your-service.onrender.com/docs` |
| **API v1** | `https://your-service.onrender.com/api/v1/` |

---

## 💰 Cost Estimate

### Free Tier
- **Render**: Free (with limitations)
- **MongoDB Atlas**: Free M0 (512MB)
- **Redis Cloud**: Free (30MB)
- **E2B**: Free tier available
- **Groq**: Free (30 RPM)
- **Cerebras**: Free tier available

**Total**: $0/month (with free tier limitations)

### Recommended Production
- **Render Starter**: $7/month
- **MongoDB Atlas M2**: $9/month (2GB)
- **Redis Cloud**: $5/month (100MB)
- **E2B**: Pay-as-you-go
- **AI Providers**: Pay-as-you-go

**Total**: ~$21/month + usage-based costs

---

## 📞 Support Links

- **Render Docs**: https://render.com/docs
- **MongoDB Atlas Docs**: https://docs.atlas.mongodb.com
- **Redis Cloud Docs**: https://docs.redis.com/latest/rc/
- **E2B Docs**: https://e2b.dev/docs
- **FastAPI Docs**: https://fastapi.tiangolo.com

---

## 🔐 Security Reminders

- ✅ Never commit `.env` file
- ✅ Use strong JWT secret (32+ characters)
- ✅ Rotate API keys regularly
- ✅ Restrict CORS to specific domains
- ✅ Enable HTTPS only (Render provides free SSL)
- ✅ Set `DEBUG=false` in production
- ✅ Monitor logs for suspicious activity

---

**Last Updated**: 2026-02-16  
**Version**: 1.0.0
