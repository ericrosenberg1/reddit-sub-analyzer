# Changelog

All notable changes to Sub Search are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project uses **Tesla-style versioning**: `YYYY.MM.VV.v` (Year.Month.Version.Patch).

---

## [2025.11.01.0] - 2025-11-12

### 🎉 Major Release - Complete Site Overhaul

This release represents a comprehensive overhaul of Sub Search with significant performance improvements, UX enhancements, and better documentation.

### ✨ Added

- **Tesla-Style Versioning** - Implemented YYYY.MM.VV.v versioning system for clearer release tracking
- **VERSION File** - Added root VERSION file for centralized version management
- **Version Bump Script** - Automated version incrementing with `scripts/bump_version.py`
- **Comprehensive Documentation** - Created extensive user and developer guides:
  - `docs/HELP.md` - ~5000 word user-friendly guide with FAQ
  - `docs/DEVELOPERS.md` - ~5000 word technical documentation
  - `docs/CHANGELOG.md` - Complete version history
- **Cleanup Function** - Added `cleanup_stale_runs()` to mark jobs stuck in "running" state as failed after 24 hours
- **Search History Section** - Added search history link on homepage below pipeline section
- **Auto-Refresh on Homepage** - Recent searches update every 5 seconds via `/api/recent-runs` endpoint
- **ETA Calculations** - Queue position now shows estimated wait time based on historical job averages
- **Progress Phases** - Added visual indicators for search stages (queued, db_search, api_search, complete)
- **Smooth Counter Animations** - Real-time progress updates with RequestAnimationFrame-based smooth transitions

### 🚀 Performance

- **60-75% Speed Improvement** - Reduced search time from 8-12 minutes to 2-4 minutes for 1000 subreddits
- **Removed Moderator Activity Tracking** - Eliminated up to 8000 unnecessary API calls per search
  - `MOD_ACTIVITY_SAMPLE_SIZE` removed
  - `MOD_ACTIVITY_FETCH_LIMIT` removed
  - `_fetch_mod_activity()` function removed
  - All mod activity fields now return `None` for new searches
- **Reduced Rate Limiting** - Decreased delay from 0.2s to 0.15s between API calls
- **Faster UI Updates** - JavaScript polling reduced from 3 seconds to 1 second

### 🎨 UI/UX Improvements

- **Standardized Capitalization** - Consistent text styling across the entire site
- **US Timezone Formatting** - All timestamps display in user's local timezone:
  - Format: MM/DD/YYYY, H:MM AM/PM with timezone abbreviation (e.g., "11/12/2025, 3:45 PM EST")
  - Replaced UTC-only timestamps throughout the site
- **Reorganized Homepage** - Simplified from 3 feature boxes to 2:
  - Changed "The Always Growing Sub Database" → "Always growing / Automatic database expansion"
  - Changed "The Secret Sauce" → "Community powered / Distributed node network"
  - Changed "Search and Export" → "Search & export / Custom subreddit lists"
  - Removed redundant boxes (Nightly cleanup, Manual+auto, bottom Open source section)
- **Improved Recent Searches** - Auto-updating status badges with live result counts
- **Updated Footer** - Removed "vdev" prefix from version, removed Activity link, updated docs to point to GitHub

### 🔧 Technical Changes

- **Context Processor Update** - `build_number` now reads from `VERSION` file instead of `BUILD_NUMBER`
- **Nightly Cleanup Enhanced** - Added stale run cleanup to node cleanup loop
- **Removed Routes** - Deleted `/helpdocs` and `/docs/developers` routes (moved to GitHub)
- **Database Optimization** - Maintained existing indexes for performance
- **Caching Strategy** - Kept existing TTL cache implementation

### 📝 Documentation

- **README Overhaul** - Complete rewrite with:
  - Badges for stars, forks, issues, Python, Flask, Reddit API, version, license, PRs welcome
  - Comprehensive features list with emojis
  - Quick start guide with copy-paste commands
  - Docker deployment instructions
  - Cloud deployment guides (Fly.io, Railway, Heroku)
  - Volunteer node setup instructions
  - Contributing guidelines
  - Architecture diagram
  - Performance metrics
  - Roadmap for future releases
