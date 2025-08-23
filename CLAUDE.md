# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Plan and Review
Before you begin, write a detailed implementation plan in a file named claude/tasks/TASK_NAME.md

This plan should include:

A clear, detailed breakdown of the implementation steps.

The reasonsing behind your approach.

A list of specific tasks.

Focus on a Minimun Viable Product (MVP) to avoid over-planning. Once the plan is ready, please ask me to review it. Do not proceed with implementation until I have approved the plan.

## While Implementing
As you work, keep the plan updated. After you complete a task, append a detailed description of the changes, you have made to the plan. This ensures that progress and next steps are clear and can be easily haded over to the other agents/engineers if needed.

## Watch your context like a hawk: ⚠️ Critical: When context drops below 20%, start fresh. Before that:

Read and check if we should update CLAUDE.md based on changes we've done to this project thus far. Make sure there are no uncommitted changes.

## Project Overview

This is a Reddit monitoring system that watches r/glasgow and r/glasgowmarket for posts containing keywords like "free ticket", "giveaway", etc., and sends **dual notifications** via both HTML email and Telegram when matches are found. The system is designed to run completely free using Reddit API, Gmail SMTP, Telegram Bot API, and GitHub Actions.

## Core Architecture

**Single-File Design**: The entire monitoring logic is contained in `main.py` as a `RedditMonitor` class with these key responsibilities:
- Reddit API integration via PRAW library
- **Dual notification system**: HTML email + Telegram bot messaging
- **24-hour post filtering**: Only processes recent posts from last day
- Duplicate post tracking using JSON file storage
- Environment-based configuration
- Dual deployment mode (local continuous vs GitHub Actions single-run)

**State Management**: Uses `seen_posts.json` to track processed Reddit post IDs and prevent duplicate notifications across runs.

**Deployment Modes**:
- **Local**: Continuous monitoring loop with configurable intervals
- **GitHub Actions**: Single check triggered every 15 minutes via cron schedule

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set up configuration
cp .env.example .env
# Edit .env with your credentials

# Run locally (continuous monitoring)
python main.py

# Test syntax validation
python -m py_compile main.py
```

### Testing
```bash
# Test both email and Telegram notifications
python main.py test

# Test only email notification
python main.py test email

# Test only Telegram notification  
python main.py test telegram

# Manual testing (legacy methods)
python -c "from main import RedditMonitor; monitor = RedditMonitor(); monitor.send_email('Test', '<h1>Test Message</h1>')"
python -c "from main import RedditMonitor; monitor = RedditMonitor(); monitor.send_telegram_message('<b>Test</b> message')"

# View logs
tail -f reddit_monitor.log

# Check seen posts
cat seen_posts.json
```

### GitHub Actions Deployment
- Configure secrets in repository settings (7-9 required: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, EMAIL_USER, EMAIL_PASSWORD, NOTIFICATION_EMAIL, KEYWORDS)
- Optional Telegram secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- Workflow runs automatically every 15 minutes
- Manual trigger available via workflow_dispatch
- Uses artifact persistence for seen_posts.json across runs

## Configuration System

**Environment Variables**: All configuration via environment variables with sensible defaults
- Required: Reddit API credentials, email credentials
- Optional: SMTP settings, **Telegram bot credentials**, monitoring parameters, keyword customization

**Runtime Behavior**:
- Detects GitHub Actions environment via `GITHUB_ACTIONS` env var
- Switches between continuous and single-run modes automatically
- Validates all required configuration on startup

**Subreddit Configuration**: Currently hardcoded to ['glasgow', 'glasgowmarket'] in the RedditMonitor.__init__ method

## Key Implementation Details

**Multi-tier Matching System**: 
- **Flair Priority**: r/glasgow monitors "Ticket share. No adverts, free tickets only" flair first
- **Keyword Matching**: Case-insensitive search across both post titles and selftext content
- **Lenient Mode**: r/glasgowmarket uses 48-hour window (less active subreddit)

**Time Filtering**: 
- Standard: 24-hour window for active subreddits (r/glasgow)
- Lenient: 48-hour window for less active subreddits (r/glasgowmarket)

**Dual Notifications**: 
- **HTML Email**: Professional formatting with clickable links, styled cards, and rich content
- **Telegram Bot**: Instant mobile notifications with group chat support and emoji formatting

**Error Handling**: Comprehensive error handling with HTML email notifications for system failures. Individual notification failures don't stop the other systems.

**Rate Limiting**: Respects Reddit API limits by processing limited number of posts per run (default 50) and reasonable check intervals (minimum 15 minutes).

**Logging**: Dual logging to both file (reddit_monitor.log) and console with timestamps and detailed error information.

## File Structure

- `main.py` - Core monitoring application (single class, ~400 lines with dual notifications)
- `requirements.txt` - Python dependencies (praw, python-dotenv, requests)
- `.env.example` - Configuration template including Telegram settings
- `TELEGRAM_SETUP.md` - Step-by-step Telegram bot setup guide
- `PROJECT_INDEX.md` - Comprehensive project documentation and API reference
- `.github/workflows/reddit_watcher.yml` - GitHub Actions automation
- `seen_posts.json` - Generated state file for duplicate tracking
- `reddit_monitor.log` - Generated log file

## Common Modifications

**Adding Subreddits**: Modify `self.subreddits` list in `RedditMonitor.__init__`
**Keyword Changes**: Update KEYWORDS environment variable (comma-separated)
**Email Provider**: Change SMTP_SERVER and SMTP_PORT environment variables
**Monitoring Frequency**: Adjust CHECK_INTERVAL_MINUTES and cron schedule in workflow