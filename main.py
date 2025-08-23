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
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Set
from dotenv import load_dotenv
import praw

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
    
    def send_email(self, subject: str, body: str):
        """Send email notification"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_user
            msg['To'] = self.notification_email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise
    
    def format_notification_email(self, posts: List[Dict]) -> tuple:
        """Format email subject and body for multiple posts"""
        if len(posts) == 1:
            post = posts[0]
            subject = f"🎫 Reddit Alert: {post['title'][:50]}..."
        else:
            subject = f"🎫 Reddit Alert: {len(posts)} new posts found"
        
        body_parts = [
            "New posts found matching your keywords!\\n",
            f"Monitoring: r/{', r/'.join(self.subreddits)}",
            f"Keywords: {', '.join(self.keywords)}\\n",
        ]
        
        for i, post in enumerate(posts, 1):
            body_parts.extend([
                f"--- POST {i} ---",
                f"Title: {post['title']}",
                f"Author: u/{post['author']}",
                f"Subreddit: r/{post['subreddit']}",
                f"Keywords found: {', '.join(post['matched_keywords'])}",
                f"Link: {post['url']}",
                f"Posted: {post['created_time']}\\n"
            ])
        
        body_parts.append(f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return subject, '\\n'.join(body_parts)
    
    def check_subreddit(self, subreddit_name: str) -> List[Dict]:
        """Check a single subreddit for new posts"""
        matching_posts = []
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            logger.info(f"Checking r/{subreddit_name}...")
            
            posts_checked = 0
            for submission in subreddit.new(limit=self.max_posts_per_run):
                posts_checked += 1
                
                if submission.id in self.seen_posts:
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
                        'matched_keywords': matched_keywords
                    }
                    matching_posts.append(post_info)
                    logger.info(f"Found matching post: {submission.title[:50]}...")
                
                self.seen_posts.add(submission.id)
            
            logger.info(f"Checked {posts_checked} posts in r/{subreddit_name}")
            
        except Exception as e:
            logger.error(f"Error checking r/{subreddit_name}: {e}")
            # Send error notification
            try:
                self.send_email(
                    "🚨 Reddit Monitor Error",
                    f"Error occurred while checking r/{subreddit_name}:\\n{str(e)}\\n\\nTime: {datetime.now()}"
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
        
        # Send notification if any matches found
        if all_matching_posts:
            try:
                subject, body = self.format_notification_email(all_matching_posts)
                self.send_email(subject, body)
                logger.info(f"Notification sent for {len(all_matching_posts)} posts")
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
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
    try:
        monitor = RedditMonitor()
        
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