- **Help Documentation** - User-friendly guide covering all features
- **Developer Documentation** - Technical reference for contributors
- **Changelog** - Tesla-style versioned release history

### 🐛 Bug Fixes

- Fixed stale jobs appearing as "running" indefinitely (now cleaned up after 24 hours)
- Corrected timestamp formatting inconsistencies across the site
- Fixed recent searches box not updating automatically

### 🗑️ Deprecated

- Moderator activity tracking (disabled for performance, database still contains historical data)
- `/helpdocs` and `/docs/developers` routes (moved to GitHub repository)
- Activity link in footer (replaced with direct link to GitHub docs)

### 📦 Dependencies

No dependency changes in this release.

---

## [2025.11.0.1] - 2025-11-11

### 🚀 Performance Enhancements

- **ETA Calculations** - Added queue position estimates based on average job completion times
- **Reduced Moderator Checks** - Initial reduction of moderator activity tracking (later fully removed)
- **Enhanced Search Strategy** - Improved database + API combination logic

### 🔧 Technical Changes

- Added `_calculate_average_job_time()` function for ETA estimation
- Updated `_apply_queue_positions()` to include `eta_seconds`
- Refactored status assignment logic for recent runs
- Fixed search functionality import issues

### 📝 Configuration

- Updated default PORT to 8383 in `.env.example` and README for consistency
- Enhanced configuration validation warnings

---

## [2025.11.0.0] - 2025-11-09

### 🎉 Initial Major Release

### ✨ Added

- **Core Search Functionality** - Manual subreddit searches with advanced filtering
- **All The Subs Database** - Browse 3+ million cached subreddits
- **Auto-Ingest Worker** - Scheduled background searches every 3 hours
- **Random Search Worker** - Discover new subreddits using random keywords
- **Volunteer Node System** - Community-contributed nodes for distributed data collection
- **Phone Home Feature** - Optional syncing with main database
- **CSV Export** - Download search results for analysis
- **REST API** - Programmatic access to database and search functionality
- **PostgreSQL Support** - Production-ready database option alongside SQLite
- **In-Memory TTL Caching** - Fast queries with automatic cache expiration
- **Queue Management** - Handle concurrent searches with automatic queuing
- **Real-Time Progress** - JavaScript polling for live search updates
- **Node Management** - Web interface for volunteer node registration and updates
- **Email Notifications** - Send management links to volunteer node operators
- **Nightly Cleanup** - Remove broken nodes and stale data automatically

### 🎨 UI/UX

