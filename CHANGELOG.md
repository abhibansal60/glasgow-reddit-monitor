# Changelog

## [1.1.0] - 2025-08-23

### Added
- **Test Notification Feature**: Added command-line test functionality
  - Usage: `python main.py test [email|telegram|both]`
  - Sends test notifications to verify email and/or Telegram configuration

- **Flair-Based Priority Monitoring**: Added support for Reddit flair filtering
  - r/glasgow now monitors flair "Ticket share. No adverts, free tickets only" as priority
  - Flair posts are checked first before keyword-based scanning
  - Flair matches are marked with `match_type: 'flair_priority'`

- **Lenient Mode for Less Active Subreddits**: 
  - r/glasgowmarket now uses 48-hour time window instead of 24 hours
  - Improves catch rate for less frequently posted subreddits

- **Enhanced Telegram Integration**: 
  - Added Telegram bot token and chat ID to GitHub Actions workflow
  - Improved notification formatting with match type indicators

### Changed
- Updated notification messages to show match type (keyword vs flair priority)
- Enhanced HTML email formatting with clearer match indicators
- Improved Telegram message formatting with match type information

### Technical Details
- Added `flair_priority` dict for subreddit-specific flair monitoring
- Added `lenient_subreddits` list for extended time filtering
- Added `_check_flair_posts()` method for flair-specific post retrieval
- Added `send_test_notification()` method for testing purposes
- Enhanced `check_subreddit()` to handle both flair and keyword matching