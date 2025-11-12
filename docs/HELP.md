# Sub Search User Guide

Welcome to Sub Search! This comprehensive guide will help you discover, analyze, and export Reddit communities using the largest community-maintained subreddit database.

---

## Table of Contents

1. [What is Sub Search?](#what-is-sub-search)
2. [Getting Started](#getting-started)
3. [Using Sub Search](#using-sub-search)
4. [All The Subs Database](#all-the-subs-database)
5. [Understanding Search Results](#understanding-search-results)
6. [Exporting Data](#exporting-data)
7. [Volunteer Nodes](#volunteer-nodes)
8. [Tips & Best Practices](#tips--best-practices)
9. [Frequently Asked Questions](#frequently-asked-questions)

---

## What is Sub Search?

Sub Search is a powerful tool for discovering Reddit subreddits with advanced filtering capabilities. Whether you're a researcher, marketer, community builder, or Reddit enthusiast, Sub Search helps you find exactly the communities you're looking for.

### Key Features

- **Advanced Filtering** - Search by keyword, subscriber count, NSFW status, and moderator activity
- **Real-Time Progress** - Live updates with ETA calculations and smooth animations
- **Dual Data Sources** - Query cached results instantly or fetch fresh data from Reddit
- **3+ Million Subreddits** - Continuously growing community-maintained index
- **CSV Export** - Download search results for analysis in Excel, Google Sheets, or any data tool
- **Distributed Network** - Community-powered nodes help grow the database faster

### How It Works

Sub Search operates on two levels:

1. **Database Search (Fast)** - Queries the cached "All The Subs" database containing 3+ million subreddits with instant results
2. **Live Reddit API Search (Fresh)** - Fetches real-time data directly from Reddit for the most up-to-date information

When you run a search, Sub Search intelligently combines both approaches: it first scans the local database for matches, then supplements with fresh API data, giving you the best of both worlds.

---

## Getting Started

### Accessing Sub Search

1. **Public Instance** - Visit [https://allthesubs.ericrosenberg.com](https://allthesubs.ericrosenberg.com) to use the hosted version
2. **Self-Hosted** - Follow the [installation guide](https://github.com/ericrosenberg1/reddit-sub-analyzer#installation-local) to run your own instance

### Interface Overview

The Sub Search interface consists of several main pages:

- **Home** - Overview of database stats, recent searches, and system status
- **Sub Search** - Main search interface with filtering options
- **All The Subs** - Browse the complete cached database
- **Nodes** - View and manage volunteer nodes contributing to the database
- **Logs** - Detailed history of all searches and background jobs

---

## Using Sub Search

### Basic Search

1. Navigate to the **Sub Search** page
2. Enter optional search parameters:
   - **Keyword** - Filter subreddits by name (e.g., "gaming", "cooking")
   - **Limit** - Maximum number of subreddits to check (default: 1000)
   - **Min Subscribers** - Minimum subscriber count threshold
3. Click **Start Search**
4. Monitor real-time progress with live counters and ETA

### Advanced Filtering Options

#### Unmoderated Only
Check this box to find subreddits without active human moderators. Useful for:
- Community takeover requests
- Finding abandoned communities
- Identifying potential spam havens

**Note:** Moderator activity checking has been disabled for performance. This filter now only checks for the presence of moderators, not their recent activity.

#### Exclude NSFW
Enable this to filter out Not Safe For Work subreddits. Essential for:
- Professional research
- Brand-safe marketing campaigns
- Family-friendly content discovery

#### Minimum Subscribers
Set a threshold to focus on larger, more established communities. Examples:
- `0` - Include all subreddits (default)
- `1000` - Mid-sized communities
- `10000` - Large, active communities
- `100000` - Major subreddits

#### Activity Filters
Filter subreddits based on their last post activity:

1. **Active After** - Find communities with posts after a specific date
   - Example: Find subreddits active in the last 30 days
   - Useful for identifying thriving communities

2. **Inactive Before** - Find dormant communities with no recent posts
   - Example: Find subreddits with no activity in the past year
   - Useful for finding revival opportunities

**How to use:**
1. Check "Enable activity filter"
2. Select "Active After" or "Inactive Before"
3. Choose a date using the date picker
4. The system will filter based on the last post timestamp

### Understanding Search Progress

During a search, you'll see real-time updates:

- **Progress Phase** - Current stage of the search:
  - `Queued` - Waiting for other searches to complete
  - `DB Search` - Scanning the cached database
  - `API Search` - Fetching fresh data from Reddit
  - `Complete` - Search finished successfully

- **Queue Position** - If multiple searches are running, your position in line
- **ETA** - Estimated time until your search starts (based on historical averages)
- **Checked** - Number of subreddits evaluated so far
- **Found** - Number matching your criteria
- **Progress Bar** - Visual indicator with smooth animations

### Search Performance

- **Database searches** are nearly instant (returns results in seconds)
- **API searches** take 2-4 minutes for 1000 subreddits
- **Larger limits** (up to 2000) may take 4-8 minutes
- **Multiple concurrent searches** are queued automatically with ETA calculations

**Note:** API searches are limited to 2000 subreddits per run to respect Reddit's rate limits. Database searches have no such limitation.

---

## All The Subs Database

The "All The Subs" page provides fast access to the complete cached database of 3+ million subreddits.

### Browsing All The Subs

1. Navigate to **All The Subs** from the main menu
2. Use the search filters:
   - **Name Search** - Find subreddits containing specific text
   - **Min Subscribers** - Set subscriber threshold
   - **Unmoderated Only** - Toggle for unmoderated communities
   - **NSFW Filter** - Include or exclude NSFW content
   - **Sort Options** - Order by subscribers, name, update date, etc.

### Sorting Options

- **Subscribers** - By community size (default: descending)
- **Name** - Alphabetical order
- **Title** - By subreddit title
- **Updated At** - Recently indexed subreddits first
- **First Seen** - Discovery order

### Pagination

- Results display 50 subreddits per page by default
- Use page navigation at the bottom to browse through results
- URL parameters allow direct linking to specific pages and filters

### Linking from Search Results

After completing a search, you can:
1. Click "View in All The Subs" to browse those specific results
2. Apply additional filters to your result set
3. Sort and paginate through your findings

---

## Understanding Search Results

Each subreddit result includes the following information:

### Basic Information

- **Name** - The subreddit's unique identifier (e.g., `r/technology`)
- **Title** - Human-readable subreddit title
- **Description** - Public description from the subreddit
- **Subscribers** - Current subscriber count
- **URL** - Direct link to the subreddit on Reddit

### Moderation Data

- **Mod Count** - Number of moderators
- **Is Unmoderated** - Whether the subreddit has active human moderators
- **Last Mod Activity** - When moderators were last active (if available)

**Note:** Moderator activity tracking was disabled in version 2025.11.01.0 for performance improvements. The database may still contain historical mod activity data, but new searches will not fetch this information.

### NSFW Status

- **NSFW Flag** - Indicates if the subreddit is marked as Not Safe For Work
- Automatically set by subreddit configuration on Reddit
- Used for content filtering and brand safety

### Activity Tracking

- **Last Activity** - Timestamp of the most recent post
- **First Seen** - When Sub Search first discovered this subreddit
- **Updated At** - Last time the database record was refreshed
- **Source** - How this subreddit was discovered:
  - `sub_search` - Found via manual user search
  - `auto-ingest` - Discovered by scheduled background bot
  - `auto-random` - Found by random keyword search
  - `manual` - Added manually

---

## Exporting Data

### CSV Export

After a search completes, you can export results to CSV:

1. Click the **Download CSV** button on the results page
2. Your browser will download a file named `subsearch_[JOB_ID].csv`
3. Open in Excel, Google Sheets, or any spreadsheet application

### CSV Format

The exported CSV includes these columns:

```
display_name_prefixed - Full subreddit name (r/subreddit)
title - Subreddit title
public_description - Description text
subscribers - Subscriber count
mod_count - Number of moderators
is_unmoderated - Boolean (True/False)
is_nsfw - Boolean (True/False)
last_activity_utc - Unix timestamp of last post
last_mod_activity_utc - Unix timestamp of last mod action (legacy)
updated_at - ISO 8601 timestamp of last database update
url - Reddit URL
source - Discovery source
```

### Using Exported Data

**Excel/Google Sheets:**
- Open the CSV file directly
- Use filters and pivot tables for analysis
- Create charts and visualizations

**Python/Pandas:**
```python
import pandas as pd
df = pd.read_csv('subsearch_abc123.csv')
print(df.head())
```

**R:**
```r
data <- read.csv('subsearch_abc123.csv')
summary(data)
```

### API Access

For programmatic access, use the REST API endpoints:

**Recent Runs:**
```bash
GET /api/recent-runs?limit=10
```

**Search Database:**
```bash
GET /api/subreddits?q=gaming&min_subs=1000&page=1&page_size=50
```

See the [API Documentation](API.md) for complete endpoint reference.

---

## Volunteer Nodes

Help grow the Sub Search database by running a volunteer node!

### What is a Volunteer Node?

A volunteer node is a community-contributed instance that:
- Runs scheduled background searches
- Discovers new subreddits automatically
- Shares findings with the main database (optional)
- Operates independently with your Reddit credentials

### Benefits of Running a Node

- **Support the Community** - Help maintain the largest open subreddit index
- **Faster Database Growth** - More nodes = faster discovery of new communities
- **Learn About Reddit API** - Hands-on experience with Reddit's API
- **Open Source Contribution** - Be part of a community-driven project

### Setting Up a Node

1. **Install Sub Search** following the [installation guide](https://github.com/ericrosenberg1/reddit-sub-analyzer#installation-local)

2. **Get Reddit API Credentials:**
   - Visit https://www.reddit.com/prefs/apps
   - Click "Create App" or "Create Another App"
   - Choose "script" as the app type
   - Note your `client_id` and `client_secret`

3. **Configure Your Node:**
   ```bash
   # Edit .env file
   AUTO_INGEST_ENABLED=1
   AUTO_INGEST_INTERVAL_MINUTES=180
   PHONE_HOME=true
   PHONE_HOME_ENDPOINT=https://allthesubs.ericrosenberg.com/api/ingest
   ```

4. **Register Your Node:**
   - Visit the [Nodes page](https://allthesubs.ericrosenberg.com/nodes/join)
   - Fill out the registration form
   - Receive a private management link via email

5. **Start Your Node:**
   ```bash
   python -m subsearch.web_app
   ```

### Managing Your Node

After registration, you'll receive a unique management URL that allows you to:

- **Update Details** - Change email, location, system information
- **Set Status** - Mark as active, pending, or broken
- **Delete Node** - Remove your node from the network

**No login required** - Your management link is private and secure.

### Node Health Status

- **Active** - Node is running and contributing
- **Pending** - Node is registered but not yet operational
- **Broken** - Node is offline or experiencing issues

**Automatic Cleanup:** Nodes marked as "broken" for 7+ days are automatically removed during nightly maintenance.

### Phone Home Feature

When enabled, your node can share discoveries with the main database:

- **How it works:** After each search, anonymized subreddit data is sent to the central server
- **What's shared:** Subreddit names, descriptions, subscriber counts (no personal data)
- **Privacy:** Your Reddit credentials and search history remain private
- **Optional:** You can run a node without phone home enabled

To enable:
```bash
PHONE_HOME=true
PHONE_HOME_ENDPOINT=https://allthesubs.ericrosenberg.com/api/ingest
```

---

## Tips & Best Practices

### Effective Searching

1. **Start Broad, Then Narrow**
   - Begin with a general keyword
   - Use filters to refine results
   - Export multiple result sets for comparison

2. **Use Subscriber Thresholds Wisely**
   - `0-100` - New or niche communities
   - `100-1000` - Growing communities
   - `1000-10000` - Established communities
   - `10000+` - Popular subreddits

3. **Combine Filters**
   - Keyword + Min Subscribers = Active niche communities
   - Unmoderated + High Subscribers = Takeover opportunities
   - Exclude NSFW + Activity Filter = Brand-safe, active communities

### Performance Optimization

1. **Use All The Subs for Quick Lookups**
   - If you don't need the absolute latest data
   - Instant results for most queries
   - Perfect for exploratory analysis

2. **Run Sub Search for Fresh Data**
   - When you need current subscriber counts
   - For discovering brand new subreddits
   - When accuracy is critical

3. **Be Patient with Large Searches**
   - Searches with limits over 1000 take longer
   - Use the ETA to plan your workflow
   - Consider running during off-peak hours

### Data Quality

1. **Database Freshness**
   - Database is updated continuously from user searches
   - Most popular subreddits are updated daily
   - Niche subreddits may have older data

2. **Validation**
   - Always verify critical data by visiting the subreddit
   - Subscriber counts may change between search and export
   - Some subreddits may be banned or private

3. **Moderator Activity**
   - Historical data may still show mod activity timestamps
   - New searches will not include mod activity data
   - Unmoderated flag is based on mod presence, not activity

---

## Frequently Asked Questions

### General Questions

**Q: Is Sub Search free to use?**
A: Yes! Sub Search is completely free and open source. You can use the hosted version or run your own instance.

**Q: Do I need a Reddit account to use Sub Search?**
A: No Reddit account is needed to use the hosted version. However, to run your own instance or volunteer node, you'll need Reddit API credentials.

**Q: How often is the database updated?**
A: The database is updated continuously. Every user search adds or refreshes subreddit data. Background bots also run scheduled searches every 3 hours.

**Q: Can I use Sub Search data commercially?**
A: Yes, but respect Reddit's Terms of Service. Don't scrape, spam, or abuse the communities you discover.

### Technical Questions

**Q: What's the API rate limit?**
A: Searches are limited to 2000 subreddits per run to respect Reddit's API limits. The delay between API calls is 0.15 seconds (configurable).

**Q: Can I run multiple searches simultaneously?**
A: Yes! The system handles concurrent searches with an automatic queue. You'll see your queue position and ETA.

**Q: How long are search results stored?**
A: Search results are stored indefinitely in the database. Your specific job results remain accessible until you clear your browser cache.

**Q: Why did my search stop at 2000 subreddits?**
A: This is the public API limit to prevent rate limit issues. The database search has no such limit.

### Troubleshooting

**Q: My search is stuck at "Running" forever**
A: This is rare, but if it happens, the nightly cleanup process will mark stale jobs as failed after 24 hours. Try starting a new search.

**Q: I'm getting an error message**
A: Check the error details on the search page. Common issues:
- Reddit API temporarily unavailable
- Rate limit exceeded (wait a few minutes)
- Invalid search parameters (check your filters)

**Q: The CSV download isn't working**
A: Ensure your search completed successfully. Check the search logs page for error details. Try a smaller search if you're hitting timeouts.

**Q: Results don't match my filters**
A: Remember that database results may include subreddits outside your filters if they were previously discovered. API results will strictly match your criteria.

### Database Questions

**Q: How many subreddits are in the database?**
A: Currently 3+ million and growing. Check the homepage for the latest count.

**Q: What's the oldest data in the database?**
A: Some subreddit entries date back to the project's inception. Check the `first_seen_at` field in exports.

**Q: Can I download the entire database?**
A: For API-based access, use the `/api/subreddits` endpoint with pagination. For bulk access, consider running your own instance.

**Q: Why are some fields empty (like mod_count)?**
A: Data availability depends on when the subreddit was discovered and what information Reddit provided. Older entries may have incomplete data.

### Contributing

**Q: How can I contribute to Sub Search?**
A: Several ways:
- Run a volunteer node
- Submit bug reports and feature requests on [GitHub](https://github.com/ericrosenberg1/reddit-sub-analyzer/issues)
- Contribute code via pull requests
- Share Sub Search with your community

**Q: Can I help improve the documentation?**
A: Absolutely! Documentation contributions are welcome. Submit a PR or open an issue with suggestions.

**Q: I found a bug. What should I do?**
A: Report it on [GitHub Issues](https://github.com/ericrosenberg1/reddit-sub-analyzer/issues) with:
- Steps to reproduce
- Expected vs actual behavior
- Browser/environment details
- Screenshots if applicable

---

## Getting Help

### Resources

- **GitHub Repository:** https://github.com/ericrosenberg1/reddit-sub-analyzer
- **Developer Docs:** [DEVELOPERS.md](DEVELOPERS.md)
- **API Documentation:** [API.md](API.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)

### Support Channels

- **GitHub Issues:** For bug reports and feature requests
- **GitHub Discussions:** For questions and community support
- **Email:** contact@ericrosenberg.com for general inquiries

### Community

Join the Sub Search community:
- Star the project on GitHub
- Share your use cases and discoveries
- Help answer questions from other users
- Contribute code or documentation

---

**Last Updated:** November 2025
**Version:** 2025.11.01.0

*Made with care by the Sub Search community*
