# Imposer API — Deployment Guide

This is a **Python API service** that does the shape matching for rotation detection. Your CEP plugin will call this service.

**Goal:** Get a live URL like `https://imposer-api.onrender.com` that your plugin can call.

**Cost:** $0 (Render free tier).

**Time:** 30-45 minutes one-time setup.

---

## What You'll Be Doing

1. Create a free GitHub account (5 min)
2. Upload this folder to a new GitHub repo (5 min)
3. Create a free Render account (5 min)
4. Connect Render to your GitHub repo (5 min)
5. Wait for first deploy (10 min)
6. Test the live URL (5 min)

Total: ~30 minutes, then it's live forever.

---

## STEP 1 — Create GitHub Account

1. Go to `https://github.com/`
2. Click **Sign up**
3. Use your email, choose a username
4. Verify your email
5. Free plan is fine

Why GitHub: Render reads code from GitHub repos. Industry standard, free.

---

## STEP 2 — Create a New Repository

1. Once logged into GitHub, click the **+** icon (top right) → **New repository**
2. Repository name: `imposer-api`
3. Description: `Shape matching API for prepress imposition`
4. Visibility: **Public** (Render free tier requires public; we can switch to private later when paid)
5. **Do NOT** check any of the "Add a README", ".gitignore", "license" boxes
6. Click **Create repository**

You'll see an empty repo with instructions. Ignore them, go to Step 3.

---

## STEP 3 — Upload the API Code

The easiest way (no terminal, no git knowledge needed):

1. On your new empty `imposer-api` repo page, click **uploading an existing file** link
   (or click "Add file" → "Upload files")
2. Open the `imposer-api` folder I gave you on your Mac
3. **Select ALL files inside** (algorithm.py, main.py, requirements.txt, render.yaml, .gitignore)
4. **Drag them ALL** into the GitHub upload area
5. Wait for upload to complete (~10 seconds)
6. At the bottom: in the commit message box type `Initial commit`
7. Click **Commit changes**

After upload, you should see all 5 files listed in the repo.

> ⚠️ Important: `.gitignore` is a hidden file on Mac. To select it:
> - In Finder, press **Cmd + Shift + .** (period) to show hidden files
> - Now you'll see `.gitignore` along with the others

---

## STEP 4 — Create Render Account

1. Go to `https://render.com/`
2. Click **Get Started for Free**
3. Sign up with your **GitHub account** (easiest — one click)
4. Authorize Render to access your GitHub
5. You're in. No payment method needed for free tier.

---

## STEP 5 — Deploy

1. In Render dashboard, click **New +** (top right) → **Web Service**
2. You'll see your GitHub repos listed. Find **imposer-api** → click **Connect**
3. Render auto-detects the `render.yaml` config. You'll see:
   - **Name:** imposer-api (auto-filled from yaml)
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free
4. Scroll down, click **Create Web Service**

Render will now:
- Pull your code from GitHub
- Install Python dependencies (FastAPI, Shapely)
- Start the service
- Give you a live URL

**This takes 5-10 minutes for the first deploy.** Watch the build logs — green = success, red = error.

When done, you'll see a URL at the top like:
```
https://imposer-api-xxxx.onrender.com
```

That's your live API.

---

## STEP 6 — Test the Live URL

Open these URLs in your browser:

**1. Health check:**
```
https://imposer-api-xxxx.onrender.com/health
```
Should show: `{"status":"ok","service":"imposer-api"}`

**2. Interactive docs (FastAPI gift):**
```
https://imposer-api-xxxx.onrender.com/docs
```
This is a full UI where you can test the API by clicking buttons. Try the `/detect` endpoint with sample data.

---

## ⚠️ Free Tier Notes (Honest Disclosure)

**Cold start delay:**
- Free tier services **sleep after 15 minutes** of no activity
- Next request takes **30-60 seconds** to wake up (one-time per session)
- After waking, all subsequent requests are fast (~50-200ms)

**For your plugin workflow:** First scan of the day = slow wake-up. Rest of day = fast. We'll add a loading indicator in the plugin to handle this gracefully.

**When to upgrade to paid ($7/mo):**
- When you have 50+ active customers
- Removes sleep, faster CPU, more memory
- Revenue from customers will easily cover this

---

## Troubleshooting

**Build fails on Render:**
- Check `requirements.txt` was uploaded
- Check the build logs for the exact error
- Most common: typo in file names — they must match exactly

**Service deploys but `/health` returns error:**
- Check `main.py` was uploaded
- Check `algorithm.py` was uploaded (both files needed)

**404 on `/docs`:**
- Make sure you're using the full Render URL with `/docs` appended
- Wait 30 seconds, the service might be waking up

---

## Next Step

Once your API is live and `/health` returns OK:

→ Share the live URL with me, and I'll integrate it into your CEP plugin in Phase 3.

The plugin will call this API instead of doing the shape matching locally. You'll get the accuracy of cloud-based matching with the same workflow you already have.