- **Modern Design** - Tailwind CSS with gradient accents and smooth animations
- **Responsive Layout** - Works on desktop, tablet, and mobile
- **Dark Theme** - Eye-friendly dark color scheme with brand colors (green #2BA84A, yellow #FBE36B)
- **Hero Graphics** - Custom SVG assets for branding
- **Progress Indicators** - Visual feedback for long-running operations
- **Status Badges** - Color-coded indicators for job states (queued, running, complete, error)

### 🔧 Core Features

- **Advanced Filtering**:
  - Keyword search in subreddit names
  - Subscriber count range (min/max)
  - Unmoderated only option
  - NSFW filter (include/exclude)
  - Activity filters (active after/inactive before date)
- **Dual Data Sources**:
  - Database search (fast, cached)
  - Reddit API search (fresh, real-time)
  - Intelligent combination of both
- **Background Workers**:
  - Auto-ingest: Scheduled keyword searches
  - Random search: Discovery via random words
  - Node cleanup: Remove stale data
- **Volunteer Nodes**:
  - Private management links (no login required)
  - Health status tracking (active/pending/broken)
  - Automatic cleanup after 7 days broken
  - Email notifications for registration

### 🗄️ Database

- **SQLite** - Default for development and small deployments
- **PostgreSQL** - Optional for production and high concurrency
- **Tables**:
  - `query_runs` - Job history and metadata
  - `subreddits` - Subreddit data with automatic deduplication
  - `volunteer_nodes` - Community node registry
- **Indexes** - Optimized for common queries (subscribers, name, updated_at)
- **WAL Mode** - Write-Ahead Logging for better concurrent access

### 📦 Dependencies

- Python 3.11+
- Flask 3.0+
- PRAW 7.7+ (Python Reddit API Wrapper)
- SQLite (included) or PostgreSQL (optional)
- Tailwind CSS (CDN)
- Vanilla JavaScript (no frameworks)

### 🚀 Deployment

- **Docker Support** - Containerized deployment with docker-compose
- **Systemd Service** - Run as background service on Linux
- **Cloud Platforms** - Deploy to Fly.io, Railway, Heroku, etc.
- **Environment Configuration** - Comprehensive .env.example template
- **Nginx Configuration** - Reverse proxy setup for production

### 📝 Documentation

- Initial README with basic setup instructions
- Environment variable documentation in .env.example
- Inline code comments for complex logic

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| **2025.11.01.0** | 2025-11-12 | **Major overhaul** - 60-75% faster searches, removed mod activity tracking, comprehensive docs |
| **2025.11.0.1** | 2025-11-11 | Performance improvements - ETA calculations, reduced mod checks |
| **2025.11.0.0** | 2025-11-09 | **Initial release** - Core functionality, volunteer nodes, PostgreSQL support |

---

## Upgrade Guide

### Upgrading to 2025.11.01.0

1. **Pull Latest Code:**
   ```bash
   cd reddit-sub-analyzer
   git pull origin main
   ```

2. **Update Dependencies** (no changes, but verify):
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Database Migration** (automatic, no action needed):
   - Existing moderator activity data will be preserved
   - New searches will not fetch moderator activity
   - No schema changes required

4. **Configuration Updates** (optional):
   ```bash
   # Update .env if you want to adjust rate limiting
   SUBSEARCH_RATE_LIMIT_DELAY=0.15  # New default (was 0.2)
   ```

5. **Restart Application:**
   ```bash
   # Systemd
   sudo systemctl restart subsearch

   # Docker
   docker-compose restart

   # Manual
   python -m subsearch.web_app
   ```

6. **Verify:**
   - Check version in footer: should show `2025.11.01.0`
   - Run a test search: should complete in 2-4 minutes for 1000 subs
   - Check logs: no moderator activity warnings

---

## Breaking Changes

### 2025.11.01.0

- **Moderator Activity Tracking Removed** - If you rely on `last_mod_activity_utc` field, be aware that new searches will return `None`. Historical data in the database is preserved.
- **Route Changes** - `/helpdocs` and `/docs/developers` routes removed (documentation moved to GitHub)

### 2025.11.0.0

- Initial release, no breaking changes

---

## Future Roadmap

See [README.md](../README.md#roadmap) for detailed roadmap.

### v2025.12 (December 2025)

- [ ] WebSocket support for real-time updates (eliminate polling)
- [ ] Advanced analytics dashboard
- [ ] Subreddit comparison tools
- [ ] API rate limit dashboard

### v2026.01 (January 2026)

- [ ] Machine learning for subreddit recommendations
- [ ] Trend analysis and visualization
- [ ] Export to additional formats (JSON, Excel)
- [ ] Mobile app

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

For questions or issues, visit [GitHub Issues](https://github.com/ericrosenberg1/reddit-sub-analyzer/issues).

---

**Versioning Convention:**

Sub Search uses Tesla-style versioning: `YYYY.MM.VV.v`

- `YYYY` - Year (4 digits)
- `MM` - Month (2 digits, zero-padded)
- `VV` - Version within month (2 digits, zero-padded, resets each month)
- `v` - Patch number (increments for hotfixes)

Examples:
- `2025.11.01.0` - November 2025, first version, no patches
- `2025.11.01.1` - November 2025, first version, first patch
- `2025.12.01.0` - December 2025, first version, no patches

**Automatic Version Bumping:**

```bash
# Bump version (automatically detects month change)
python scripts/bump_version.py

# Output: Version bumped: 2025.11.01.0 → 2025.11.01.1
```

---

*Last Updated: 2025-11-12*
*Current Version: 2025.11.01.0*
