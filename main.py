#!/usr/bin/env python3
"""
Glasgow Reddit Monitor
Monitors r/glasgow and r/glasgowmarket for ticket/giveaway posts and sends email notifications.
"""

import os
import json
import re
import time
import logging
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Set
from datetime import datetime, timedelta, timedelta
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
        self.analytics_file = 'analytics.json'
        self.seen_posts: Dict[str, str] = self.load_seen_posts()
        self.analytics: Dict = self.load_analytics()
        
        # Configuration from environment variables
        self.subreddits = ['glasgow', 'glasgowmarket']
        self.keywords = self._parse_keywords(os.getenv('KEYWORDS', 'free ticket,cheap ticket,giveaway,free entry,discount'))
        self.check_interval = int(os.getenv('CHECK_INTERVAL_MINUTES', '15') or '15') * 60
        self.max_posts_per_run = int(os.getenv('MAX_POSTS_PER_RUN', '50') or '50')
        self.days_to_check = int(os.getenv('DAYS_TO_CHECK', '7') or '7')
        
        # Advanced filtering configuration
        self.exclusion_keywords = self._parse_keywords(os.getenv('EXCLUSION_KEYWORDS', 'sold,taken,gone,closed,no longer available,found'))
        self.enable_regex_keywords = os.getenv('ENABLE_REGEX_KEYWORDS', 'false').lower() == 'true'
        self.min_user_karma = int(os.getenv('MIN_USER_KARMA', '10') or '10')
        self.min_account_age_days = int(os.getenv('MIN_ACCOUNT_AGE_DAYS', '7') or '7')
        self.min_post_score = int(os.getenv('MIN_POST_SCORE', '0') or '0')
        self.similarity_threshold = float(os.getenv('SIMILARITY_THRESHOLD', '0.8') or '0.8')
        self.enable_user_filtering = os.getenv('ENABLE_USER_FILTERING', 'true').lower() == 'true'
        self.enable_deduplication = os.getenv('ENABLE_DEDUPLICATION', 'true').lower() == 'true'
        
        # Flair configuration for priority monitoring
        self.flair_priority = {
            'glasgow': 'Ticket share. No adverts, free tickets only'
        }
        
        # Lenient mode for less active subreddits (uses 2x time window)
        self.lenient_subreddits = ['glasgowmarket']
        
        # Email configuration
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com') or 'smtp.gmail.com'
        self.smtp_port = int(os.getenv('SMTP_PORT', '587') or '587')
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
        
        # Multi-platform notifications (Phase 3)
        self.discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        self.enable_discord = bool(self.discord_webhook_url)
        
        self.slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        self.enable_slack = bool(self.slack_webhook_url)
        
        self.ifttt_webhook_key = os.getenv('IFTTT_WEBHOOK_KEY')
        self.ifttt_event_name = os.getenv('IFTTT_EVENT_NAME', 'reddit_match')
        self.enable_ifttt = bool(self.ifttt_webhook_key)
        
        # Pushover configuration
        self.pushover_user_key = os.getenv('PUSHOVER_USER_KEY')
        self.pushover_api_token = os.getenv('PUSHOVER_API_TOKEN')
        self.enable_pushover = bool(self.pushover_user_key and self.pushover_api_token)
        
        self._validate_config()
        self._init_reddit()
    
    def _parse_keywords(self, keywords_str: str) -> List[str]:
        """Parse comma-separated keywords and clean them"""
        if not keywords_str:
            return []
        keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
        
        # Validate regex patterns if regex mode is enabled
        if hasattr(self, 'enable_regex_keywords') and self.enable_regex_keywords:
            valid_keywords = []
            for keyword in keywords:
                try:
                    re.compile(keyword, re.IGNORECASE)
                    valid_keywords.append(keyword)
                except re.error as e:
                    logger.warning(f"Invalid regex pattern '{keyword}': {e}. Treating as literal string.")
                    valid_keywords.append(re.escape(keyword.lower()))
            return valid_keywords
        else:
            return [kw.lower() for kw in keywords]
    
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
    
    def cleanup_old_posts(self, days: int = 7):
        """Remove posts older than specified days to keep storage efficient"""
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff_time.isoformat()
            
            initial_count = len(self.seen_posts)
            
            # Filter out old posts
            self.seen_posts = {
                post_id: timestamp 
                for post_id, timestamp in self.seen_posts.items()
                if timestamp > cutoff_iso
            }
            
            removed_count = initial_count - len(self.seen_posts)
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} posts older than {days} days")
                self.save_seen_posts()
            
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
    
    def load_seen_posts(self) -> Dict[str, str]:
        """Load previously seen post IDs with timestamps from file"""
        try:
            if os.path.exists(self.seen_posts_file):
                with open(self.seen_posts_file, 'r') as f:
                    data = json.load(f)
                    
                    # Handle old format (list of post IDs)
                    if 'seen_posts' in data and isinstance(data['seen_posts'], list):
                        logger.info("Converting old format seen_posts.json to new timestamped format")
                        current_time = datetime.now().isoformat()
                        # Convert old format to new format with current timestamp
                        return {post_id: current_time for post_id in data['seen_posts']}
                    
                    # Handle new format (dict with timestamps)
                    elif 'seen_posts' in data and isinstance(data['seen_posts'], dict):
                        return data['seen_posts']
                    
                    # Fallback for unexpected format
                    else:
                        logger.warning("Unexpected seen_posts.json format, starting fresh")
                        return {}
                        
        except Exception as e:
            logger.warning(f"Could not load seen posts: {e}")
        return {}

    def load_analytics(self) -> Dict:
        """Load analytics data from JSON file"""
        try:
            if os.path.exists(self.analytics_file):
                with open(self.analytics_file, 'r') as f:
                    analytics = json.load(f)
                logger.info(f"Loaded analytics data: {len(analytics.get('matches', []))} matches recorded")
                return analytics
        except Exception as e:
            logger.error(f"Error loading analytics: {e}")
        
        # Return default analytics structure
        return {
            'matches': [],
            'keywords_stats': {},
            'subreddit_stats': {},
            'user_stats': {},
            'filter_stats': {
                'total_posts_checked': 0,
                'keyword_matches': 0,
                'excluded_by_keywords': 0,
                'excluded_by_user_quality': 0,
                'excluded_by_score': 0,
                'excluded_by_deduplication': 0
            },
            'last_updated': None
        }

    def save_analytics(self) -> None:
        """Save analytics data to JSON file"""
        try:
            self.analytics['last_updated'] = datetime.now().isoformat()
            with open(self.analytics_file, 'w') as f:
                json.dump(self.analytics, f, indent=2)
            logger.info("Analytics data saved successfully")
        except Exception as e:
            logger.error(f"Error saving analytics: {e}")
    
    def save_seen_posts(self):
        """Save seen post IDs with timestamps to file"""
        try:
            data = {
                'seen_posts': self.seen_posts,  # Now a dict with timestamps
                'last_updated': datetime.now().isoformat(),
                'total_posts': len(self.seen_posts)
            }
            with open(self.seen_posts_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save seen posts: {e}")
    
    def contains_keywords(self, text: str) -> List[str]:
        """Advanced keyword matching with regex support and exclusion filtering"""
        if not text:
            return []
            
        text_lower = text.lower()
        matches = []
        
        # Check for exclusion keywords first
        if self.should_exclude_by_keywords(text):
            self.analytics['filter_stats']['excluded_by_keywords'] += 1
            return []
        
        # Keyword matching
        for keyword in self.keywords:
            if self.enable_regex_keywords:
                try:
                    pattern = re.compile(keyword, re.IGNORECASE)
                    if pattern.search(text):
                        matches.append(keyword)
                        # Update keyword stats
                        if keyword not in self.analytics['keywords_stats']:
                            self.analytics['keywords_stats'][keyword] = {'count': 0, 'last_match': None}
                        self.analytics['keywords_stats'][keyword]['count'] += 1
                        self.analytics['keywords_stats'][keyword]['last_match'] = datetime.now().isoformat()
                except re.error:
                    # Fallback to literal matching
                    if keyword.lower() in text_lower:
                        matches.append(keyword)
            else:
                # Enhanced word boundary matching for literal keywords
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, text_lower, re.IGNORECASE):
                    matches.append(keyword)
                    # Update keyword stats
                    if keyword not in self.analytics['keywords_stats']:
                        self.analytics['keywords_stats'][keyword] = {'count': 0, 'last_match': None}
                    self.analytics['keywords_stats'][keyword]['count'] += 1
                    self.analytics['keywords_stats'][keyword]['last_match'] = datetime.now().isoformat()
        
        if matches:
            self.analytics['filter_stats']['keyword_matches'] += 1
            
        return matches

    def should_exclude_by_keywords(self, text: str) -> bool:
        """Check if post should be excluded based on exclusion keywords"""
        if not self.exclusion_keywords or not text:
            return False
            
        text_lower = text.lower()
        for exclusion_keyword in self.exclusion_keywords:
            if exclusion_keyword in text_lower:
                logger.debug(f"Post excluded due to keyword: {exclusion_keyword}")
                return True
        return False

    def should_exclude_by_user_quality(self, post) -> bool:
        """Check if post should be excluded based on user quality metrics"""
        if not self.enable_user_filtering:
            return False
            
        try:
            author = post.author
            if author is None:
                # Deleted or suspended user
                logger.debug("Post excluded: author is None (deleted/suspended)")
                self.analytics['filter_stats']['excluded_by_user_quality'] += 1
                return True
                
            # Check account age
            account_age_days = (datetime.now() - datetime.fromtimestamp(author.created_utc)).days
            if account_age_days < self.min_account_age_days:
                logger.debug(f"Post excluded: account age {account_age_days} days < {self.min_account_age_days}")
                self.analytics['filter_stats']['excluded_by_user_quality'] += 1
                return True
                
            # Check karma (comment + link karma)
            total_karma = (author.comment_karma or 0) + (author.link_karma or 0)
            if total_karma < self.min_user_karma:
                logger.debug(f"Post excluded: user karma {total_karma} < {self.min_user_karma}")
                self.analytics['filter_stats']['excluded_by_user_quality'] += 1
                return True
                
        except Exception as e:
            logger.warning(f"Error checking user quality: {e}")
            # Don't exclude on error, err on side of caution
            return False
            
        return False

    def should_exclude_by_score(self, post) -> bool:
        """Check if post should be excluded based on score"""
        if post.score < self.min_post_score:
            logger.debug(f"Post excluded: score {post.score} < {self.min_post_score}")
            self.analytics['filter_stats']['excluded_by_score'] += 1
            return True
        return False

    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using simple word overlap"""
        if not text1 or not text2:
            return 0.0
            
        # Simple word-based similarity
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
            
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def should_exclude_by_deduplication(self, post) -> bool:
        """Check if post is too similar to recently seen posts"""
        if not self.enable_deduplication:
            return False
            
        current_text = f"{post.title} {post.selftext}"
        current_author = str(post.author) if post.author else "unknown"
        
        # Check against recent posts
        for post_id, post_data in self.seen_posts.items():
            try:
                stored_data = json.loads(post_data) if isinstance(post_data, str) else post_data
                stored_text = stored_data.get('text', '')
                stored_author = stored_data.get('author', 'unknown')
                
                # Higher threshold for same author (likely repost)
                threshold = 0.6 if current_author == stored_author else self.similarity_threshold
                
                similarity = self.calculate_text_similarity(current_text, stored_text)
                if similarity > threshold:
                    logger.debug(f"Post excluded: similarity {similarity:.2f} > {threshold} with post {post_id}")
                    self.analytics['filter_stats']['excluded_by_deduplication'] += 1
                    return True
                    
            except Exception as e:
                logger.debug(f"Error comparing with stored post {post_id}: {e}")
                continue
                
        return False

    def update_analytics_for_match(self, post, subreddit_name: str, matched_keywords: List[str]):
        """Update analytics when a post matches"""
        match_data = {
            'timestamp': datetime.now().isoformat(),
            'post_id': post.id,
            'subreddit': subreddit_name,
            'title': post.title,
            'author': str(post.author) if post.author else 'unknown',
            'score': post.score,
            'created_utc': post.created_utc,
            'matched_keywords': matched_keywords,
            'url': f"https://reddit.com{post.permalink}"
        }
        
        self.analytics['matches'].append(match_data)
        
        # Update subreddit stats
        if subreddit_name not in self.analytics['subreddit_stats']:
            self.analytics['subreddit_stats'][subreddit_name] = {'count': 0, 'last_match': None}
        self.analytics['subreddit_stats'][subreddit_name]['count'] += 1
        self.analytics['subreddit_stats'][subreddit_name]['last_match'] = datetime.now().isoformat()
        
        # Update user stats (if we want to track prolific posters)
        author_name = str(post.author) if post.author else 'unknown'
        if author_name not in self.analytics['user_stats']:
            self.analytics['user_stats'][author_name] = {'count': 0, 'last_post': None}
        self.analytics['user_stats'][author_name]['count'] += 1
        self.analytics['user_stats'][author_name]['last_post'] = datetime.now().isoformat()
        
        # Keep only recent matches (last 30 days)
        cutoff_date = datetime.now() - timedelta(days=30)
        self.analytics['matches'] = [
            match for match in self.analytics['matches']
            if datetime.fromisoformat(match['timestamp']) > cutoff_date
        ]

    def generate_analytics_dashboard(self) -> str:
        """Generate static HTML analytics dashboard"""
        if not self.analytics['matches']:
            return self._generate_empty_dashboard()
        
        # Calculate statistics
        stats = self._calculate_dashboard_stats()
        
        # Generate HTML
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor Analytics Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            text-align: center;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-label {{
            color: #666;
            margin-top: 5px;
        }}
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
            margin-bottom: 30px;
        }}
        .chart-container {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .chart-title {{
            font-size: 1.2em;
            font-weight: bold;
            margin-bottom: 15px;
            text-align: center;
            color: #333;
        }}
        .recent-matches {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .recent-matches h3 {{
            background: #667eea;
            color: white;
            margin: 0;
            padding: 20px;
            font-size: 1.1em;
        }}
        .match-item {{
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
        }}
        .match-item:last-child {{
            border-bottom: none;
        }}
        .match-title {{
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }}
        .match-meta {{
            color: #666;
            font-size: 0.9em;
        }}
        .match-keywords {{
            background: #e3f2fd;
            color: #1565c0;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            margin: 5px 5px 0 0;
            display: inline-block;
        }}
        .footer {{
            text-align: center;
            color: #666;
            margin-top: 30px;
            padding: 20px;
        }}
        @media (max-width: 768px) {{
            .charts-grid {{
                grid-template-columns: 1fr;
            }}
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎫 Reddit Monitor Analytics</h1>
            <p>Monitoring r/glasgow & r/glasgowmarket for tickets and giveaways</p>
            <p><small>Last updated: {stats['last_updated']}</small></p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{stats['total_matches']}</div>
                <div class="stat-label">Total Matches</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['matches_last_7_days']}</div>
                <div class="stat-label">Last 7 Days</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['filter_efficiency']:.1f}%</div>
                <div class="stat-label">Filter Efficiency</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['avg_daily_matches']:.1f}</div>
                <div class="stat-label">Daily Average</div>
            </div>
        </div>

        <div class="charts-grid">
            <div class="chart-container">
                <div class="chart-title">Matches Over Time</div>
                <canvas id="timeChart" width="400" height="200"></canvas>
            </div>
            
            <div class="chart-container">
                <div class="chart-title">Top Keywords</div>
                <canvas id="keywordsChart" width="400" height="200"></canvas>
            </div>
            
            <div class="chart-container">
                <div class="chart-title">Subreddit Distribution</div>
                <canvas id="subredditChart" width="400" height="200"></canvas>
            </div>
            
            <div class="chart-container">
                <div class="chart-title">Filtering Statistics</div>
                <canvas id="filterChart" width="400" height="200"></canvas>
            </div>
        </div>

        <div class="recent-matches">
            <h3>Recent Matches (Last 10)</h3>
            {self._generate_recent_matches_html(stats['recent_matches'])}
        </div>

        <div class="footer">
            <p>Generated by Reddit Monitor v2.0 | Zero-cost analytics on GitHub Pages</p>
        </div>
    </div>

    <script>
        // Chart.js configuration
        Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        Chart.defaults.color = '#666';

        // Time chart
        {self._generate_time_chart_js(stats['time_data'])}

        // Keywords chart  
        {self._generate_keywords_chart_js(stats['keywords_data'])}

        // Subreddit chart
        {self._generate_subreddit_chart_js(stats['subreddit_data'])}

        // Filter chart
        {self._generate_filter_chart_js(stats['filter_data'])}
    </script>
</body>
</html>"""
        
        return html_content

    def _generate_empty_dashboard(self) -> str:
        """Generate dashboard for when no data is available"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor Analytics Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }}
        .empty-state {{
            text-align: center;
            background: white;
            padding: 60px 40px;
            border-radius: 12px;
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
            max-width: 500px;
        }}
        .empty-icon {{
            font-size: 4em;
            margin-bottom: 20px;
        }}
        .empty-title {{
            font-size: 1.5em;
            color: #333;
            margin-bottom: 10px;
        }}
        .empty-description {{
            color: #666;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div class="empty-state">
        <div class="empty-icon">📊</div>
        <div class="empty-title">No Data Available</div>
        <div class="empty-description">
            The Reddit Monitor is running but hasn't found any matches yet.<br>
            Check back after the system has been monitoring for a while.
        </div>
        <p><small>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
    </div>
</body>
</html>"""

    def _calculate_dashboard_stats(self) -> dict:
        """Calculate statistics for the dashboard"""
        now = datetime.now()
        seven_days_ago = now - timedelta(days=7)
        
        # Time-based filtering
        recent_matches = [
            match for match in self.analytics['matches']
            if datetime.fromisoformat(match['timestamp']) > seven_days_ago
        ]
        
        # Calculate efficiency (matches found vs posts checked)
        total_checked = self.analytics['filter_stats']['total_posts_checked']
        total_matches = len(self.analytics['matches'])
        filter_efficiency = (total_matches / total_checked * 100) if total_checked > 0 else 0
        
        # Daily average (over last 7 days)
        avg_daily = len(recent_matches) / 7 if recent_matches else 0
        
        # Time series data for chart
        time_data = self._prepare_time_series_data()
        
        # Keywords data
        keywords_data = sorted(
            [(k, v['count']) for k, v in self.analytics['keywords_stats'].items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]  # Top 10
        
        # Subreddit data
        subreddit_data = [
            (k, v['count']) for k, v in self.analytics['subreddit_stats'].items()
        ]
        
        # Filter data
        filter_stats = self.analytics['filter_stats']
        filter_data = {
            'Keywords Matched': filter_stats.get('keyword_matches', 0),
            'Excluded by Keywords': filter_stats.get('excluded_by_keywords', 0),
            'Excluded by User Quality': filter_stats.get('excluded_by_user_quality', 0),
            'Excluded by Score': filter_stats.get('excluded_by_score', 0),
            'Excluded by Deduplication': filter_stats.get('excluded_by_deduplication', 0)
        }
        
        return {
            'last_updated': now.strftime('%Y-%m-%d %H:%M:%S'),
            'total_matches': total_matches,
            'matches_last_7_days': len(recent_matches),
            'filter_efficiency': filter_efficiency,
            'avg_daily_matches': avg_daily,
            'recent_matches': sorted(self.analytics['matches'], 
                                   key=lambda x: x['timestamp'], reverse=True)[:10],
            'time_data': time_data,
            'keywords_data': keywords_data,
            'subreddit_data': subreddit_data,
            'filter_data': filter_data
        }

    def _prepare_time_series_data(self) -> dict:
        """Prepare time series data for the chart"""
        # Group matches by date
        date_counts = {}
        for match in self.analytics['matches']:
            date_str = match['timestamp'][:10]  # YYYY-MM-DD
            date_counts[date_str] = date_counts.get(date_str, 0) + 1
        
        # Fill in missing dates for last 30 days
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=29)
        
        dates = []
        counts = []
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            dates.append(current_date.strftime('%m/%d'))
            counts.append(date_counts.get(date_str, 0))
            current_date += timedelta(days=1)
            
        return {'dates': dates, 'counts': counts}

    def _generate_recent_matches_html(self, matches: list) -> str:
        """Generate HTML for recent matches"""
        if not matches:
            return '<div class="match-item">No recent matches</div>'
        
        html_parts = []
        for match in matches:
            keywords_html = ''.join([
                f'<span class="match-keywords">{keyword}</span>'
                for keyword in match.get('matched_keywords', [])
            ])
            
            html_parts.append(f'''
            <div class="match-item">
                <div class="match-title">
                    <a href="{match['url']}" target="_blank" style="text-decoration: none; color: inherit;">
                        {match['title'][:80]}{'...' if len(match['title']) > 80 else ''}
                    </a>
                </div>
                <div class="match-meta">
                    r/{match['subreddit']} • {match['author']} • Score: {match['score']} • 
                    {datetime.fromisoformat(match['timestamp']).strftime('%Y-%m-%d %H:%M')}
                </div>
                <div>{keywords_html}</div>
            </div>
            ''')
        
        return ''.join(html_parts)

    def _generate_time_chart_js(self, time_data: dict) -> str:
        """Generate JavaScript for time series chart"""
        return f"""
        const timeCtx = document.getElementById('timeChart').getContext('2d');
        new Chart(timeCtx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(time_data['dates'])},
                datasets: [{{
                    label: 'Matches',
                    data: {json.dumps(time_data['counts'])},
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4,
                    fill: true
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});"""

    def _generate_keywords_chart_js(self, keywords_data: list) -> str:
        """Generate JavaScript for keywords chart"""
        if not keywords_data:
            return "// No keywords data"
        
        labels = [item[0] for item in keywords_data]
        data = [item[1] for item in keywords_data]
        
        return f"""
        const keywordsCtx = document.getElementById('keywordsChart').getContext('2d');
        new Chart(keywordsCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{
                    label: 'Matches',
                    data: {json.dumps(data)},
                    backgroundColor: 'rgba(102, 126, 234, 0.6)',
                    borderColor: '#667eea',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});"""

    def _generate_subreddit_chart_js(self, subreddit_data: list) -> str:
        """Generate JavaScript for subreddit chart"""
        if not subreddit_data:
            return "// No subreddit data"
        
        labels = [f"r/{item[0]}" for item in subreddit_data]
        data = [item[1] for item in subreddit_data]
        colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe']
        
        return f"""
        const subredditCtx = document.getElementById('subredditChart').getContext('2d');
        new Chart(subredditCtx, {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{
                    data: {json.dumps(data)},
                    backgroundColor: {json.dumps(colors[:len(data)])},
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }}
            }}
        }});"""

    def _generate_filter_chart_js(self, filter_data: dict) -> str:
        """Generate JavaScript for filter statistics chart"""
        labels = list(filter_data.keys())
        data = list(filter_data.values())
        
        return f"""
        const filterCtx = document.getElementById('filterChart').getContext('2d');
        new Chart(filterCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{
                    label: 'Count',
                    data: {json.dumps(data)},
                    backgroundColor: [
                        'rgba(76, 175, 80, 0.6)',   // Keywords Matched - green
                        'rgba(255, 152, 0, 0.6)',   // Excluded by Keywords - orange  
                        'rgba(244, 67, 54, 0.6)',   // Excluded by User Quality - red
                        'rgba(156, 39, 176, 0.6)',  // Excluded by Score - purple
                        'rgba(33, 150, 243, 0.6)'   // Excluded by Deduplication - blue
                    ],
                    borderColor: [
                        '#4caf50', '#ff9800', '#f44336', '#9c27b0', '#2196f3'
                    ],
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});"""

    def save_dashboard_html(self, output_path: str = 'dashboard.html') -> bool:
        """Save dashboard HTML to file"""
        try:
            html_content = self.generate_analytics_dashboard()
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"Analytics dashboard saved to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving dashboard: {e}")
            return False

    
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
                    
                # Check if post is within configured time window
                post_age_hours = (datetime.now().timestamp() - submission.created_utc) / 3600
                max_hours = self.days_to_check * 24
                if post_age_hours > max_hours:
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
                self.seen_posts[submission.id] = datetime.now().isoformat()
                logger.info(f"Found flair post: {submission.title[:50]}...")
                
        except Exception as e:
            logger.error(f"Error checking flair posts for r/{subreddit_name}: {e}")
            
        return flair_posts
    
    def send_test_notification(self, test_type: str = 'all'):
        """Send test notifications - 'email', 'telegram', 'discord', 'slack', 'pushover', 'ifttt', 'all'"""
        test_posts = [{
            'id': 'test_post_' + str(int(time.time())),
            'title': '🎫 TEST: Free Concert Tickets Available',
            'author': 'test_user',
            'subreddit': 'glasgow',
            'url': 'https://reddit.com/r/glasgow/test',
            'created_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'matched_keywords': ['free ticket', 'test'],
            'match_type': 'test',
            'score': 10
        }]
        
        notifications_sent = []
        
        # Determine which notifications to send
        send_email = test_type in ['email', 'all']
        send_telegram = test_type in ['telegram', 'all'] and self.enable_telegram
        send_discord = test_type in ['discord', 'all'] and self.enable_discord
        send_slack = test_type in ['slack', 'all'] and self.enable_slack
        send_pushover = test_type in ['pushover', 'all'] and self.enable_pushover
        send_ifttt = test_type in ['ifttt', 'all'] and self.enable_ifttt
        
        # Email notification
        if send_email:
            try:
                subject, body = self.format_notification_email(test_posts)
                subject = "[TEST] " + subject
                if self.send_email(subject, body):
                    notifications_sent.append("email")
                    logger.info("Test email notification sent successfully")
            except Exception as e:
                logger.error(f"Failed to send test email: {e}")
        
        # Telegram notification
        if send_telegram:
            try:
                message = "[TEST NOTIFICATION]\n\n" + self.format_telegram_message(test_posts)
                if self.send_telegram_message(message):
                    notifications_sent.append("Telegram")
                    logger.info("Test Telegram notification sent successfully")
            except Exception as e:
                logger.error(f"Failed to send test Telegram notification: {e}")
        
        # Discord notification
        if send_discord:
            try:
                message = "**[TEST NOTIFICATION]**\n\n" + self.format_discord_message(test_posts)
                if self.send_discord_message(message):
                    notifications_sent.append("Discord")
                    logger.info("Test Discord notification sent successfully")
            except Exception as e:
                logger.error(f"Failed to send test Discord notification: {e}")
        
        # Slack notification
        if send_slack:
            try:
                message = "*[TEST NOTIFICATION]*\n\n" + self.format_slack_message(test_posts)
                if self.send_slack_message(message):
                    notifications_sent.append("Slack")
                    logger.info("Test Slack notification sent successfully")
            except Exception as e:
                logger.error(f"Failed to send test Slack notification: {e}")
        
        # Pushover notification
        if send_pushover:
            try:
                title, message, url = self.format_pushover_message(test_posts)
                title = "[TEST] " + title
                if self.send_pushover_notification(title, message, url):
                    notifications_sent.append("Pushover")
                    logger.info("Test Pushover notification sent successfully")
            except Exception as e:
                logger.error(f"Failed to send test Pushover notification: {e}")
        
        # IFTTT webhook
        if send_ifttt:
            try:
                if self.send_ifttt_webhook("Test Reddit Match", "This is a test notification from Reddit Monitor", "https://reddit.com/test"):
                    notifications_sent.append("IFTTT")
                    logger.info("Test IFTTT webhook sent successfully")
            except Exception as e:
                logger.error(f"Failed to send test IFTTT webhook: {e}")
        
        return notifications_sent
    
    def send_email(self, subject: str, body: str, is_html: bool = True) -> bool:
        """Send email notification"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_user
            msg['To'] = self.notification_email
            msg['Subject'] = subject
            
            # Send as HTML if is_html is True, otherwise plain text
            content_type = 'html' if is_html else 'plain'
            msg.attach(MIMEText(body, content_type))
            
            try:
                logger.debug(f"Connecting to SMTP server {self.smtp_server}:{self.smtp_port}")
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            finally:
                try:
                    server.quit()
                except:
                    pass  # Ignore quit errors
            
            logger.info(f"Email sent successfully: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            logger.error(f"SMTP Config: server={self.smtp_server}, port={self.smtp_port}, user={self.email_user}")
            return False

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
            
            # Validate message length and HTML tags
            if len(message) > 4096:
                message = message[:4090] + "..."
                data['text'] = message
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Telegram API error {response.status_code}: {response.text}")
                # Try with plain text if HTML fails
                if response.status_code == 400 and 'parse_mode' in data:
                    data['parse_mode'] = 'Markdown'  # Fallback to Markdown
                    response = requests.post(url, data=data, timeout=10)
                    if response.status_code != 200:
                        data.pop('parse_mode', None)  # Try plain text
                        response = requests.post(url, data=data, timeout=10)
                        
            response.raise_for_status()
            logger.info("Telegram notification sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

    def send_discord_message(self, content: str) -> bool:
        """Send message to Discord via webhook"""
        if not self.enable_discord:
            return False
            
        try:
            import requests
            
            # Discord allows up to 2000 characters
            if len(content) > 2000:
                content = content[:1997] + "..."
                
            payload = {
                "content": content,
                "username": "Reddit Monitor",
                "avatar_url": "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png"
            }
            
            response = requests.post(
                self.discord_webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 204:  # Discord returns 204 for successful webhooks
                logger.info("Discord notification sent successfully")
                return True
            else:
                logger.error(f"Discord webhook failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Discord message: {e}")
            return False

    def send_slack_message(self, text: str) -> bool:
        """Send message to Slack via webhook"""
        if not self.enable_slack:
            return False
            
        try:
            import requests
            
            payload = {
                "text": text,
                "username": "Reddit Monitor",
                "icon_emoji": ":ticket:",
                "channel": "#general"  # Can be overridden by webhook configuration
            }
            
            response = requests.post(
                self.slack_webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Slack notification sent successfully")
                return True
            else:
                logger.error(f"Slack webhook failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack message: {e}")
            return False

    def send_ifttt_webhook(self, title: str, message: str, url: str = "") -> bool:
        """Send webhook to IFTTT to trigger other services"""
        if not self.enable_ifttt:
            return False
            
        try:
            import requests
            
            webhook_url = f"https://maker.ifttt.com/trigger/{self.ifttt_event_name}/with/key/{self.ifttt_webhook_key}"
            
            payload = {
                "value1": title,    # Event title
                "value2": message,  # Event description
                "value3": url       # Optional URL
            }
            
            response = requests.post(
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("IFTTT webhook sent successfully")
                return True
            else:
                logger.error(f"IFTTT webhook failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending IFTTT webhook: {e}")
            return False

    def send_pushover_notification(self, title: str, message: str, url: str = "") -> bool:
        """Send push notification via Pushover"""
        if not self.enable_pushover:
            return False
            
        try:
            import requests
            
            payload = {
                "token": self.pushover_api_token,
                "user": self.pushover_user_key,
                "title": title,
                "message": message,
                "priority": 1,  # High priority
                "sound": "tugboat"
            }
            
            if url:
                payload["url"] = url
                payload["url_title"] = "View on Reddit"
            
            response = requests.post(
                "https://api.pushover.net/1/messages.json",
                data=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 1:
                    logger.info("Pushover notification sent successfully")
                    return True
                else:
                    logger.error(f"Pushover API error: {result}")
                    return False
            else:
                logger.error(f"Pushover request failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Pushover notification: {e}")
            return False

    def format_discord_message(self, matching_posts: List[Dict]) -> str:
        """Format notification message for Discord"""
        count = len(matching_posts)
        
        if count == 1:
            post = matching_posts[0]
            message = f"🎫 **New Reddit Match Found!**\n\n"
            message += f"**{post['title']}**\n"
            message += f"👤 Posted by: u/{post['author']}\n"
            message += f"📍 Subreddit: r/{post['subreddit']}\n"
            message += f"🏷️ Keywords: {', '.join(post['matched_keywords'])}\n"
            message += f"🔗 {post['url']}\n"
            message += f"⏰ {post['created_time']}"
        else:
            message = f"🎫 **{count} New Reddit Matches Found!**\n\n"
            
            for i, post in enumerate(matching_posts[:5], 1):  # Limit to 5 for Discord
                message += f"**{i}. {post['title'][:60]}{'...' if len(post['title']) > 60 else ''}**\n"
                message += f"r/{post['subreddit']} • u/{post['author']} • {', '.join(post['matched_keywords'])}\n"
                message += f"{post['url']}\n\n"
            
            if count > 5:
                message += f"... and {count - 5} more matches"
        
        return message

    def format_slack_message(self, matching_posts: List[Dict]) -> str:
        """Format notification message for Slack"""
        count = len(matching_posts)
        
        if count == 1:
            post = matching_posts[0]
            message = f":ticket: *New Reddit Match Found!*\n\n"
            message += f"*{post['title']}*\n"
            message += f"Posted by: u/{post['author']} in r/{post['subreddit']}\n"
            message += f"Keywords: {', '.join(post['matched_keywords'])}\n"
            message += f"<{post['url']}|View on Reddit>\n"
            message += f"Time: {post['created_time']}"
        else:
            message = f":ticket: *{count} New Reddit Matches Found!*\n\n"
            
            for i, post in enumerate(matching_posts[:5], 1):
                message += f"*{i}. {post['title'][:60]}{'...' if len(post['title']) > 60 else ''}*\n"
                message += f"r/{post['subreddit']} • u/{post['author']} • {', '.join(post['matched_keywords'])}\n"
                message += f"<{post['url']}|View>\n\n"
            
            if count > 5:
                message += f"... and {count - 5} more matches"
        
        return message

    def format_pushover_message(self, matching_posts: List[Dict]) -> tuple:
        """Format notification for Pushover (returns title, message, url)"""
        count = len(matching_posts)
        
        if count == 1:
            post = matching_posts[0]
            title = "🎫 Reddit Match Found"
            message = f"{post['title']}\n\n"
            message += f"r/{post['subreddit']} • u/{post['author']}\n"
            message += f"Keywords: {', '.join(post['matched_keywords'])}\n"
            message += f"Posted: {post['created_time']}"
            url = post['url']
        else:
            title = f"🎫 {count} Reddit Matches Found"
            message = ""
            
            for i, post in enumerate(matching_posts[:3], 1):  # Limit to 3 for Pushover
                message += f"{i}. {post['title'][:50]}{'...' if len(post['title']) > 50 else ''}\n"
                message += f"   r/{post['subreddit']} • {', '.join(post['matched_keywords'])}\n\n"
            
            if count > 3:
                message += f"... and {count - 3} more matches"
            
            url = ""  # Multiple posts, no single URL
        
        return title, message, url

    def send_all_notifications(self, matching_posts: List[Dict]) -> List[str]:
        """Send notifications via all enabled platforms"""
        sent_notifications = []
        
        # Email notification
        try:
            subject, body = self.format_notification_email(matching_posts)
            if self.send_email(subject, body):
                sent_notifications.append("email")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
        
        # Telegram notification
        try:
            if self.enable_telegram:
                telegram_message = self.format_telegram_message(matching_posts)
                if self.send_telegram_message(telegram_message):
                    sent_notifications.append("Telegram")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
        
        # Discord notification
        try:
            if self.enable_discord:
                discord_message = self.format_discord_message(matching_posts)
                if self.send_discord_message(discord_message):
                    sent_notifications.append("Discord")
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
        
        # Slack notification
        try:
            if self.enable_slack:
                slack_message = self.format_slack_message(matching_posts)
                if self.send_slack_message(slack_message):
                    sent_notifications.append("Slack")
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
        
        # Pushover notification
        try:
            if self.enable_pushover:
                title, message, url = self.format_pushover_message(matching_posts)
                if self.send_pushover_notification(title, message, url):
                    sent_notifications.append("Pushover")
        except Exception as e:
            logger.error(f"Failed to send Pushover notification: {e}")
        
        # IFTTT webhook (triggers other services)
        try:
            if self.enable_ifttt:
                count = len(matching_posts)
                title = f"Reddit Match{'es' if count > 1 else ''} Found"
                if count == 1:
                    post = matching_posts[0]
                    message = f"{post['title']} - r/{post['subreddit']}"
                    url = post['url']
                else:
                    message = f"{count} new matches found"
                    url = ""
                
                if self.send_ifttt_webhook(title, message, url):
                    sent_notifications.append("IFTTT")
        except Exception as e:
            logger.error(f"Failed to send IFTTT webhook: {e}")
        
        return sent_notifications

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
        """Check a single subreddit for new posts with advanced filtering"""
        matching_posts = []
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            logger.info(f"Checking r/{subreddit_name}...")
            
            # Check for flair-based posts first (priority)
            if subreddit_name in self.flair_priority:
                flair_posts = self._check_flair_posts(subreddit, subreddit_name)
                matching_posts.extend(flair_posts)
            
            posts_checked = 0
            posts_filtered = 0
            
            # Adjust time filter based on subreddit activity (lenient mode)
            base_hours = self.days_to_check * 24
            time_filter_hours = base_hours * 2 if subreddit_name in self.lenient_subreddits else base_hours
            
            for submission in subreddit.new(limit=self.max_posts_per_run):
                posts_checked += 1
                self.analytics['filter_stats']['total_posts_checked'] += 1
                
                if submission.id in self.seen_posts:
                    continue
                
                # Filter posts based on time
                post_age_hours = (datetime.now().timestamp() - submission.created_utc) / 3600
                if post_age_hours > time_filter_hours:
                    continue
                
                # Apply advanced filtering
                if self.should_exclude_by_user_quality(submission):
                    posts_filtered += 1
                    continue
                    
                if self.should_exclude_by_score(submission):
                    posts_filtered += 1
                    continue
                    
                if self.should_exclude_by_deduplication(submission):
                    posts_filtered += 1
                    continue
                
                # Check title and selftext for keywords (includes exclusion filtering)
                search_text = f"{submission.title} {submission.selftext}"
                matched_keywords = self.contains_keywords(search_text)
                
                # Debug logging for troubleshooting
                if any(keyword.lower() in search_text.lower() for keyword in ['glasgow', 'love']):
                    logger.info(f"DEBUG: Post with glasgow/love found: '{submission.title[:50]}...' Age: {post_age_hours:.1f}h Matches: {matched_keywords}")
                
                if matched_keywords:
                    post_info = {
                        'id': submission.id,
                        'title': submission.title,
                        'author': str(submission.author) if submission.author else '[deleted]',
                        'subreddit': subreddit_name,
                        'url': f"https://reddit.com{submission.permalink}",
                        'created_time': datetime.fromtimestamp(submission.created_utc).strftime('%Y-%m-%d %H:%M:%S'),
                        'matched_keywords': matched_keywords,
                        'match_type': 'keyword',
                        'score': submission.score,
                        'post_age_hours': round(post_age_hours, 1)
                    }
                    matching_posts.append(post_info)
                    
                    # Update analytics
                    self.update_analytics_for_match(submission, subreddit_name, matched_keywords)
                    
                    logger.info(f"Found matching post: {submission.title[:50]}...")
                
                # Store post data for deduplication (even if not matching)
                post_data = {
                    'text': search_text,
                    'author': str(submission.author) if submission.author else 'unknown',
                    'timestamp': datetime.now().isoformat()
                }
                self.seen_posts[submission.id] = json.dumps(post_data)
            
            logger.info(f"Checked {posts_checked} posts in r/{subreddit_name}, filtered {posts_filtered}")
            
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
        
        # Cleanup old posts to keep storage efficient
        self.cleanup_old_posts()
        all_matching_posts = []
        
        for subreddit_name in self.subreddits:
            matching_posts = self.check_subreddit(subreddit_name)
            all_matching_posts.extend(matching_posts)
        
        # Send notifications if any matches found
        if all_matching_posts:
            notification_count = len(all_matching_posts)
            logger.info(f"Found {notification_count} matching posts, sending notifications...")
            
            # Use new multi-platform notification system
            sent_notifications = self.send_all_notifications(all_matching_posts)
            
            if sent_notifications:
                logger.info(f"Notifications sent via: {', '.join(sent_notifications)}")
            else:
                logger.warning("Failed to send notifications via any platform")
        else:
            logger.info("No new matching posts found")
        
        # Save analytics and seen posts
        self.save_analytics()
        self.save_seen_posts()
        
        # Log analytics summary
        filter_stats = self.analytics['filter_stats']
        logger.info(f"Check completed. Posts checked: {filter_stats['total_posts_checked']}, "
                   f"Keyword matches: {filter_stats['keyword_matches']}, "
                   f"Filtered: {filter_stats['excluded_by_keywords'] + filter_stats['excluded_by_user_quality'] + filter_stats['excluded_by_score'] + filter_stats['excluded_by_deduplication']}")
        logger.info(f"Total seen posts: {len(self.seen_posts)}, Total matches recorded: {len(self.analytics['matches'])}")
    
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
                test_type = sys.argv[2] if len(sys.argv) > 2 else 'all'
                valid_types = ['email', 'telegram', 'discord', 'slack', 'pushover', 'ifttt', 'all']
                if test_type not in valid_types:
                    print(f"Usage: python main.py test [{' | '.join(valid_types)}]")
                    sys.exit(1)
                
                print(f"Sending test notification via {test_type}...")
                sent = monitor.send_test_notification(test_type)
                if sent:
                    print(f"✅ Test notification sent via: {', '.join(sent)}")
                else:
                    print("❌ Failed to send test notifications")
                return
            elif sys.argv[1] == 'dashboard':
                print("Generating analytics dashboard...")
                success = monitor.save_dashboard_html('dashboard.html')
                if success:
                    print("✅ Dashboard generated successfully: dashboard.html")
                    print("📊 Open dashboard.html in your browser to view analytics")
                else:
                    print("❌ Failed to generate dashboard")
                return
        
        # Check if running in CI (single run) or locally (continuous)
        if os.getenv('GITHUB_ACTIONS'):
            logger.info("Running in GitHub Actions mode (single check)")
            monitor.run_single_check()
            # Generate dashboard for GitHub Pages in CI
            monitor.save_dashboard_html('docs/index.html')
            logger.info("Dashboard generated for GitHub Pages")
        else:
            logger.info("Running in continuous mode")
            monitor.run_continuous()
            
    except Exception as e:
        logger.error(f"Failed to start Reddit monitor: {e}")
        raise

if __name__ == "__main__":
    main()