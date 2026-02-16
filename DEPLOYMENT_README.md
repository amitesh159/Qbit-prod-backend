# 🚀 Qbit Backend - Render Deployment

This directory contains everything you need to deploy the Qbit backend to Render.com using Python 3.11 (no Docker).

## 📁 Deployment Files

- **`render.yaml`** - Render Blueprint configuration (infrastructure as code)
- **`DEPLOYMENT_GUIDE.md`** - Complete step-by-step deployment guide
- **`QUICK_REFERENCE.md`** - Quick reference for common tasks
- **`.env.production.example`** - Production environment variables template
- **`scripts/validate_env.py`** - Environment validation script

## 🎯 Quick Start

### 1. Prerequisites Setup (30 minutes)

Create accounts and get credentials for:

- ✅ **MongoDB Atlas** (free tier) - Database
- ✅ **Redis Cloud** (free tier) - Cache & task queue
- ✅ **E2B** - Sandbox environment
- ✅ **Groq Cloud** - AI provider (Central Hub)
- ✅ **Cerebras Cloud** - AI provider (Full Stack Agent)
- ✅ **Render** - Hosting platform

**See**: `DEPLOYMENT_GUIDE.md` → "Pre-Deployment Setup" for detailed instructions.

### 2. Validate Environment (2 minutes)

```bash
# Run the validation script
python scripts/validate_env.py
```

This checks all required environment variables are properly configured.

### 3. Push to GitHub (5 minutes)

```bash
git add .
git commit -m "Ready for Render deployment"
git push origin main
```

### 4. Deploy to Render (10 minutes)

**Option A: Using Blueprint (Recommended)**
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New" → "Blueprint"
3. Connect your GitHub repository
4. Render will detect `render.yaml` automatically
5. Click "Apply"

**Option B: Manual Setup**
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure as per `DEPLOYMENT_GUIDE.md` → "Render Deployment Steps"

### 5. Configure Environment Variables (15 minutes)

In Render Dashboard → Your Service → Environment:

**Critical Variables** (must set):
```bash
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
REDIS_URL=redis://default:pass@host:port
GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3
CEREBRAS_API_KEYS=csk_key1,csk_key2
E2B_API_KEY=e2b_your_key
JWT_SECRET_KEY=your_64_char_secret
CELERY_BROKER_URL=redis://default:pass@host:port/0
CELERY_RESULT_BACKEND=redis://default:pass@host:port/0
CORS_ORIGINS=https://your-frontend.com
```

**See**: `.env.production.example` for complete list with instructions.

### 6. Verify Deployment (5 minutes)

```bash
# Check health endpoint
curl https://your-service.onrender.com/health

# Expected response:
# {
#   "status": "healthy",
#   "mongodb": "connected",
#   "redis": "connected"
# }
```

**See**: `DEPLOYMENT_GUIDE.md` → "Post-Deployment Verification" for detailed checks.

## 📚 Documentation

### For First-Time Deployment
→ Read **`DEPLOYMENT_GUIDE.md`** - Complete guide with screenshots and troubleshooting

### For Quick Reference
→ Read **`QUICK_REFERENCE.md`** - Cheat sheet for common tasks

### For Environment Setup
→ Use **`.env.production.example`** - Template with all required variables

## 🔧 Configuration Details

### Python Version
- **Required**: Python 3.11.0
- **Set in**: `render.yaml` → `envVars.PYTHON_VERSION`

### Build Command
```bash
pip install --upgrade pip && pip install -r requirements.txt
```

### Start Command
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
```

### Health Check
- **Path**: `/health`
- **Frequency**: Every 30 seconds (automatic)

## 🌐 Service Endpoints

After deployment, your API will be available at:

| Endpoint | URL |
|----------|-----|
| Root | `https://your-service.onrender.com/` |
| Health Check | `https://your-service.onrender.com/health` |
| API Docs | `https://your-service.onrender.com/docs` |
| API v1 | `https://your-service.onrender.com/api/v1/` |

## 💰 Cost Breakdown

