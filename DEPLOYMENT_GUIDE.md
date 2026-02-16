# Qbit Backend - Render Deployment Guide

## 📋 Table of Contents
1. [Prerequisites](#prerequisites)
2. [Pre-Deployment Setup](#pre-deployment-setup)
3. [Render Deployment Steps](#render-deployment-steps)
4. [Environment Variables Configuration](#environment-variables-configuration)
5. [Post-Deployment Verification](#post-deployment-verification)
6. [Troubleshooting](#troubleshooting)
7. [Production Optimization](#production-optimization)

---

## 🔧 Prerequisites

Before deploying to Render, ensure you have:

### Required Accounts
- ✅ **Render Account** - [Sign up at render.com](https://render.com)
- ✅ **MongoDB Atlas Account** - [Sign up at mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
- ✅ **Redis Cloud Account** - [Sign up at redis.com/try-free](https://redis.com/try-free/)
- ✅ **GitHub Account** - For code repository
- ✅ **E2B Account** - [Sign up at e2b.dev](https://e2b.dev)
- ✅ **Groq Account** - [Sign up at console.groq.com](https://console.groq.com)
- ✅ **Cerebras Account** - [Sign up at cerebras.ai](https://cerebras.ai)

### Optional Accounts
- ⭕ **Bytez Account** - For Claude Sonnet 4 integration
- ⭕ **GitHub OAuth App** - If using GitHub authentication

---

## 🚀 Pre-Deployment Setup

### Step 1: Set Up MongoDB Atlas (Free Tier)

1. **Create a MongoDB Atlas Account**
   - Go to [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
   - Click "Try Free" and sign up

2. **Create a Free Cluster**
   - Choose **M0 Free Tier** (512MB storage)
   - Select a cloud provider (AWS/GCP/Azure)
   - Choose a region close to your Render deployment region
   - Cluster name: `qbit-cluster`

3. **Configure Database Access**
   - Go to "Database Access" → "Add New Database User"
   - Username: `qbit_admin`
   - Password: Generate a strong password (save it!)
   - Database User Privileges: **Read and write to any database**

4. **Configure Network Access**
   - Go to "Network Access" → "Add IP Address"
   - Click "Allow Access from Anywhere" (0.0.0.0/0)
   - ⚠️ **Important**: This is required for Render to connect
   - Confirm

5. **Get Connection String**
   - Go to "Database" → Click "Connect" on your cluster
   - Choose "Connect your application"
   - Driver: **Python** / Version: **3.11 or later**
   - Copy the connection string:
     ```
     mongodb+srv://qbit_admin:<password>@qbit-cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority
     ```
   - Replace `<password>` with your actual password
   - **Save this connection string** - you'll need it for Render

### Step 2: Set Up Redis Cloud (Free Tier)

1. **Create a Redis Cloud Account**
   - Go to [redis.com/try-free](https://redis.com/try-free/)
   - Sign up for a free account

2. **Create a Free Database**
   - Click "New Database"
   - Select **Free Plan** (30MB)
   - Choose a cloud provider and region (same as Render region)
   - Database name: `qbit-cache`

3. **Get Connection Details**
   - After creation, click on your database
   - Copy the **Endpoint** (e.g., `redis-12345.c123.region.cloud.redislabs.com:12345`)
   - Copy the **Default user password**
   - Format the connection string:
     ```
     redis://default:<password>@<endpoint>
     ```
   - Example:
     ```
     redis://default:yourpassword@redis-12345.c123.us-central1-1.gce.cloud.redislabs.com:12345
     ```
   - **Save this connection string** - you'll need it for Render

### Step 3: Set Up E2B Sandbox

1. **Create E2B Account**
   - Go to [e2b.dev](https://e2b.dev)
   - Sign up and verify your email

2. **Get API Key**
   - Go to Dashboard → API Keys
   - Click "Create API Key"
   - Copy the key (starts with `e2b_`)
   - **Save this API key**

3. **Get Template ID** (if you have a custom template)
   - Go to Templates
   - Copy your template ID (or use default)
   - **Save this template ID**

### Step 4: Set Up AI Provider API Keys

#### Groq Cloud (Central Hub)
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up and verify email
3. Navigate to API Keys
4. Create **3-5 API keys** (for rotation to avoid rate limits)
5. Copy all keys (format: `gsk_...`)
6. **Save as comma-separated list**: `key1,key2,key3`

#### Cerebras Cloud (Full Stack Agent)
1. Go to [cerebras.ai](https://cerebras.ai)
2. Sign up and get API access
3. Create **2-3 API keys**
4. Copy all keys (format: `csk_...`)
5. **Save as comma-separated list**: `key1,key2,key3`

#### Bytez Cloud (Optional - Claude Sonnet 4)
1. Get Bytez API access
2. Create **2 API keys**
3. **Save as comma-separated list**: `key1,key2`

### Step 5: Generate JWT Secret Key

Run this command to generate a secure JWT secret:

```bash
# On Linux/Mac
openssl rand -hex 32

# On Windows (PowerShell)
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | % {[char]$_})

# Or use Python
python -c "import secrets; print(secrets.token_hex(32))"
```

**Save this secret key** - you'll need it for Render.

### Step 6: Push Code to GitHub

1. **Create a GitHub Repository**
   ```bash
   # Initialize git (if not already done)
   cd "e:\2026 Qbit\Elixirlabs-Qbit-Production"
   git init
   
   # Add all files
   git add .
   
   # Commit
   git commit -m "Initial commit - Qbit backend"
   
   # Create repository on GitHub (via web interface)
   # Then push
   git remote add origin https://github.com/YOUR_USERNAME/qbit-backend.git
   git branch -M main
   git push -u origin main
   ```

2. **Verify .gitignore**
   - Ensure `.env` is in `.gitignore` (never commit secrets!)
   - Verify `venv/` is ignored

---

## 🌐 Render Deployment Steps

### Method 1: Using Render Blueprint (Recommended)

1. **Log in to Render Dashboard**
   - Go to [dashboard.render.com](https://dashboard.render.com)

2. **Create New Blueprint**
   - Click "New" → "Blueprint"
   - Connect your GitHub repository
   - Render will detect `render.yaml` automatically

3. **Review Services**
   - Verify the service configuration
   - Click "Apply"

4. **Configure Environment Variables** (See next section)

### Method 2: Manual Web Service Creation

1. **Create New Web Service**
   - Click "New" → "Web Service"
   - Connect your GitHub repository
   - Select the `qbit-backend` repository

2. **Configure Service**
   - **Name**: `qbit-backend`
   - **Region**: Choose closest to your users (e.g., Oregon, Frankfurt)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: 
     ```bash
     pip install --upgrade pip && pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
     ```

3. **Advanced Settings**
   - **Python Version**: `3.11.0`
   - **Health Check Path**: `/health`
   - **Auto-Deploy**: `Yes`

4. **Plan Selection**
   - **Free Tier**: Limited resources, sleeps after inactivity
   - **Starter ($7/month)**: Recommended for production
   - **Standard**: For high traffic

5. **Click "Create Web Service"**

---

## 🔐 Environment Variables Configuration

After creating the service, configure environment variables:

### Critical Variables (MUST SET)

Go to your service → "Environment" → "Add Environment Variable"

#### Database & Cache
```bash
MONGODB_URI=mongodb+srv://qbit_admin:<password>@qbit-cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=qbit_production
REDIS_URL=redis://default:<password>@redis-xxxxx.cloud.redislabs.com:12345
```

#### AI Provider Keys
```bash
GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3
CEREBRAS_API_KEYS=csk_key1,csk_key2,csk_key3
BYTEZ_API_KEYS=bytez_key1,bytez_key2
```

#### E2B Sandbox
```bash
E2B_API_KEY=e2b_your_api_key_here
E2B_TEMPLATE_ID=your_template_id
```

#### JWT Authentication
```bash
JWT_SECRET_KEY=your_generated_secret_key_from_step_5
```

#### Celery (Background Tasks)
```bash
CELERY_BROKER_URL=redis://default:<password>@redis-xxxxx.cloud.redislabs.com:12345/0
CELERY_RESULT_BACKEND=redis://default:<password>@redis-xxxxx.cloud.redislabs.com:12345/0
```

### Optional Variables

#### GitHub OAuth (if using)
```bash
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
GITHUB_CALLBACK_URL=https://qbit-backend.onrender.com/api/v1/auth/github/callback
```

#### CORS (Update with your frontend URL)
```bash
CORS_ORIGINS=https://your-frontend.vercel.app,https://your-custom-domain.com
```

### Application Settings (Already in render.yaml)
```bash
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
SHOW_ERROR_DETAILS=false
ENABLE_DOCS=true
```

---

## ✅ Post-Deployment Verification

### Step 1: Check Deployment Status

1. **Monitor Build Logs**
   - Go to your service → "Logs"
   - Watch for successful build completion
   - Look for: `application_started` log message

2. **Verify Service is Running**
   - Status should show "Live" (green)
   - If "Deploy failed", check logs for errors

### Step 2: Test Health Endpoint

Open your browser or use curl:

```bash
# Replace with your actual Render URL
curl https://qbit-backend.onrender.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "app": "Qbit",
  "version": "1.0.0",
  "environment": "production",
  "mongodb": "connected",
  "redis": "connected"
}
```

### Step 3: Test API Documentation

Visit: `https://qbit-backend.onrender.com/docs`

You should see the FastAPI Swagger UI with all endpoints.

### Step 4: Test Root Endpoint

```bash
curl https://qbit-backend.onrender.com/
```

Expected response:
```json
{
  "name": "Qbit",
  "version": "1.0.0",
  "status": "online",
  "environment": "production",
  "docs": "/docs"
}
```

### Step 5: Verify Database Connections

Check logs for:
```
mongodb_initialized
redis_initialized
central_hub_initialized_with_memory
fullstack_agent_initialized_with_tools
application_started
```

---

## 🔧 Troubleshooting

### Issue 1: Build Fails - "Could not find a version that satisfies the requirement"

**Solution**: Check Python version
```bash
# In render.yaml or Environment Variables
PYTHON_VERSION=3.11.0
```

### Issue 2: MongoDB Connection Failed

**Symptoms**: `mongodb: "error: connection refused"`

**Solutions**:
1. Verify MongoDB Atlas IP whitelist includes `0.0.0.0/0`
2. Check connection string format:
   ```
   mongodb+srv://username:password@cluster.mongodb.net/
   ```
3. Ensure password doesn't contain special characters (URL encode if needed)
4. Test connection string locally first

### Issue 3: Redis Connection Failed

**Symptoms**: `redis: "error: connection timeout"`

**Solutions**:
1. Verify Redis Cloud endpoint is correct
2. Check password is correct
3. Ensure Redis instance is running
4. Test connection:
   ```bash
   redis-cli -h your-endpoint -p port -a password ping
   ```

### Issue 4: Application Crashes on Startup

**Check logs for**:
- Missing environment variables
- Import errors
- Database connection failures

**Solution**: Verify all required environment variables are set

### Issue 5: 502 Bad Gateway

**Causes**:
- Application not binding to `0.0.0.0`
- Wrong port (must use `$PORT`)
- Application crashed

**Solution**: Verify start command:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Issue 6: Free Tier Service Sleeps

**Symptom**: First request takes 30+ seconds

**Solution**: 
- Upgrade to Starter plan ($7/month)
- Or use a cron job to ping health endpoint every 10 minutes

### Issue 7: Rate Limit Errors from AI Providers

**Solution**: 
- Add more API keys to rotation pool
- Increase `GROQ_RPM_LIMIT` and `CEREBRAS_RPM_LIMIT` if you have paid tiers

---

## 🚀 Production Optimization

### 1. Upgrade to Paid Plan

**Free Tier Limitations**:
- 512MB RAM
- Sleeps after 15 minutes of inactivity
- Slower CPU

**Recommended**: Starter plan ($7/month)
- 512MB RAM (always on)
- No sleep
- Better performance

### 2. Enable Auto-Scaling (Standard+ plans)

```yaml
# In render.yaml
services:
  - type: web
    scaling:
      minInstances: 1
      maxInstances: 3
      targetCPUPercent: 70
```

### 3. Add Custom Domain

1. Go to service → "Settings" → "Custom Domain"
2. Add your domain (e.g., `api.yourdomain.com`)
3. Update DNS records as instructed
4. Update CORS settings:
   ```bash
   CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
   ```

### 4. Enable Persistent Disk (if needed)

For file storage beyond database:
```yaml
# In render.yaml
disk:
  name: qbit-storage
  mountPath: /data
  sizeGB: 1
```

### 5. Set Up Background Worker (Celery)

Uncomment the worker service in `render.yaml`:
```yaml
- type: worker
  name: qbit-celery-worker
  runtime: python
  buildCommand: pip install -r requirements.txt
  startCommand: celery -A tasks.celery_app worker --loglevel=info
```

### 6. Configure Monitoring

**Render Built-in Metrics**:
- CPU usage
- Memory usage
- Request count
- Response time

**External Monitoring** (Optional):
- Sentry for error tracking
- Datadog for APM
- Prometheus + Grafana

### 7. Set Up Alerts

1. Go to service → "Settings" → "Alerts"
2. Configure:
   - High CPU usage (>80%)
   - High memory usage (>90%)
   - Failed health checks
   - Deploy failures

### 8. Enable Continuous Deployment

Already configured in `render.yaml`:
```yaml
autoDeploy: true
```

Every push to `main` branch will trigger automatic deployment.

### 9. Database Optimization

**MongoDB Atlas**:
- Create indexes for frequently queried fields
- Enable connection pooling (already configured)
- Monitor slow queries

**Redis**:
- Set appropriate TTL for cached data
- Monitor memory usage
- Use Redis persistence if needed

### 10. Security Hardening

**Environment Variables**:
- Never commit `.env` to git
- Rotate API keys regularly
- Use strong JWT secret

**CORS**:
- Restrict to specific domains (not `*`)
- Update `CORS_ORIGINS` with production URLs

**Rate Limiting**:
- Already configured in application
- Adjust limits based on usage patterns

**HTTPS**:
- Render provides free SSL certificates
- Enforce HTTPS in production

---

## 📊 Monitoring Deployment

### View Logs

```bash
# Real-time logs in Render Dashboard
# Or use Render CLI
render logs qbit-backend --tail
```

### Check Metrics

- Go to service → "Metrics"
- Monitor:
  - Request rate
  - Response time
  - Error rate
  - CPU/Memory usage

### Health Checks

Render automatically pings `/health` endpoint every 30 seconds.

---

## 🎯 Next Steps

1. ✅ Deploy backend to Render
2. ✅ Verify all endpoints work
3. ✅ Deploy frontend (Vercel/Netlify)
4. ✅ Update CORS settings with frontend URL
5. ✅ Test end-to-end flow
6. ✅ Set up monitoring and alerts
7. ✅ Configure custom domain
8. ✅ Enable auto-scaling (if needed)

---

## 📞 Support

**Render Documentation**: [render.com/docs](https://render.com/docs)  
**Render Community**: [community.render.com](https://community.render.com)  
**Qbit Issues**: [GitHub Issues](https://github.com/YOUR_USERNAME/qbit-backend/issues)

---

## 📝 Deployment Checklist

- [ ] MongoDB Atlas cluster created and configured
- [ ] Redis Cloud instance created
- [ ] E2B API key obtained
- [ ] Groq API keys obtained (3-5 keys)
- [ ] Cerebras API keys obtained (2-3 keys)
- [ ] JWT secret key generated
- [ ] GitHub repository created and code pushed
- [ ] Render service created
- [ ] All environment variables configured
- [ ] Deployment successful
- [ ] Health endpoint returns "healthy"
- [ ] API documentation accessible
- [ ] Database connections verified
- [ ] CORS configured for frontend
- [ ] Custom domain added (optional)
- [ ] Monitoring and alerts configured
- [ ] Production optimizations applied

---

**Deployment Date**: _______________  
**Deployed By**: _______________  
**Service URL**: https://qbit-backend.onrender.com  
**Status**: _______________
