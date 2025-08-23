# 📱 Telegram Bot Setup Guide

Your Reddit Monitor now supports **dual notifications**: beautiful HTML emails + instant Telegram messages!

## 🚀 Quick Setup (10 minutes)

### Step 1: Create a Telegram Bot
1. Open Telegram and search for `@BotFather`
2. Start a chat and send `/newbot`
3. Follow prompts to name your bot (e.g., "Glasgow Reddit Monitor")
4. Copy the **bot token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Get Your Chat ID

**For Personal Messages:**
1. Send any message to your new bot
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Look for `"chat":{"id": NUMBER}` and copy that number

**For Group Chat:**
1. Add your bot to the group
2. Send a message that mentions the bot: `@YourBotName hello`
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Find the group chat ID (usually negative number like `-123456789`)

### Step 3: Update Your .env File
```bash
# Add these lines to your .env file:
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=your_chat_id_here
```

### Step 4: Install Dependencies & Test
```bash
pip install -r requirements.txt
python main.py
```

## 🎯 What You'll Get

**Telegram notifications include:**
- 🎫 Instant alerts with Reddit post links
- 📱 Clickable links to view posts
- 👤 Author and subreddit info
- 🔍 Matched keywords highlighted
- ⏰ Post timestamps

**Plus your existing beautiful HTML emails with:**
- 🎨 Professional formatting with colors
- 🔗 Clickable Reddit links
- 📋 Organized post cards
- 📧 Gmail-optimized layout

## 🔧 Troubleshooting

**Bot not responding?**
- Make sure bot token is correct
- Check that chat ID is accurate (include the minus sign for groups)

**Getting "Forbidden" errors?**
- For groups: Make sure the bot is still in the group
- For private chats: Send `/start` to your bot first

**Want to disable Telegram?**
- Simply don't set the TELEGRAM_BOT_TOKEN in your .env file
- The system will continue with email-only notifications

## 💡 Pro Tips

- **Group Setup**: Add the bot to a family/friends group for shared notifications
- **Multiple Chats**: You can only send to one chat ID per instance
- **Message Limits**: Telegram has a 4096 character limit, so very long posts may be truncated
- **Free Forever**: Telegram Bot API is completely free with no limits

Your Reddit Monitor now gives you the best of both worlds! 🚀