# 📋 Glasgow Reddit Monitor - Project Index

## 🎯 Project Overview

A comprehensive Reddit monitoring system that watches r/glasgow and r/glasgowmarket for posts containing keywords like "free ticket", "giveaway", etc., and sends **dual notifications** via both HTML email and Telegram when matches are found.

**Status**: ✅ Enhanced with dual notifications, HTML email, and 24-hour filtering  
**Last Updated**: 2025-08-23  
**Deployment**: GitHub Actions + Local execution support

---

## 📁 Project Structure

```
glasgow-reddit-monitor/
├── 📄 main.py                    # Core monitoring application (single class)
├── 📄 requirements.txt           # Python dependencies (praw, dotenv, requests)
├── 📄 .env.example              # Configuration template with Telegram support
├── 📄 .gitignore                # Git ignore patterns
├── 📄 seen_posts.json           # Generated: Post tracking state
├── 📄 reddit_monitor.log        # Generated: Application logs
├── 📄 README.md                 # Basic project README
├── 📄 CLAUDE.md                 # Claude Code AI instructions
├── 📄 TELEGRAM_SETUP.md         # Telegram bot setup guide
├── 📄 PROJECT_INDEX.md          # This comprehensive index
├── 📁 .github/workflows/
│   └── 📄 reddit_watcher.yml    # GitHub Actions automation
├── 📁 .serena/                  # Serena MCP project files
└── 📁 __pycache__/              # Python cache files
```

---

## 🏗️ Architecture Overview

### Core Components

#### **RedditMonitor Class** (`main.py`)
Single-responsibility class containing all monitoring logic:

**Configuration Management:**
- `__init__()` - Environment-based configuration
- `_validate_config()` - Required settings validation  
- `_parse_keywords()` - Keyword processing

**Reddit Integration:**
- `_init_reddit()` - PRAW Reddit API setup
- `check_subreddit()` - Individual subreddit monitoring
- `contains_keywords()` - Keyword matching logic

**Notification System:**
- `send_email()` - HTML email notifications
- `send_telegram_message()` - Telegram bot messaging
- `format_notification_email()` - HTML email formatting
- `format_telegram_message()` - Telegram message formatting

**State Management:**
- `load_seen_posts()` - JSON file state loading
- `save_seen_posts()` - JSON file state persistence

**Execution Modes:**
- `run_single_check()` - Single run (GitHub Actions)
- `run_continuous()` - Continuous monitoring (local)

### Key Features

#### **✅ Dual Notification System**
- **HTML Email**: Professional formatting, clickable links, detailed cards
- **Telegram Bot**: Instant mobile notifications, group chat support
- **Smart Fallbacks**: Independent operation if one system fails

#### **✅ Enhanced Filtering**
- **24-Hour Window**: Only processes posts from last 24 hours
- **Duplicate Prevention**: Tracks seen posts across sessions
- **Keyword Matching**: Case-insensitive title + content search

#### **✅ Deployment Flexibility**
- **Local Mode**: Continuous monitoring with configurable intervals
- **GitHub Actions**: Scheduled runs every 15 minutes
- **Auto-Detection**: Environment-based mode switching

---

## ⚙️ Configuration System

### Required Environment Variables
```bash
# Reddit API (required)
REDDIT_CLIENT_ID=your_reddit_client_id_here
REDDIT_CLIENT_SECRET=your_reddit_client_secret_here
REDDIT_USER_AGENT=GlasgowRedditMonitor/1.0

# Email notifications (required)
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password_here
NOTIFICATION_EMAIL=where_to_send_alerts@gmail.com
```

### Optional Environment Variables
```bash
# SMTP customization
SMTP_SERVER=smtp.gmail.com      # Default: Gmail
SMTP_PORT=587                   # Default: Gmail TLS

# Telegram notifications (optional)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=your_chat_id_here

# Monitoring behavior
KEYWORDS=free ticket,giveaway   # Default: comprehensive list
CHECK_INTERVAL_MINUTES=15       # Default: 15 minutes
MAX_POSTS_PER_RUN=50           # Default: 50 posts per check
```

---

## 🚀 Deployment Modes

### **Local Development**
```bash
# Setup
cp .env.example .env
# Edit .env with your credentials
pip install -r requirements.txt

# Run continuous monitoring
python main.py

# Test email functionality
python -c "from main import RedditMonitor; monitor = RedditMonitor(); monitor.send_email('Test', '<h1>Test</h1>')"
```

### **GitHub Actions**
- **Trigger**: Cron schedule every 15 minutes
- **Secrets**: 7 required repository secrets
- **Artifacts**: `seen_posts.json` persistence across runs
- **Manual**: `workflow_dispatch` for manual triggering

---

## 📊 API Documentation

### RedditMonitor Class Methods

#### **Core Methods**

**`__init__()`**
- Initializes configuration from environment variables
- Validates required settings
- Sets up Reddit API client
- Configures dual notification systems

**`run_single_check()`**
- Executes one complete monitoring cycle
- Processes all configured subreddits
- Sends dual notifications for matches
- Updates seen posts state
- **Used by**: GitHub Actions mode

**`run_continuous()`**
- Runs indefinite monitoring loop
- Configurable sleep intervals
- Graceful keyboard interrupt handling
- **Used by**: Local development mode

#### **Reddit Integration**

**`check_subreddit(subreddit_name: str) -> List[Dict]`**
- Monitors single subreddit for new posts
- Applies 24-hour time filtering
- Tracks seen posts to prevent duplicates
- Returns matching post information
- **Time Complexity**: O(n) where n = MAX_POSTS_PER_RUN

