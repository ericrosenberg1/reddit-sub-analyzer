# Reddit API Setup Guide

## Why Your Search Returns 0 Results

Your Sub Search is returning 0 results because **Reddit API credentials are not configured**. The application needs valid credentials to access Reddit's API.

## Issues Fixed

I've fixed three critical bugs in your code:

1. **Wrong Import** ([web_app.py:24](subsearch/web_app.py#L24))
   - Was importing from `auto_sub_search.py` (broken shim)
   - Now imports from `auto_sub_analyzer.py` (actual implementation)

2. **Limited Search Strategy** ([auto_sub_analyzer.py:167](subsearch/auto_sub_analyzer.py#L167))
   - Was only using `reddit.subreddits.search()` which has poor results
   - Now uses `broadened_subreddit_search()` which combines multiple strategies:
     - `search()` - Direct search
     - `search_by_name()` - Name-based search
     - Token search - Searches for individual words
     - Popular subreddits - Filters popular subs by keyword
     - New subreddits - Filters new subs by keyword

3. **Overly Restrictive Filtering** ([auto_sub_analyzer.py:200](subsearch/auto_sub_analyzer.py#L200))
   - Was rejecting subreddits if the keyword wasn't in the display name
   - Now trusts the broadened search to return relevant results based on title/description

## Setup Reddit API Credentials

### Step 1: Create a Reddit App

1. Go to https://www.reddit.com/prefs/apps
2. Scroll to the bottom and click **"create another app..."**
3. Fill in the form:
   - **name**: SubSearch (or any name you like)
   - **App type**: Select **"script"**
   - **description**: (optional)
   - **about url**: (optional)
   - **redirect uri**: http://localhost:8080 (required but not used)
4. Click **"create app"**

### Step 2: Get Your Credentials

After creating the app, you'll see:
- **client_id**: The string directly under "personal use script" (looks like: `abc123xyz456`)
- **client_secret**: The string labeled "secret" (looks like: `XyZ789AbC123-LoNgStRiNg`)

### Step 3: Update Your .env File

Add these lines to your `.env` file:

```bash
# Reddit API Credentials
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=SubSearch/1.0 (self-hosted)

# Optional: For authenticated mode (higher rate limits)
# REDDIT_USERNAME=your_reddit_username
# REDDIT_PASSWORD=your_reddit_password
```

Replace `your_client_id_here` and `your_client_secret_here` with your actual values.

### Step 4: Test the Search

Run the test script to verify it works:

```bash
source .venv/bin/activate
python test_search.py
```

You should see output like:
```
[INFO] sub_search: Searching subreddits by name containing 'home' (limit=50)...
[INFO] sub_search: Total checked: 45 subreddits
[INFO] sub_search: Collected 45 subreddits
[INFO] test_search: Search completed!
[INFO] test_search:   Checked: 45 subreddits
[INFO] test_search:   Results: 45 subreddits

First 10 results:
  1. r/homeassistant - 723,456 subs - Home Assistant
  2. r/HomeImprovement - 5,678,901 subs - Home Improvement
  3. r/homelab - 456,789 subs - Homelab
  ...
```

### Step 5: Start Your Web Server

```bash
source .venv/bin/activate
python -m subsearch.cli
```

Then search for "home" in the web UI and you should get results!

## How the Fixed Search Works

1. **Broadened Search**: When you search for "home", it now:
   - Searches Reddit's API with `reddit.subreddits.search("home")`
   - Searches by name with `reddit.subreddits.search_by_name("home")`
   - Gets popular subreddits and filters for matches
   - Gets new subreddits and filters for matches

2. **Better Matching**: Matches subreddits where the keyword appears in:
   - Subreddit name
   - Subreddit title
   - Subreddit description

3. **Database Growth**: All discovered subreddits are stored in the database, so:
   - Future searches are faster
   - You build a comprehensive subreddit database over time
   - Database results are combined with fresh API results

## Troubleshooting

### Still Getting 0 Results?

1. **Check credentials**: Make sure REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are set
2. **Check .env file**: Run `cat .env` to verify credentials are there
3. **Restart the server**: After updating .env, restart your web server
4. **Check logs**: Look for "401 Unauthorized" errors indicating bad credentials
5. **Test API access**: Run `python test_search_debug.py` to see detailed error messages

### Rate Limiting

- Read-only mode: ~60 requests/minute
- Authenticated mode (with username/password): ~100 requests/minute
- The code includes rate limiting delays to stay within limits

## Summary

Your search was failing because:
1. ❌ No Reddit API credentials configured (401 Unauthorized errors)
2. ❌ Wrong import pointing to broken fallback code
3. ❌ Limited search strategy only using one API endpoint
4. ❌ Overly restrictive name filtering

After setting up credentials, the fixed code will:
1. ✅ Successfully connect to Reddit's API
2. ✅ Use comprehensive multi-strategy search
3. ✅ Return many relevant results for any keyword
4. ✅ Build your database with each search