### Free Tier (Development)
- **Render**: Free (with limitations)
- **MongoDB Atlas**: Free M0 (512MB)
- **Redis Cloud**: Free (30MB)
- **E2B**: Free tier available
- **AI Providers**: Free tiers available

**Total**: $0/month

**Limitations**:
- Service sleeps after 15 minutes of inactivity
- 512MB RAM
- Slower performance

### Production (Recommended)
- **Render Starter**: $7/month
- **MongoDB Atlas M2**: $9/month (2GB)
- **Redis Cloud**: $5/month (100MB)
- **E2B**: Pay-as-you-go
- **AI Providers**: Pay-as-you-go

**Total**: ~$21/month + usage costs

## 🐛 Troubleshooting

### Common Issues

**Build Fails**
```bash
# Check Python version
# In Render: Environment → PYTHON_VERSION = 3.11.0
```

**MongoDB Connection Error**
```bash
# Verify IP whitelist includes 0.0.0.0/0
# Check connection string format
```

**Redis Connection Error**
```bash
# Verify Redis URL format: redis://default:password@host:port
# Check Redis instance is running
```

**Application Crashes**
```bash
# Check logs for missing environment variables
# Verify all REQUIRED variables are set
```

**See**: `DEPLOYMENT_GUIDE.md` → "Troubleshooting" for detailed solutions.

## 🔄 Updating Deployment

### Auto-Deploy (Enabled by Default)
```bash
# Just push to main branch
git add .
git commit -m "Update feature"
git push origin main

# Render will automatically deploy
```

### Manual Deploy
1. Go to Render Dashboard
2. Click "Manual Deploy" → "Deploy latest commit"

## 🔐 Security Checklist

Before deploying to production:

- [ ] Generated strong JWT secret (32+ characters)
- [ ] Set `DEBUG=false`
- [ ] Set `SHOW_ERROR_DETAILS=false`
- [ ] Configured specific CORS origins (not `*`)
- [ ] Never committed `.env` file to git
- [ ] Rotated API keys regularly
- [ ] Enabled HTTPS (automatic on Render)
- [ ] Set up monitoring and alerts

## 📊 Monitoring

### Render Dashboard Metrics
- CPU Usage
- Memory Usage
- Request Count
- Response Time
- Error Rate

### Health Checks
Render automatically pings `/health` every 30 seconds.

### Logs
Real-time logs available in Dashboard → Logs

## 🎯 Next Steps After Deployment

1. ✅ Verify all endpoints work
2. ✅ Deploy frontend (Vercel/Netlify)
3. ✅ Update CORS settings with frontend URL
4. ✅ Test end-to-end flow
5. ✅ Set up monitoring and alerts
6. ✅ Configure custom domain (optional)
7. ✅ Enable auto-scaling (if needed)

## 📞 Support

- **Render Docs**: https://render.com/docs
- **Deployment Guide**: See `DEPLOYMENT_GUIDE.md`
- **Quick Reference**: See `QUICK_REFERENCE.md`
- **Issues**: Create GitHub issue

## 📝 Deployment Checklist

Use this checklist to track your deployment progress:

### Pre-Deployment
- [ ] MongoDB Atlas cluster created
- [ ] Redis Cloud instance created
- [ ] E2B API key obtained
- [ ] Groq API keys obtained (3-5 keys)
- [ ] Cerebras API keys obtained (2-3 keys)
- [ ] JWT secret generated
- [ ] GitHub repository created
- [ ] Code pushed to GitHub

### Deployment
- [ ] Render service created
- [ ] All environment variables configured
- [ ] Deployment successful
- [ ] Health endpoint returns "healthy"
- [ ] API documentation accessible
- [ ] Database connections verified

### Post-Deployment
- [ ] CORS configured for frontend
- [ ] Custom domain added (optional)
- [ ] Monitoring configured
- [ ] Alerts set up
- [ ] Production optimizations applied

---

**Version**: 1.0.0  
**Last Updated**: 2026-02-16  
**Python Version**: 3.11.0  
**Platform**: Render.com