**`contains_keywords(text: str) -> List[str]`**
- Case-insensitive keyword matching
- Searches both title and post content
- Returns list of matched keywords
- **Algorithm**: Simple string containment

#### **Notification System**

**`send_email(subject: str, body: str, is_html: bool = True)`**
- Sends HTML or plain text email via SMTP
- Gmail-optimized with TLS encryption
- Comprehensive error handling and logging
- **Dependencies**: smtplib, email.mime

**`send_telegram_message(message: str)`**
- Sends formatted message via Telegram Bot API
- Supports HTML formatting and link previews
- Optional feature (graceful degradation)
- **API Endpoint**: `https://api.telegram.org/bot<token>/sendMessage`

**`format_notification_email(posts: List[Dict]) -> tuple`**
- Generates professional HTML email layout
- Creates styled cards for each post
- Includes clickable Reddit links
- Returns (subject, html_body) tuple

**`format_telegram_message(posts: List[Dict]) -> str`**
- Creates mobile-optimized message format
- Handles 4096 character Telegram limit
- Includes clickable links and emoji formatting
- Smart truncation for long content

#### **State Management**

**`load_seen_posts() -> Set[str]`**
- Loads post IDs from JSON file
- Handles missing or corrupted files gracefully
- Returns set of previously seen post IDs

**`save_seen_posts()`**
- Persists seen post IDs to JSON file
- Includes timestamp metadata
- Atomic write operation for data integrity

---

## 📈 Performance & Monitoring

### **Rate Limiting**
- **Reddit API**: Respects PRAW default limits
- **Email SMTP**: No artificial limits
- **Telegram API**: 30 messages/second (unused at current scale)

### **Resource Usage**
- **Memory**: ~50MB Python process
- **Disk**: <1MB for state files and logs
- **Network**: Minimal API calls (50 posts every 15 minutes)

### **Error Handling**
- Individual subreddit failures don't stop monitoring
- Email notification failures are logged but don't block Telegram
- Telegram failures don't affect email notifications
- Comprehensive logging for debugging

### **Monitoring**
- **Logs**: Both file (`reddit_monitor.log`) and console output
- **State**: JSON tracking of processed posts
- **Health**: Email notifications for system errors

---

## 🔧 Development Guidelines

### **Code Organization**
- **Single Class Design**: All logic in `RedditMonitor` class
- **Separation of Concerns**: Clear method responsibilities
- **Configuration-Driven**: Environment variable based setup
- **Error Isolation**: Individual component failure handling

### **Testing Strategy**
```bash
# Syntax validation
python -m py_compile main.py

# Configuration testing
python -c "from main import RedditMonitor; RedditMonitor()"

# Email testing
python -c "from main import RedditMonitor; monitor = RedditMonitor(); monitor.send_email('Test', '<h1>Test Message</h1>')"

# Telegram testing (if configured)
python -c "from main import RedditMonitor; monitor = RedditMonitor(); monitor.send_telegram_message('<b>Test</b> message')"
```

### **Common Modifications**

**Add Subreddits:**
```python
# In RedditMonitor.__init__
self.subreddits = ['glasgow', 'glasgowmarket', 'new_subreddit']
```

**Modify Keywords:**
```bash
# In .env file
KEYWORDS=new keyword,another keyword,free stuff
```

**Change Notification Frequency:**
```bash
# In .env file
CHECK_INTERVAL_MINUTES=30
```

---

## 🚨 Troubleshooting

### **Common Issues**

**Email Not Sending:**
- Check Gmail App Password (not regular password)
- Verify SMTP settings for non-Gmail providers
- Check firewall/network restrictions on port 587

**Reddit API Errors:**
- Verify Reddit App credentials
- Check Reddit API status
- Ensure user agent is descriptive

**Telegram Not Working:**
- Verify bot token from @BotFather
- Check chat ID (include minus sign for groups)
- Ensure bot has group permissions

**No Posts Found:**
- Verify subreddit names are correct
- Check keywords are relevant
- Ensure 24-hour window isn't too restrictive

### **Debug Commands**
```bash
# Check configuration
python -c "from main import RedditMonitor; m = RedditMonitor(); print(f'Monitoring: {m.subreddits}, Keywords: {m.keywords}')"

# Test Reddit connection
python -c "from main import RedditMonitor; m = RedditMonitor(); print(m.reddit.user.me())"

# View recent posts
tail -f reddit_monitor.log

# Check seen posts
cat seen_posts.json | jq '.'
```

---

## 📚 Related Documentation

- **[TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)** - Step-by-step Telegram bot configuration
- **[CLAUDE.md](CLAUDE.md)** - AI development guidelines and project instructions
- **[README.md](README.md)** - Basic project overview and quick start
- **[.env.example](.env.example)** - Complete configuration template

---

## 🔄 Changelog

### **v2.0 - Enhanced Notifications** (2025-08-23)
- ✅ Added dual notification system (Email + Telegram)
- ✅ Implemented HTML email formatting with clickable links
- ✅ Added 24-hour post filtering
- ✅ Created comprehensive Telegram bot integration
- ✅ Enhanced error handling and logging
- ✅ Updated documentation and setup guides

### **v1.0 - Initial Release**
- Basic Reddit monitoring functionality
- Plain text email notifications
- GitHub Actions deployment
- Simple keyword matching

---

*This index provides comprehensive documentation for the Glasgow Reddit Monitor project. For specific setup instructions, see the related documentation files.*