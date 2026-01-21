import requests
import feedparser
import os
import google.generativeai as genai
from datetime import datetime, timezone

# --- CONFIGURATION ---
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
USER_AGENT = "MovieglitchAI/3.0"

# --- TIME WINDOW (Crucial for Deduplication) ---
# The bot runs every 5 minutes. We check the last 5 minutes.
# This ensures we see each post exactly once (mostly).
TIME_WINDOW_MINUTES = 5

# --- SOURCES ---
REDDIT_URL = "https://www.reddit.com/r/Steelbooks+4kbluray+boutiquebluray/search.json?q=%22OOP%22+OR+%22Restock%22+OR+%22Glitch%22+OR+%22Misprice%22+OR+%22Steal%22&restrict_sr=on&sort=new&limit=10"
SLICKDEALS_RSS = "https://slickdeals.net/newsearch.php?mode=popdeals&searcharea=deals&sort=newest&q=4k+blu-ray&rss=1"

# --- AI SETUP ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

def analyze_profit_potential(title, subreddit):
    """
    Asks Gemini: Will this item flip for a profit?
    """
    if not GEMINI_API_KEY: return True # Fail open if no key
    
    prompt = f"""
    You are a ruthless eBay flipper and arbitrage expert.
    Analyze this Reddit post title from r/{subreddit}: "{title}"
    
    Your Goal: Identify items that can be bought and resold for a HIGH PROFIT.
    
    Criteria for YES:
    1. Is it a "Price Mistake" or "Glitch" (e.g. 90% off)?
    2. Is it a "Steelbook" restock (high collector value)?
    3. Is it "Out of Print" (OOP) or "Limited Edition"?
    4. Is the profit margin likely > $20?
    
    Criteria for NO:
    1. Standard sales (e.g. "Buy 2 Get 1 Free", "$5 off").
    2. Common movies that are not rare.
    3. Questions or Show-off posts (e.g. "Look what I bought").
    
    Answer YES only if it is a high-profit flip opportunity.
    Answer NO if it is just a regular deal or discussion.
    Answer only one word.
    """
    
    try:
        response = model.generate_content(prompt)
        decision = response.text.strip().upper()
        print(f"   [AI] Profit Analysis of '{title}': {decision}")
        return "YES" in decision
    except Exception as e:
        print(f"   [AI] Error: {e}")
        return True 

def send_discord_alert(source, title, link, is_verified=False):
    if not WEBHOOK_URL: return
    
    emoji = "💰" # Money bag for profit
    if is_verified: emoji = "🤖" # Robot for AI verified
    
    data = {
        "content": f"{emoji} **PROFIT OPPORTUNITY**\n**{title}**\n[View Link]({link})"
    }
    requests.post(WEBHOOK_URL, json=data)

def check_reddit():
    print("--- Checking Reddit ---")
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(REDDIT_URL, headers=headers)
        response.raise_for_status()
        posts = response.json()['data']['children']
        
        for post in posts:
            data = post['data']
            # Strict Time Window Check
            post_time = datetime.fromtimestamp(data['created_utc'], timezone.utc)
            minutes_ago = (datetime.now(timezone.utc) - post_time).total_seconds() / 60
            
            # ONLY process if it falls in the exact window of the last run
            if minutes_ago <= TIME_WINDOW_MINUTES:
                print(f"-> Fresh Candidate: {data['title']}")
                
                # Ask the Brain
                is_profitable = analyze_profit_potential(data['title'], data['subreddit'])
                
                if is_profitable:
                    print("   -> HIGH PROFIT! Sending alert.")
                    send_discord_alert(f"r/{data['subreddit']}", data['title'], f"https://www.reddit.com{data['permalink']}", is_verified=True)
                else:
                    print("   -> Ignored (Low Profit/Noise).")
            else:
                # We skip old posts silently to avoid duplicates
                pass

    except Exception as e:
        print(f"Reddit Error: {e}")

def check_rss(name, url):
    print(f"--- Checking {name} ---")
    try:
        feed = feedparser.parse(url)
        # We need to filter RSS by time too, or we get duplicates.
        # Slickdeals usually provides 'published_parsed'
        
        for entry in feed.entries[:5]:
            title = entry.title
            link = entry.link
            
            # RSS Time Handling is tricky. We try to find a timestamp.
            if hasattr(entry, 'published_parsed'):
                published_time = datetime.fromtimestamp(time.mktime(entry.published_parsed), timezone.utc)
                minutes_ago = (datetime.now(timezone.utc) - published_time).total_seconds() / 60
                
                if minutes_ago <= TIME_WINDOW_MINUTES:
                     print(f"-> RSS Candidate: {title}")
                     # For RSS, we assume it's a deal (Gemini doesn't read linked RSS content easily yet)
                     # But we can still keyword filter for "Glitch" or "Error"
                     triggers = ["glitch", "price error", "mistake"]
                     if any(w in title.lower() for w in triggers):
                         send_discord_alert(name, title, link)
            else:
                # If no time data, we skip to be safe against spamming dupes
                pass
                 
    except Exception as e:
        print(f"RSS Error for {name}: {e}")

if __name__ == "__main__":
    check_reddit()
    check_rss("Slickdeals", SLICKDEALS_RSS)
