# Reddit Community Cleanup

A Chrome extension (Manifest V3) for Reddit moderators and power users. Provides a unified dashboard for filtering posts, performing bulk moderation actions, analyzing community health, and automating enforcement rules — all from within the browser.

## Features

### 📊 Dashboard
- Subreddit stats: post count, unique authors, average karma, flair distribution
- Top contributor leaderboard
- Data via DOM scraping (no login required) or Reddit API (richer data)

### 🔍 Filter & Search
- Filter posts by karma threshold, age, flair, and regex pattern
- Sort by new, top, hot, or controversial
- Save named filter views for quick reuse
- Export filtered results as CSV or JSON

### ⚡ Bulk Actions
- Batch remove, approve, lock, unlock, sticky, distinguish, flair, NSFW, and spoiler toggle
- Supports 11 mod action types
- Works via Reddit API (preferred) with DOM fallback
- Action log tracks every operation

### 🏷️ Auto-Organization
- Keyword-based auto-tagging with configurable tag→keyword mappings
- Duplicate post detection using bigram similarity
- Feed health analysis with engagement scoring (Hot/Rising/Stale/Dead tiers)

### 📈 Mod Queue Insights
- Pending items over time chart
- Response SLA compliance meter (target: 24h)
- Mod workload distribution view

### 📬 Mod Tools
- Mod log viewer with action-type filtering
- Quick mod note composer with label support
- User lookup: karma, account age, join date, verification status

### ⚖️ Enforcement Rules
- Configurable automated rules: karma floor, account age, flair required, regex blacklist, duplicate detection
- Actions: remove, report, flag, or lock
- Scheduled background scans with configurable intervals
- Desktop notifications when rule violations are found

### ⚙️ Settings
- Dark and light theme
- Default filter preferences
- Import/export all settings as JSON
- Clear all data

## Installation

1. Download or clone this repository
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable **Developer mode** (top right toggle)
4. Click **Load unpacked**
5. Select the `reddit-community-cleanup/` directory
6. The extension icon appears in your toolbar — click it to open

## Usage

1. Navigate to any Reddit subreddit page
2. Click the extension icon in your toolbar (or press `Alt+R`)
3. Click **↻ Refresh Data** to scrape current page data
4. If logged into Reddit, the green dot appears and **Fetch via API** becomes available for richer data

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Alt+R` | Open extension popup |
| `Alt+1` — `Alt+6` | Switch tabs |
| `Alt+A` | Select/deselect all posts |
| `Escape` | Deselect all |

## Architecture

```
manifest.json         Extension manifest (MV3)
background.js         Service worker: scheduled scans, alarms, notifications
content_script.js     DOM scraping: posts + comments on Reddit pages
content_inject.css    Active indicator styles
popup.html/js         Main popup UI controller
settings.html/js      Settings page controller
reddit_api.js         Reddit API client (cookie-based session auth)
rules_engine.js       Automated enforcement rules engine
filters.js            Post filtering and sorting logic
auto_organization.js  Auto-tagging and duplicate detection
bulk_actions.js       Batch moderation action executor
mod_tools.js          Mod log, notes, and user lookup
mod_queue_insights.js Mod queue analytics
export.js             CSV/JSON export
storage.js            chrome.storage persistence layer
utils.js              Shared utilities (escapeHTML, formatNumber, etc.)
styles.css            Dark/light theme CSS
```

## Permissions

| Permission | Why |
|------------|-----|
| `storage` | Save preferences, rules, views |
| `activeTab` | Read current Reddit page |
| `downloads` | Export CSV/JSON files |
| `alarms` | Scheduled background scans |
| `notifications` | Scan result alerts |
| `host_permissions` (reddit.com) | API requests with session cookies |

## Requirements

- Google Chrome (or Chromium-based browser)
- No API keys required — uses your existing Reddit login session

## License

MIT
