# Glasgow Reddit Monitor 🎫

Automatically monitors r/glasgow and r/glasgowmarket for posts containing keywords like "free ticket", "giveaway", etc., and sends email notifications when matches are found.

## Features

- 🔍 Monitors multiple subreddits simultaneously
- 📧 Email notifications with post details and direct links
- 🚫 Duplicate detection to avoid repeat notifications
- ⚙️ Fully configurable keywords and settings
- 🆓 Completely free to run (uses only free services)
- 🤖 Runs locally or automated via GitHub Actions
- 📝 Comprehensive logging and error handling

## Quick Start

### 1. Set up Reddit API

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Choose "script" as the app type
4. Note down your `client_id` (under the app name) and `client_secret`

### 2. Set up Gmail for notifications

1. Enable 2-factor authentication on your Gmail account
2. Generate an App Password: https://support.google.com/accounts/answer/185833
3. Use this App Password (not your regular password) in the configuration

### 3. Local Setup

```bash
# Clone and enter the repository
git clone https://github.com/abhibansal60/glasgow-reddit-monitor.git
cd glasgow-reddit-monitor

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your credentials (see Configuration section)

# Run the monitor
python main.py
```

### 4. GitHub Actions Setup (Free Cloud Automation)

1. Fork this repository to your GitHub account
2. Go to your repository Settings → Secrets and Variables → Actions
3. Add the following secrets:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `REDDIT_CLIENT_ID` | Reddit app client ID | `abc123xyz` |
| `REDDIT_CLIENT_SECRET` | Reddit app client secret | `def456uvw` |
| `REDDIT_USER_AGENT` | Reddit app user agent | `GlasgowRedditMonitor/1.0` |
| `EMAIL_USER` | Your Gmail address | `your.email@gmail.com` |
| `EMAIL_PASSWORD` | Gmail App Password | `abcd efgh ijkl mnop` |
| `NOTIFICATION_EMAIL` | Where to send alerts | `alerts@gmail.com` |
| `KEYWORDS` | Comma-separated keywords | `free ticket,giveaway,discount` |

**Optional secrets (will use defaults if not set):**
- `SMTP_SERVER` (default: `smtp.gmail.com`)
- `SMTP_PORT` (default: `587`)
- `CHECK_INTERVAL_MINUTES` (default: `15`)
- `MAX_POSTS_PER_RUN` (default: `50`)

4. The workflow will run automatically every 15 minutes
5. You can also trigger it manually from the Actions tab

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Reddit API (required)
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=GlasgowRedditMonitor/1.0

# Email settings (required)
EMAIL_USER=your.email@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
NOTIFICATION_EMAIL=where.to.send@alerts.com

# Optional settings
KEYWORDS=free ticket,cheap ticket,giveaway,free entry,discount,spare ticket
CHECK_INTERVAL_MINUTES=15
MAX_POSTS_PER_RUN=50
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

### Monitored Subreddits

Currently monitors:
- r/glasgow
- r/glasgowmarket

### Default Keywords

- free ticket
- cheap ticket
- giveaway
- free entry
- discount
- spare ticket
- extra ticket

## How It Works

1. **Monitoring**: Checks the latest posts in configured subreddits
2. **Keyword Matching**: Searches post titles and content for configured keywords
3. **Duplicate Prevention**: Tracks seen posts in `seen_posts.json`
4. **Notifications**: Sends email with post details when matches are found
5. **Logging**: Records all activity in `reddit_monitor.log`

### Running Modes

- **Local Continuous**: Runs indefinitely, checking every N minutes
- **GitHub Actions**: Single check every 15 minutes (free tier limit)

## Files Generated

- `seen_posts.json` - Tracks processed posts to avoid duplicates
- `reddit_monitor.log` - Detailed activity logs

## Cost Analysis ✅ 100% Free

| Service | Usage | Cost |
|---------|--------|------|
| Reddit API | 60 requests/hour | **Free** |
| Gmail SMTP | ~100 emails/month | **Free** (up to 500/day) |
| GitHub Actions | 1440 minutes/month | **Free** (2000/month limit) |
| **Total** | | **$0/month** |

## Troubleshooting

### Common Issues

**Reddit API Errors:**
- Verify your `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`
- Check if your Reddit app is set as "script" type
- Ensure your `REDDIT_USER_AGENT` is descriptive

**Email Issues:**
- Use Gmail App Password, not your regular password
- Enable 2FA on your Google account first
- Check spam folder for notifications

**GitHub Actions Issues:**
- Verify all secrets are set correctly (no extra spaces)
- Check the Actions tab for error logs
- Ensure your repository is not private (or you have Actions enabled)

### Debugging

Check logs for detailed error information:
```bash
# View recent logs
tail -f reddit_monitor.log

# View all logs
cat reddit_monitor.log
```

### Testing

Test email functionality:
```python
# Quick test script
from main import RedditMonitor
monitor = RedditMonitor()
monitor.send_email("Test", "This is a test email from Reddit Monitor")
```

## Customization

### Adding More Subreddits

Edit `main.py`, modify the `subreddits` list:
```python
self.subreddits = ['glasgow', 'glasgowmarket', 'ScotlandForSale']
```

### Custom Keywords

Update your `.env` file or GitHub secrets:
```
KEYWORDS=concert tickets,festival passes,event tickets,free entry,giveaway
```

### Different Email Provider

For Outlook/Hotmail:
```
SMTP_SERVER=smtp-mail.outlook.com
SMTP_PORT=587
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally
5. Submit a pull request

## License

MIT License - feel free to use and modify as needed.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review the logs in `reddit_monitor.log`
3. Open an issue on GitHub

---

**Happy monitoring! May you never miss a free ticket again! 🎟️**