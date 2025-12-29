#!/usr/bin/env python3
"""
Blacklist Manager for Escrow Bot
Blocks specific users from using the bot
"""
import json
import os
import logging

logger = logging.getLogger(__name__)

# Paths
BLACKLIST_FILE = 'data/blacklist.json'

def load_blacklist():
    """Load blacklist data"""
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            return json.load(f)
    return {"users": [], "usernames": []}

def save_blacklist(blacklist):
    """Save blacklist data"""
    os.makedirs('data', exist_ok=True)
    with open(BLACKLIST_FILE, 'w') as f:
        json.dump(blacklist, f, indent=2)

def add_to_blacklist(user_id=None, username=None, reason=""):
    """Add user to blacklist"""
    blacklist = load_blacklist()
    
    if user_id and user_id not in blacklist["users"]:
        blacklist["users"].append(user_id)
        logger.info(f"Added user_id {user_id} to blacklist: {reason}")
    
    if username and username.lower() not in [u.lower() for u in blacklist["usernames"]]:
        blacklist["usernames"].append(username.lower())
        logger.info(f"Added username @{username} to blacklist: {reason}")
    
    save_blacklist(blacklist)
    return True

def remove_from_blacklist(user_id=None, username=None):
    """Remove user from blacklist"""
    blacklist = load_blacklist()
    
    if user_id and user_id in blacklist["users"]:
        blacklist["users"].remove(user_id)
        logger.info(f"Removed user_id {user_id} from blacklist")
    
    if username:
        username_lower = username.lower()
        blacklist["usernames"] = [u for u in blacklist["usernames"] if u != username_lower]
        logger.info(f"Removed username @{username} from blacklist")
    
    save_blacklist(blacklist)
    return True

def is_blacklisted(user_obj):
    """Check if user is blacklisted by ID or username"""
    try:
        blacklist = load_blacklist()
        
        # Check by user ID
        user_id = getattr(user_obj, 'id', None)
        if user_id and str(user_id) in blacklist["users"]:
            return True, "User ID is blacklisted"
        
        # Check by username
        username = getattr(user_obj, 'username', None)
        if username and username.lower() in blacklist["usernames"]:
            return True, f"Username @{username} is blacklisted"
        
        # Check by first name (optional, for known scammers)
        first_name = getattr(user_obj, 'first_name', '').lower()
        known_scammers = ["alyaassis"]  # Add known scammer names
        
        for scammer in known_scammers:
            if scammer in first_name:
                return True, f"Known scammer name detected: {scammer}"
        
        return False, ""
        
    except Exception as e:
        logger.error(f"Error checking blacklist: {e}")
        return False, ""
