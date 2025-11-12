# Sub Search - Reddit Subreddit Discovery Tool

[![GitHub stars](https://img.shields.io/github/stars/ericrosenberg1/reddit-sub-analyzer?style=for-the-badge)](https://github.com/ericrosenberg1/reddit-sub-analyzer/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/ericrosenberg1/reddit-sub-analyzer?style=for-the-badge)](https://github.com/ericrosenberg1/reddit-sub-analyzer/network)
[![GitHub issues](https://img.shields.io/github/issues/ericrosenberg1/reddit-sub-analyzer?style=for-the-badge)](https://github.com/ericrosenberg1/reddit-sub-analyzer/issues)
[![Python](https://img.shields.io/badge/python-3.11+-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-3.0+-green?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com/)
[![Reddit API](https://img.shields.io/badge/reddit-API-orange?style=for-the-badge&logo=reddit)](https://www.reddit.com/dev/api/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Current Version](https://img.shields.io/badge/version-2025.11.01.0-brightgreen?style=for-the-badge)](VERSION)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](CONTRIBUTING.md)

> 🔍 Discover, analyze, and export Reddit communities with the largest community-maintained subreddit database.

**Sub Search** is an open-source tool for discovering Reddit subreddits with advanced filtering, real-time search, and a constantly-growing database of 3+ million subreddits. Perfect for researchers, marketers, community builders, and Reddit enthusiasts.

[🚀 Live Demo](https://allthesubs.ericrosenberg.com) • [📖 User Guide](docs/HELP.md) • [💻 Developer Docs](docs/DEVELOPERS.md) • [📋 Changelog](docs/CHANGELOG.md)

---

## ✨ Features

### 🔎 Powerful Search
- **Advanced Filtering** - Search by keyword, subscriber count, NSFW status, and moderator activity
- **Real-Time Progress** - Live updates with ETA calculations and smooth animations
- **Database + API** - Query cached results instantly or fetch fresh data from Reddit

### 📊 Comprehensive Database
- **3+ Million Subreddits** - Continuously growing community-maintained index
- **Auto-Ingest** - Automated discovery of new subreddits every 3 hours
- **Random Discovery** - Background bot finds subreddits using random keywords

### 🌐 Distributed Network
- **Volunteer Nodes** - Run your own discovery node to contribute to the database
- **Phone Home** - Share discoveries with the main database
- **No Central Bottleneck** - Decentralized data collection

### 📤 Export & Integration
- **CSV Export** - Download search results for analysis
- **REST API** - Programmatic access to the database
- **Real-Time Updates** - WebSocket-like polling for live progress

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Reddit API Credentials** ([Get them here](https://www.reddit.com/prefs/apps))
- **SQLite** (included) or **PostgreSQL** (optional)

### Installation (Local)

```bash
# 1. Clone the repository
git clone https://github.com/ericrosenberg1/reddit-sub-analyzer.git
cd reddit-sub-analyzer

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your Reddit API credentials

# 5. Initialize database
python -c "from subsearch.storage import init_db; init_db()"

# 6. Run the application
python -m subsearch.web_app
```

Visit `http://localhost:5055` 🎉

### Docker Deployment

```bash
# Build image
docker build -t sub-search .

# Run container
docker run -d \
  -p 5055:5055 \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  --name sub-search \
  sub-search
```

---

## 📖 Documentation

- **[User Guide](docs/HELP.md)** - How to use Sub Search (no coding required)
- **[Developer Guide](docs/DEVELOPERS.md)** - Technical documentation for contributors
- **[API Documentation](docs/API.md)** - REST API reference
- **[Changelog](docs/CHANGELOG.md)** - Version history and release notes

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Web Interface                       │
│              (Flask + Tailwind CSS + HTMX)              │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                  Core Application                        │
│                  (Python + Flask)                        │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Search    │  │   Queue     │  │   Storage   │    │
│  │   Engine    │  │   Manager   │  │   Layer     │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                External Integrations                     │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Reddit    │  │   Database  │  │ Phone Home  │    │
│  │     API     │  │  SQLite/PG  │  │   Sync      │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Key Components

- **Search Engine** - Queries Reddit API with intelligent rate limiting
- **Queue Manager** - Handles concurrent searches with ETA calculations
- **Storage Layer** - Caches results in SQLite/PostgreSQL
- **Auto-Ingest** - Background worker for continuous discovery
- **Phone Home** - Optional sync with central database

---

## 🛠️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDDIT_CLIENT_ID` | Reddit app client ID | Required |
| `REDDIT_CLIENT_SECRET` | Reddit app secret | Required |
| `REDDIT_USERNAME` | Reddit account username | Optional |
| `REDDIT_PASSWORD` | Reddit account password | Optional |
| `SUBSEARCH_RATE_LIMIT_DELAY` | Delay between API calls (seconds) | 0.15 |
| `SUBSEARCH_PUBLIC_API_LIMIT` | Max subreddits to check per search | 2000 |
| `AUTO_INGEST_ENABLED` | Enable automatic discovery | 1 |
| `AUTO_INGEST_INTERVAL_MINUTES` | Time between auto-ingest runs | 180 |
| `PHONE_HOME` | Enable syncing with main database | false |

See [.env.example](.env.example) for complete configuration options.

---

## 🌐 Cloud Deployment

### Deploy to Fly.io

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Deploy
fly launch
fly deploy
```

### Deploy to Railway

1. Fork this repository
2. Connect to Railway
3. Add environment variables
4. Deploy

### Deploy to Heroku

```bash
# Install Heroku CLI
# https://devcenter.heroku.com/articles/heroku-cli

# Create app
heroku create your-app-name

# Set environment variables
heroku config:set REDDIT_CLIENT_ID=your_id
heroku config:set REDDIT_CLIENT_SECRET=your_secret

# Deploy
git push heroku main
```

---

## 🤝 Running a Volunteer Node

Help grow the database by running your own discovery node!

### Setup

```bash
# 1. Follow Quick Start installation

# 2. Enable auto-ingest in .env
AUTO_INGEST_ENABLED=1
AUTO_INGEST_INTERVAL_MINUTES=180

# 3. Optional: Enable phone home to share discoveries
PHONE_HOME=true
PHONE_HOME_ENDPOINT=https://allthesubs.ericrosenberg.com/api/ingest
PHONE_HOME_TOKEN=your_token_here

# 4. Run continuously
python -m subsearch.web_app
```

### Register Your Node

Visit the [Nodes page](https://allthesubs.ericrosenberg.com/nodes/join) to register your volunteer node and get a management link.

---

## 🧪 Development

### Setup Development Environment

```bash
# Clone and setup
git clone https://github.com/ericrosenberg1/reddit-sub-analyzer.git
cd reddit-sub-analyzer

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (including dev tools)
pip install -r requirements.txt
pip install -r requirements-dev.txt  # If exists

# Run in debug mode
export FLASK_DEBUG=1
python -m subsearch.web_app
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=subsearch --cov-report=html

# Run specific test file
pytest tests/test_search.py
```

### Code Quality

```bash
# Format code
black subsearch/

# Lint
flake8 subsearch/
pylint subsearch/

# Type checking
mypy subsearch/
```

---

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Ways to Contribute

- 🐛 **Report Bugs** - [Open an issue](https://github.com/ericrosenberg1/reddit-sub-analyzer/issues/new)
- 💡 **Suggest Features** - Share your ideas in discussions
- 📝 **Improve Docs** - Help make documentation better
- 🔧 **Submit PRs** - Fix bugs or add features
- 🌐 **Run a Node** - Help grow the database

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Commit your changes (`git commit -m 'feat: add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

---

## 📊 Performance

- **Search Speed**: 2-4 minutes for 1000 subreddits (60-75% faster than v1.0)
- **Database Size**: 3+ million subreddits and growing
- **API Efficiency**: Intelligent rate limiting with 0.15s delays
- **Real-Time Updates**: Status polling every 1 second

See [PERFORMANCE_OPTIMIZATIONS.md](PERFORMANCE_OPTIMIZATIONS.md) for details.

---

## 🔐 Security

- **API Key Protection** - Credentials stored securely in environment variables
- **Rate Limiting** - Respects Reddit API limits
- **Input Sanitization** - All user input is validated
- **CSRF Protection** - Flask CSRF tokens enabled

Found a security issue? Please email security@ericrosenberg.com instead of opening a public issue.

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **PRAW** - Python Reddit API Wrapper
- **Flask** - Web framework
- **Tailwind CSS** - Styling
- **Reddit** - API and data source
- **Contributors** - Everyone who has helped improve Sub Search

---

## 📞 Support

- **Documentation**: [User Guide](docs/HELP.md) | [Developer Docs](docs/DEVELOPERS.md)
- **Issues**: [GitHub Issues](https://github.com/ericrosenberg1/reddit-sub-analyzer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ericrosenberg1/reddit-sub-analyzer/discussions)
- **Email**: contact@ericrosenberg.com

---

## 🗺️ Roadmap

### v2025.12 (December 2025)
- [ ] WebSocket support for real-time updates
- [ ] Advanced analytics dashboard
- [ ] Subreddit comparison tools
- [ ] API rate limit dashboard

### v2026.01 (January 2026)
- [ ] Machine learning for subreddit recommendations
- [ ] Trend analysis and visualization
- [ ] Export to additional formats (JSON, Excel)
- [ ] Mobile app

See [ROADMAP.md](ROADMAP.md) for the complete roadmap.

---

## 📈 Stats

- **3+ Million** subreddits indexed
- **500+ searches** per day
- **20+ volunteer nodes** contributing
- **99.9%** uptime

---

<p align="center">
  Made with ❤️ by <a href="https://ericrosenberg.com">Eric Rosenberg</a>
  <br>
  <sub>Current Version: <strong>2025.11.01.0</strong></sub>
</p>
