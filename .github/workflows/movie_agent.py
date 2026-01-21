import requests
import feedparser
import os
import google.generativeai as genai
from datetime import datetime, timezone

# --- CONFIGURATION ---
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
USER_AGENT = "MovieglitchAI/2.0"

# --- SOURCES ---
# 1. Reddit (Messy, fast)
REDDIT_URL = "https://www.reddit.com/r/Steelbooks+4kbluray+boutiquebluray/search.json?q=%22OOP%22+OR+%22Restock%22+OR+%22Glitch%22+OR+%22Misprice%22+OR+%22Steal%22&restrict_sr=on&sort=new&limit=5"
# 2. Slickdeals (Verified sales)
SLICKDEALS_RSS = "https://slickdeals.net/newsearch.php?mode=popdeals&searcharea=deals&sort=newest&q=4k+blu-ray&rss=1"

# --- AI SETUP ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

def analyze_deal_with_gemini(title, subreddit):
    """Asks Gemini: Is this a real deal or just discussion?"""
    if not GEMINI_API_KEY: return True # Fail open if no key
    
    prompt = f"""
    Review this Reddit post title from r/{subreddit}: "{title}"
    Is this reporting a specific purchasing opportunity, restock, sale, or price error?
    Answer YES if it is a deal. Answer NO if it is discussion.
    Answer only one word.
    """
    try:
        response = model.generate_content(prompt)
        decision = response.text.strip().upper()
        print(f"   [AI] Analysis of '{title}': {decision}")
        return "YES" in decision
    except:
        return True

def send_discord_alert(source, title, link, is_verified=False):
    if not WEBHOOK_URL: return
    emoji = "🔥"
    if "Reddit" in source: emoji = "🔥"
    if is_verified: emoji = "🤖" # Robot face = AI Verified
    if "Slick" in source: emoji = "💰"

    data = {"content": f"{emoji} **{source}**\n**{title}**\n[View Link]({link})"}
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
            # Time Filter: Last 15 mins
            post_time = datetime.fromtimestamp(data['created_utc'], timezone.utc)
            minutes_ago = (datetime.now(timezone.utc) - post_time).total_seconds() / 60
            
            if minutes_ago <= 15:
                print(f"-> Fresh Post: {data['title']}")
                if analyze_deal_with_gemini(data['title'], data['subreddit']):
                    print("   -> VERIFIED! Sending alert.")
                    send_discord_alert(f"r/{data['subreddit']}", data['title'], f"https://www.reddit.com{data['permalink']}", is_verified=True)
    except Exception as e:
        print(f"Reddit Error: {e}")

def check_rss(name, url):
    print(f"--- Checking {name} ---")
    try:
        feed = feedparser.parse(url)
        triggers = ["steelbook", "4k", "criterion", "sale", "price error"]
        for entry in feed.entries[:3]:
            if any(w in entry.title.lower() for w in triggers):
                 print(f"-> Match: {entry.title}")
                 send_discord_alert(name, entry.title, entry.link)
    except Exception as e:
        print(f"RSS Error: {e}")

if __name__ == "__main__":
    check_reddit()
    check_rss("Slickdeals", SLICKDEALS_RSS)
