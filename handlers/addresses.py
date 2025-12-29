#!/usr/bin/env python3
"""
Minimal Address Handler for Escrow Bot
"""
import re
import json
import os
import logging
import time
from telethon import events

# Import texts
from utils.texts import (
    BUYER_ADDRESS_PROMPT, SELLER_ADDRESS_PROMPT,
    ADDRESS_SAVED, INVALID_ADDRESS,
    NO_ROLE, ADDRESS_ALREADY_SET,
    ADDRESSES_VIEW, NO_ADDRESSES_SET,
    ADDRESS_VERIFICATION_FAILED
)

logger = logging.getLogger(__name__)

USER_ADDRESSES_FILE = 'data/user_addresses.json'
USER_ROLES_FILE = 'data/user_roles.json'

def load_addresses():
    if os.path.exists(USER_ADDRESSES_FILE):
        with open(USER_ADDRESSES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_addresses(addresses):
    os.makedirs('data', exist_ok=True)
    with open(USER_ADDRESSES_FILE, 'w') as f:
        json.dump(addresses, f, indent=2)

def load_user_roles():
    if os.path.exists(USER_ROLES_FILE):
        with open(USER_ROLES_FILE, 'r') as f:
            return json.load(f)
    return {}

class AddressValidator:
    PATTERNS = {
        'USDT_BEP20': r'^0x[a-fA-F0-9]{40}$',
        'USDT_TRC20': r'^T[0-9a-zA-Z]{33}$',
        'ETH': r'^0x[a-fA-F0-9]{40}$',
        'BTC': [r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$', r'^bc1[ac-hj-np-z02-9]{11,71}$'],
        'LTC': [r'^[LM][a-km-zA-HJ-NP-Z1-9]{26,33}$', r'^ltc1[ac-hj-np-z02-9]{11,71}$']
    }
    
    @staticmethod
    def validate_address(address: str):
        address = address.strip()
        if re.match(AddressValidator.PATTERNS['USDT_BEP20'], address):
            return True, 'USDT (BEP20)'
        if re.match(AddressValidator.PATTERNS['USDT_TRC20'], address):
            return True, 'USDT (TRC20)'
        if re.match(AddressValidator.PATTERNS['ETH'], address):
            return True, 'ETH'
        for pattern in AddressValidator.PATTERNS['BTC']:
            if re.match(pattern, address):
                return True, 'BTC'
        for pattern in AddressValidator.PATTERNS['LTC']:
            if re.match(pattern, address):
                return True, 'LTC'
        return False, 'Unknown'

async def handle_buyer_address(event, client):
    try:
        user = await event.get_sender()
        text = event.text.strip()
        if len(text.split()) < 2:
            await event.reply(BUYER_ADDRESS_PROMPT, parse_mode='html')
            return
        
        address = text.split(maxsplit=1)[1].strip()
        is_valid, chain = AddressValidator.validate_address(address)
        if not is_valid:
            await event.reply(INVALID_ADDRESS.format(address=address), parse_mode='html')
            return
        
        roles = load_user_roles()
        user_group_id = None
        user_role_data = None
        
        for gid, role_data in roles.items():
            for uid, data in role_data.items():
                if int(uid) == user.id and data.get('role') == 'buyer':
                    user_group_id = gid
                    user_role_data = data
                    break
            if user_group_id:
                break
        
        if not user_group_id:
            await event.reply(NO_ROLE, parse_mode='html')
            return
        
        addresses = load_addresses()
        if user_group_id not in addresses:
            addresses[user_group_id] = {}
        
        if 'buyer' in addresses[user_group_id]:
            await event.reply(ADDRESS_ALREADY_SET.format(
                role='Buyer', address=addresses[user_group_id]['buyer']['address']
            ), parse_mode='html')
            return
        
        addresses[user_group_id]['buyer'] = {
            'address': address, 'chain': chain, 'user_id': user.id,
            'username': user.username or user.first_name or f"User_{user.id}",
            'saved_at': time.time()
        }
        save_addresses(addresses)
        
        await event.reply(ADDRESS_SAVED.format(
            role='Buyer', address=address, chain=chain,
            user_mention=f"<a href='tg://user?id={user.id}'>{user_role_data['name']}</a>"
        ), parse_mode='html')
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await event.reply("❌ Error", parse_mode='html')

async def handle_seller_address(event, client):
    try:
        user = await event.get_sender()
        text = event.text.strip()
        if len(text.split()) < 2:
            await event.reply(SELLER_ADDRESS_PROMPT, parse_mode='html')
            return
        
        address = text.split(maxsplit=1)[1].strip()
        is_valid, chain = AddressValidator.validate_address(address)
        if not is_valid:
            await event.reply(INVALID_ADDRESS.format(address=address), parse_mode='html')
            return
        
        roles = load_user_roles()
        user_group_id = None
        user_role_data = None
        
        for gid, role_data in roles.items():
            for uid, data in role_data.items():
                if int(uid) == user.id and data.get('role') == 'seller':
                    user_group_id = gid
                    user_role_data = data
                    break
            if user_group_id:
                break
        
        if not user_group_id:
            await event.reply(NO_ROLE, parse_mode='html')
            return
        
        addresses = load_addresses()
        if user_group_id not in addresses:
            addresses[user_group_id] = {}
        
        if 'seller' in addresses[user_group_id]:
            await event.reply(ADDRESS_ALREADY_SET.format(
                role='Seller', address=addresses[user_group_id]['seller']['address']
            ), parse_mode='html')
            return
        
        addresses[user_group_id]['seller'] = {
            'address': address, 'chain': chain, 'user_id': user.id,
            'username': user.username or user.first_name or f"User_{user.id}",
            'saved_at': time.time()
        }
        save_addresses(addresses)
        
        await event.reply(ADDRESS_SAVED.format(
            role='Seller', address=address, chain=chain,
            user_mention=f"<a href='tg://user?id={user.id}'>{user_role_data['name']}</a>"
        ), parse_mode='html')
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await event.reply("❌ Error", parse_mode='html')

async def handle_view_addresses(event, client):
    try:
        user = await event.get_sender()
        roles = load_user_roles()
        user_group_id = None
        
        for group_id, role_data in roles.items():
            for uid in role_data:
                if int(uid) == user.id:
                    user_group_id = group_id
                    break
            if user_group_id:
                break
        
        if not user_group_id:
            await event.reply("❌ No active session", parse_mode='html')
            return
        
        addresses = load_addresses()
        group_addresses = addresses.get(user_group_id, {})
        
        if not group_addresses:
            await event.reply(NO_ADDRESSES_SET, parse_mode='html')
            return
        
        buyer_data = group_addresses.get('buyer', {})
        seller_data = group_addresses.get('seller', {})
        
        buyer_mention = f"<a href='tg://user?id={buyer_data.get('user_id', '')}'>{buyer_data.get('username', 'Unknown')}</a>" if buyer_data else "❌ Not set"
        seller_mention = f"<a href='tg://user?id={seller_data.get('user_id', '')}'>{seller_data.get('username', 'Unknown')}</a>" if seller_data else "❌ Not set"
        
        buyer_address = buyer_data.get('address', 'Not set')
        seller_address = seller_data.get('address', 'Not set')
        buyer_chain = buyer_data.get('chain', 'N/A')
        seller_chain = seller_data.get('chain', 'N/A')
        
        await event.reply(ADDRESSES_VIEW.format(
            buyer_mention=buyer_mention, buyer_address=buyer_address, buyer_chain=buyer_chain,
            seller_mention=seller_mention, seller_address=seller_address, seller_chain=seller_chain,
            group_name="Escrow Group"
        ), parse_mode='html')
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await event.reply("❌ Error", parse_mode='html')

def setup_address_handlers(client):
    @client.on(events.NewMessage(pattern=r'^/buyer(\s|$)'))
    async def buyer_handler(event):
        await handle_buyer_address(event, client)
    
    @client.on(events.NewMessage(pattern=r'^/seller(\s|$)'))
    async def seller_handler(event):
        await handle_seller_address(event, client)
    
    @client.on(events.NewMessage(pattern=r'^/addresses(\s|$)'))
    async def addresses_handler(event):
        await handle_view_addresses(event, client)
    
    logger.info("✅ Address handlers setup")
