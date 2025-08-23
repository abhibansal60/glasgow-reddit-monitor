#!/usr/bin/env python3
"""
Glasgow Reddit Monitor
Monitors r/glasgow and r/glasgowmarket for ticket/giveaway posts and sends email notifications.
"""

import os
import json
import time
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Set
from dotenv import load_dotenv
import praw
import requests

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('reddit_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RedditMonitor:
    def __init__(self):
        self.reddit = None
        self.seen_posts_file = 'seen_posts.json'
        self.seen_posts: Set[str] = self.load_seen_posts()
        
        # Configuration from environment variables
        self.subreddits = ['glasgow', 'glasgowmarket']
        self.keywords = self._parse_keywords(os.getenv('KEYWORDS', 'free ticket,cheap ticket,giveaway,free entry,discount'))
        self.check_interval = int(os.getenv('CHECK_INTERVAL_MINUTES', '15')) * 60
        self.max_posts_per_run = int(os.getenv('MAX_POSTS_PER_RUN', '50'))
        
        # Flair configuration for priority monitoring
        self.flair_priority = {
            'glasgow': 'Ticket share. No adverts, free tickets only'
        }
        
        # Lenient mode for less active subreddits
        self.lenient_subreddits = ['glasgowmarket']
        
        # Email configuration
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.email_user = os.getenv('EMAIL_USER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.notification_email = os.getenv('NOTIFICATION_EMAIL')
        
        # Reddit API configuration
        self.reddit_client_id = os.getenv('REDDIT_CLIENT_ID')
        self.reddit_client_secret = os.getenv('REDDIT_CLIENT_SECRET')
        self.reddit_user_agent = os.getenv('REDDIT_USER_AGENT', 'GlasgowRedditMonitor/1.0')
        
        # Telegram configuration (optional)
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.enable_telegram = bool(self.telegram_bot_token and self.telegram_chat_id)
        
        self._validate_config()
        self._init_reddit()
    
    def _parse_keywords(self, keywords_str: str) -> List[str]:
        """Parse comma-separated keywords and clean them"""
        return [kw.strip().lower() for kw in keywords_str.split(',') if kw.strip()]
    
    def _validate_config(self):
        """Validate required configuration"""
        required_vars = [
            'EMAIL_USER', 'EMAIL_PASSWORD', 'NOTIFICATION_EMAIL',
            'REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET'
        ]
        
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        if not self.keywords:
            raise ValueError("No keywords specified in KEYWORDS environment variable")
    
    def _init_reddit(self):
        """Initialize Reddit API client"""
        try:
            self.reddit = praw.Reddit(
                client_id=self.reddit_client_id,
                client_secret=self.reddit_client_secret,
                user_agent=self.reddit_user_agent
            )
            # Test the connection
            self.reddit.user.me()
            logger.info("Reddit API initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Reddit API: {e}")
            raise
    
    def load_seen_posts(self) -> Set[str]:
        """Load previously seen post IDs from file"""
        try:
            if os.path.exists(self.seen_posts_file):
                with open(self.seen_posts_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('seen_posts', []))
        except Exception as e:
            logger.warning(f"Could not load seen posts: {e}")
        return set()
    
    def save_seen_posts(self):
        """Save seen post IDs to file"""
        try:
            data = {
                'seen_posts': list(self.seen_posts),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.seen_posts_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save seen posts: {e}")
    
    def contains_keywords(self, text: str) -> List[str]:
        """Check if text contains any keywords and return matches"""
        text_lower = text.lower()
        matches = []
        for keyword in self.keywords:
            if keyword in text_lower:
                matches.append(keyword)
        return matches

    
    def _check_flair_posts(self, subreddit, subreddit_name: str) -> List[Dict]:
        """Check for posts with priority flair"""
        flair_posts = []
        target_flair = self.flair_priority.get(subreddit_name)
        
        if not target_flair:
            return flair_posts
            
        try:
            logger.info(f"Checking flair posts for r/{subreddit_name} with flair: {target_flair}")
            
            # Search for posts with the specific flair
            for submission in subreddit.search(f'flair:"{target_flair}"', sort='new', time_filter='day', limit=20):
                if submission.id in self.seen_posts:
                    continue
                    
                # Check if post is from last 24 hours
                post_age_hours = (datetime.now().timestamp() - submission.created_utc) / 3600
                if post_age_hours > 24:
                    continue
                
                post_info = {
                    'id': submission.id,
                    'title': submission.title,
                    'author': str(submission.author) if submission.author else '[deleted]',
                    'subreddit': subreddit_name,
                    'url': f"https://reddit.com{submission.permalink}",
                    'created_time': datetime.fromtimestamp(submission.created_utc).strftime('%Y-%m-%d %H:%M:%S'),
                    'matched_keywords': ['flair:' + target_flair],
                    'match_type': 'flair_priority'
                }
                flair_posts.append(post_info)
                self.seen_posts.add(submission.id)
                logger.info(f"Found flair post: {submission.title[:50]}...")
                
        except Exception as e:
            logger.error(f"Error checking flair posts for r/{subreddit_name}: {e}")
            
        return flair_posts
    
    def send_test_notification(self, test_type: str = 'both'):
        """Send test notifications - 'email', 'telegram', or 'both'"""
        test_posts = [{
            'id': 'test_post_' + str(int(time.time())),
            'title': '🎫 TEST: Free Concert Tickets Available',
            'author': 'test_user',
            'subreddit': 'glasgow',
            'url': 'https://reddit.com/r/glasgow/test',
            'created_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'matched_keywords': ['free ticket', 'test'],
            'match_type': 'test'
        }]
        
        notifications_sent = []
        
        if test_type in ['email', 'both']:
            try:
                subject, body = self.format_notification_email(test_posts)
                subject = "[TEST] " + subject
                self.send_email(subject, body)
                notifications_sent.append("email")
                logger.info("Test email notification sent successfully")
            except Exception as e:
                logger.error(f"Failed to send test email: {e}")
        
        if test_type in ['telegram', 'both']:
            try:
                message = "[TEST NOTIFICATION]\n\n" + self.format_telegram_message(test_posts)
                self.send_telegram_message(message)
                notifications_sent.append("Telegram")
                logger.info("Test Telegram notification sent successfully")
            except Exception as e:
                logger.error(f"Failed to send test Telegram notification: {e}")
        
        return notifications_sent
    
    def send_email(self, subject: str, body: str, is_html: bool = True):
        """Send email notification"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_user
            msg['To'] = self.notification_email
            msg['Subject'] = subject
            
            # Send as HTML if is_html is True, otherwise plain text
            content_type = 'html' if is_html else 'plain'
            msg.attach(MIMEText(body, content_type))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise

    def send_telegram_message(self, message: str):
        """Send Telegram notification"""
        if not self.enable_telegram:
            logger.debug("Telegram not configured, skipping Telegram notification")
            return
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }
            
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            
            logger.info("Telegram notification sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

    def format_telegram_message(self, posts: List[Dict]) -> str:
        """Format Telegram message for multiple posts"""
        if len(posts) == 1:
            post = posts[0]
            header = f"🎫 <b>Reddit Alert</b>\n{post['title'][:100]}..."
        else:
            header = f"🎫 <b>Reddit Alert</b>\n{len(posts)} new posts found!"
        
        message_parts = [
            header,
            "",
            f"📍 <b>Monitoring:</b> r/{', r/'.join(self.subreddits)}",
            f"🔍 <b>Keywords:</b> {', '.join(self.keywords)}",
            ""
        ]
        
        for i, post in enumerate(posts, 1):
            # Telegram has a 4096 character limit, so we need to be concise
            message_parts.extend([
                f"<b>📋 Post #{i}</b>",
                f"<b>Title:</b> {post['title'][:120]}{'...' if len(post['title']) > 120 else ''}",
                f"<b>👤 Author:</b> u/{post['author']}",
                f"<b>📍 Subreddit:</b> r/{post['subreddit']}",
                f"<b>🔍 Match:</b> {post.get('match_type', 'keyword').replace('_', ' ').title()}",
                f"<b>🎯 Found:</b> {', '.join(post['matched_keywords'])}",
                f"<b>⏰ Posted:</b> {post['created_time']}",
                f"<a href=\"{post['url']}\">📖 View Post on Reddit</a>",
                ""
            ])
            
            # Check message length to avoid Telegram's 4096 char limit
            current_message = '\n'.join(message_parts)
            if len(current_message) > 3800:  # Leave some buffer
                message_parts.append("... (more posts found, check email for full details)")
                break
        
        message_parts.append(f"⏰ <i>Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>")
        
        return '\n'.join(message_parts)
            # Don't raise - we don't want Telegram failures to break email notifications
    
    def format_notification_email(self, posts: List[Dict]) -> tuple:
        """Format email subject and body for multiple posts"""
        if len(posts) == 1:
            post = posts[0]
            subject = f"🎫 Reddit Alert: {post['title'][:50]}..."
        else:
            subject = f"🎫 Reddit Alert: {len(posts)} new posts found"
        
        # Create HTML email body
        html_body = f"""
        <html>
        <head></head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c5530; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">
                    🎫 New Reddit Posts Found!
                </h2>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <p><strong>Monitoring:</strong> r/{', r/'.join(self.subreddits)}</p>
                    <p><strong>Keywords:</strong> {', '.join(self.keywords)}</p>
                    <p><strong>Found:</strong> {len(posts)} post{'s' if len(posts) != 1 else ''}</p>
                </div>
        """
        
        for i, post in enumerate(posts, 1):
            # Create a nice card for each post
            html_body += f"""
                <div style="border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 20px 0; background-color: #fff;">
                    <h3 style="color: #1a73e8; margin-top: 0;">
                        Post #{i}: {post['title']}
                    </h3>
                    
                    <div style="background-color: #f1f3f4; padding: 10px; border-radius: 4px; margin: 10px 0;">
                        <p style="margin: 5px 0;"><strong>👤 Author:</strong> u/{post['author']}</p>
                        <p style="margin: 5px 0;"><strong>📍 Subreddit:</strong> r/{post['subreddit']}</p>
                        <p style="margin: 5px 0;"><strong>🔍 Match type:</strong> {post.get('match_type', 'keyword').replace('_', ' ').title()}</p>
                        <p style="margin: 5px 0;"><strong>🎯 Matched on:</strong> {', '.join(post['matched_keywords'])}</p>
                        <p style="margin: 5px 0;"><strong>⏰ Posted:</strong> {post['created_time']}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 15px 0;">
                        <a href="{post['url']}" 
                           style="background-color: #4CAF50; color: white; padding: 12px 24px; 
                                  text-decoration: none; border-radius: 5px; display: inline-block;
                                  font-weight: bold;">
                            📖 View Post on Reddit
                        </a>
                    </div>
                </div>
            """
        
        # Add footer
        html_body += f"""
                <div style="border-top: 1px solid #ddd; padding-top: 15px; margin-top: 30px; 
                           text-align: center; color: #666; font-size: 12px;">
                    <p>Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>Glasgow Reddit Monitor - Keep an eye on the best deals! 🎫</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_body
    
    def check_subreddit(self, subreddit_name: str) -> List[Dict]:
        """Check a single subreddit for new posts"""
        matching_posts = []
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            logger.info(f"Checking r/{subreddit_name}...")
            
            # Check for flair-based posts first (priority)
            if subreddit_name in self.flair_priority:
                flair_posts = self._check_flair_posts(subreddit, subreddit_name)
                matching_posts.extend(flair_posts)
            
            posts_checked = 0
            # Adjust time filter based on subreddit activity (lenient mode)
            time_filter_hours = 48 if subreddit_name in self.lenient_subreddits else 24
            
            for submission in subreddit.new(limit=self.max_posts_per_run):
                posts_checked += 1
                
                if submission.id in self.seen_posts:
                    continue
                
                # Filter posts based on time
                post_age_hours = (datetime.now().timestamp() - submission.created_utc) / 3600
                if post_age_hours > time_filter_hours:
                    continue
                
                # Check title and selftext for keywords
                search_text = f"{submission.title} {submission.selftext}"
                matched_keywords = self.contains_keywords(search_text)
                
                if matched_keywords:
                    post_info = {
                        'id': submission.id,
                        'title': submission.title,
                        'author': str(submission.author) if submission.author else '[deleted]',
                        'subreddit': subreddit_name,
                        'url': f"https://reddit.com{submission.permalink}",
                        'created_time': datetime.fromtimestamp(submission.created_utc).strftime('%Y-%m-%d %H:%M:%S'),
                        'matched_keywords': matched_keywords,
                        'match_type': 'keyword'
                    }
                    matching_posts.append(post_info)
                    logger.info(f"Found matching post: {submission.title[:50]}...")
                
                self.seen_posts.add(submission.id)
            
            logger.info(f"Checked {posts_checked} posts in r/{subreddit_name}")
            
        except Exception as e:
            logger.error(f"Error checking r/{subreddit_name}: {e}")
            # Send error notification
            try:
                error_html = f"""
                <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2 style="color: #d32f2f;">🚨 Reddit Monitor Error</h2>
                    <p><strong>Subreddit:</strong> r/{subreddit_name}</p>
                    <p><strong>Error:</strong> {str(e)}</p>
                    <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </body>
                </html>
                """
                self.send_email(
                    "🚨 Reddit Monitor Error",
                    error_html
                )
            except:
                pass  # Don't fail if error notification fails
        
        return matching_posts
    
    def run_single_check(self):
        """Run a single check of all subreddits"""
        logger.info("Starting Reddit check...")
        all_matching_posts = []
        
        for subreddit_name in self.subreddits:
            matching_posts = self.check_subreddit(subreddit_name)
            all_matching_posts.extend(matching_posts)
        
        # Send notifications if any matches found
        if all_matching_posts:
            notification_count = len(all_matching_posts)
            notifications_sent = []
            
            # Send email notification
            try:
                subject, body = self.format_notification_email(all_matching_posts)
                self.send_email(subject, body)
                notifications_sent.append("email")
                logger.info(f"Email notification sent for {notification_count} posts")
            except Exception as e:
                logger.error(f"Failed to send email notification: {e}")
            
            # Send Telegram notification
            try:
                telegram_message = self.format_telegram_message(all_matching_posts)
                self.send_telegram_message(telegram_message)
                notifications_sent.append("Telegram")
                logger.info(f"Telegram notification sent for {notification_count} posts")
            except Exception as e:
                logger.error(f"Failed to send Telegram notification: {e}")
            
            if notifications_sent:
                logger.info(f"Notifications sent via: {', '.join(notifications_sent)}")
            else:
                logger.warning("Failed to send notifications via any method")
        else:
            logger.info("No new matching posts found")
        
        # Save seen posts
        self.save_seen_posts()
        logger.info(f"Check completed. Total seen posts: {len(self.seen_posts)}")
    
    def run_continuous(self):
        """Run continuous monitoring"""
        logger.info(f"Starting continuous monitoring every {self.check_interval // 60} minutes...")
        logger.info(f"Monitoring keywords: {', '.join(self.keywords)}")
        logger.info(f"Monitoring subreddits: r/{', r/'.join(self.subreddits)}")
        
        while True:
            try:
                self.run_single_check()
                logger.info(f"Sleeping for {self.check_interval // 60} minutes...")
                time.sleep(self.check_interval)
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying

def main():
    """Main entry point"""
    import sys
    
    try:
        monitor = RedditMonitor()
        
        # Check for command line arguments
        if len(sys.argv) > 1:
            if sys.argv[1] == 'test':
                test_type = sys.argv[2] if len(sys.argv) > 2 else 'both'
                if test_type not in ['email', 'telegram', 'both']:
                    print("Usage: python main.py test [email|telegram|both]")
                    sys.exit(1)
                
                print(f"Sending test notification via {test_type}...")
                sent = monitor.send_test_notification(test_type)
                if sent:
                    print(f"✅ Test notification sent via: {', '.join(sent)}")
                else:
                    print("❌ Failed to send test notifications")
                return
        
        # Check if running in CI (single run) or locally (continuous)
        if os.getenv('GITHUB_ACTIONS'):
            logger.info("Running in GitHub Actions mode (single check)")
            monitor.run_single_check()
        else:
            logger.info("Running in continuous mode")
            monitor.run_continuous()
            
    except Exception as e:
        logger.error(f"Failed to start Reddit monitor: {e}")
        raise

if __name__ == "__main__":
    main()