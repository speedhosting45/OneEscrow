#!/usr/bin/env python3
"""
Address Handler for Escrow Bot
Handles /buyer and /seller commands with validation
"""
import re
import json
import os
import logging
import time
import asyncio
import aiohttp
from telethon import events
from telethon.tl import types

# Import texts
from utils.texts import (
    BUYER_ADDRESS_PROMPT, SELLER_ADDRESS_PROMPT,
    ADDRESS_SAVED, INVALID_ADDRESS,
    NO_ROLE, ADDRESS_ALREADY_SET,
    ADDRESSES_VIEW, NO_ADDRESSES_SET,
    ADDRESS_VERIFICATION_FAILED
)

# Setup logging
logger = logging.getLogger(__name__)

# Paths
USER_ADDRESSES_FILE = 'data/user_addresses.json'
USER_ROLES_FILE = 'data/user_roles.json'
ACTIVE_GROUPS_FILE = 'data/active_groups.json'

def load_addresses():
    """Load user addresses"""
    if os.path.exists(USER_ADDRESSES_FILE):
        with open(USER_ADDRESSES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_addresses(addresses):
    """Save user addresses"""
    os.makedirs('data', exist_ok=True)
    with open(USER_ADDRESSES_FILE, 'w') as f:
        json.dump(addresses, f, indent=2)

def load_user_roles():
    """Load user roles"""
    if os.path.exists(USER_ROLES_FILE):
        with open(USER_ROLES_FILE, 'r') as f:
            return json.load(f)
    return {}

def load_groups():
    """Load active groups"""
    if os.path.exists(ACTIVE_GROUPS_FILE):
        with open(ACTIVE_GROUPS_FILE, 'r') as f:
            return json.load(f)
    return {}

class AddressValidator:
    """Validate cryptocurrency addresses"""
    
    # Regex patterns for supported chains
    PATTERNS = {
        'USDT_BEP20': r'^0x[a-fA-F0-9]{40}$',
        'USDT_TRC20': r'^T[0-9a-zA-Z]{33}$',
        'ETH': r'^0x[a-fA-F0-9]{40}$',
        'BTC': [
            r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$',  # Legacy
            r'^bc1[ac-hj-np-z02-9]{11,71}$',  # Bech32
        ],
        'LTC': [
            r'^[LM][a-km-zA-HJ-NP-Z1-9]{26,33}$',  # Legacy
            r'^ltc1[ac-hj-np-z02-9]{11,71}$',  # Bech32
        ]
    }
    
    # API keys (you can add your own API keys here)
    API_KEYS = {
        'bscscan': '',  # Add BSCScan API key
        'etherscan': '',  # Add Etherscan API key
        'blockcypher': ''  # Add BlockCypher API key
    }
    
    @staticmethod
    def validate_address(address: str) -> tuple:
        """Validate address and return (is_valid, chain)"""
        address = address.strip()
        
        # Check USDT BEP20 (Ethereum format)
        if re.match(AddressValidator.PATTERNS['USDT_BEP20'], address):
            return True, 'USDT (BEP20)'
        
        # Check USDT TRC20
        if re.match(AddressValidator.PATTERNS['USDT_TRC20'], address):
            return True, 'USDT (TRC20)'
        
        # Check ETH
        if re.match(AddressValidator.PATTERNS['ETH'], address):
            return True, 'ETH'
        
        # Check BTC
        for pattern in AddressValidator.PATTERNS['BTC']:
            if re.match(pattern, address):
                return True, 'BTC'
        
        # Check LTC
        for pattern in AddressValidator.PATTERNS['LTC']:
            if re.match(pattern, address):
                return True, 'LTC'
        
        return False, 'Unknown'
    
    @staticmethod
    async def verify_on_blockchain(address: str, chain: str) -> bool:
        """Verify address exists on blockchain (API call)"""
        try:
            # Map chains to API endpoints
            apis = {
                'USDT (BEP20)': {
                    'url': f'https://api.bscscan.com/api?module=account&action=balance&address={address}&tag=latest',
                    'check': lambda data: data.get('status') == '1' and data.get('message') == 'OK'
                },
                'USDT (TRC20)': {
                    'url': f'https://apilist.tronscan.org/api/account?address={address}',
                    'check': lambda data: 'data' in data or 'balance' in data
                },
                'ETH': {
                    'url': f'https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest',
                    'check': lambda data: data.get('status') == '1' and data.get('message') == 'OK'
                },
                'BTC': {
                    'url': f'https://blockchain.info/balance?active={address}',
                    'check': lambda data: bool(data) and address in data
                },
                'LTC': {
                    'url': f'https://api.blockcypher.com/v1/ltc/main/addrs/{address}/balance',
                    'check': lambda data: 'balance' in data or 'address' in data
                }
            }
            
            if chain not in apis:
                logger.warning(f"No API configured for chain: {chain}")
                return True  # Skip verification if no API
            
            api_config = apis[chain]
            url = api_config['url']
            
            # Add API keys if available
            if chain == 'USDT (BEP20)' and AddressValidator.API_KEYS['bscscan']:
                url += f"&apikey={AddressValidator.API_KEYS['bscscan']}"
            elif chain == 'ETH' and AddressValidator.API_KEYS['etherscan']:
                url += f"&apikey={AddressValidator.API_KEYS['etherscan']}"
            
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"API response for {chain}: {data}")
                        return api_config['check'](data)
                    else:
                        logger.error(f"API error {response.status} for {chain}: {await response.text()}")
                        return False
            
            return False
        except asyncio.TimeoutError:
            logger.error(f"Timeout verifying {chain} address: {address}")
            return False  # Timeout - reject address
        except Exception as e:
            logger.error(f"Blockchain verification failed for {chain}: {e}")
            return False  # If verification fails, reject address

async def handle_buyer_address(event, client):
    """Handle /buyer command - SEND RESPONSE IN GROUP"""
    try:
        user = await event.get_sender()
        chat = await event.get_chat()
        
        # Get address from command
        text = event.text.strip()
        if len(text.split()) < 2:
            await event.reply(BUYER_ADDRESS_PROMPT, parse_mode='html')
            return
        
        address = text.split(maxsplit=1)[1].strip()
        
        # Validate address format
        is_valid, chain = AddressValidator.validate_address(address)
        if not is_valid:
            await event.reply(
                INVALID_ADDRESS.format(address=address),
                parse_mode='html'
            )
            return
        
        # Verify on blockchain
        verified = await AddressValidator.verify_on_blockchain(address, chain)
        if not verified:
            await event.reply(
                ADDRESS_VERIFICATION_FAILED.format(address=address, chain=chain),
                parse_mode='html'
            )
            return
        
        # Check user has buyer role
        roles = load_user_roles()
        user_has_role = False
        user_role_data = None
        group_id = None
        
        for gid, role_data in roles.items():
            for uid, data in role_data.items():
                if int(uid) == user.id and data.get('role') == 'buyer':
                    user_has_role = True
                    user_role_data = data
                    group_id = gid
                    break
            if user_has_role:
                break
        
        if not user_has_role:
            await event.reply(NO_ROLE, parse_mode='html')
            return
        
        # Check if address already set
        addresses = load_addresses()
        if group_id not in addresses:
            addresses[group_id] = {}
        
        if 'buyer' in addresses[group_id]:
            await event.reply(
                ADDRESS_ALREADY_SET.format(
                    role='Buyer',
                    address=addresses[group_id]['buyer']['address']
                ),
                parse_mode='html'
            )
            return
        
        # Save address
        addresses[group_id]['buyer'] = {
            'address': address,
            'chain': chain,
            'user_id': user.id,
            'username': user.username or user.first_name or f"User_{user.id}",
            'saved_at': time.time()
        }
        save_addresses(addresses)
        
        # Send confirmation IN THE GROUP
        await event.reply(
            ADDRESS_SAVED.format(
                role='Buyer',
                address=address,
                chain=chain,
                user_mention=f"<a href='tg://user?id={user.id}'>{user_role_data['name']}</a>"
            ),
            parse_mode='html'
        )
        
        logger.info(f"Buyer address saved: {user.id} -> {address} ({chain})")
        
    except Exception as e:
        logger.error(f"Error in handle_buyer_address: {e}")
        await event.reply("❌ Error saving address", parse_mode='html')

async def handle_seller_address(event, client):
    """Handle /seller command - SEND RESPONSE IN GROUP"""
    try:
        user = await event.get_sender()
        chat = await event.get_chat()
        
        # Get address from command
        text = event.text.strip()
        if len(text.split()) < 2:
            await event.reply(SELLER_ADDRESS_PROMPT, parse_mode='html')
            return
        
        address = text.split(maxsplit=1)[1].strip()
        
        # Validate address format
        is_valid, chain = AddressValidator.validate_address(address)
        if not is_valid:
            await event.reply(
                INVALID_ADDRESS.format(address=address),
                parse_mode='html'
            )
            return
        
        # Verify on blockchain
        verified = await AddressValidator.verify_on_blockchain(address, chain)
        if not verified:
            await event.reply(
                ADDRESS_VERIFICATION_FAILED.format(address=address, chain=chain),
                parse_mode='html'
            )
            return
        
        # Check user has seller role
        roles = load_user_roles()
        user_has_role = False
        user_role_data = None
        group_id = None
        
        for gid, role_data in roles.items():
            for uid, data in role_data.items():
                if int(uid) == user.id and data.get('role') == 'seller':
                    user_has_role = True
                    user_role_data = data
                    group_id = gid
                    break
            if user_has_role:
                break
        
        if not user_has_role:
            await event.reply(NO_ROLE, parse_mode='html')
            return
        
        # Check if address already set
        addresses = load_addresses()
        if group_id not in addresses:
            addresses[group_id] = {}
        
        if 'seller' in addresses[group_id]:
            await event.reply(
                ADDRESS_ALREADY_SET.format(
                    role='Seller',
                    address=addresses[group_id]['seller']['address']
                ),
                parse_mode='html'
            )
            return
        
        # Save address
        addresses[group_id]['seller'] = {
            'address': address,
            'chain': chain,
            'user_id': user.id,
            'username': user.username or user.first_name or f"User_{user.id}",
            'saved_at': time.time()
        }
        save_addresses(addresses)
        
        # Send confirmation IN THE GROUP
        await event.reply(
            ADDRESS_SAVED.format(
                role='Seller',
                address=address,
                chain=chain,
                user_mention=f"<a href='tg://user?id={user.id}'>{user_role_data['name']}</a>"
            ),
            parse_mode='html'
        )
        
        logger.info(f"Seller address saved: {user.id} -> {address} ({chain})")
        
    except Exception as e:
        logger.error(f"Error in handle_seller_address: {e}")
        await event.reply("❌ Error saving address", parse_mode='html')

async def handle_view_addresses(event, client):
    """Handle /addresses command to view saved addresses"""
    try:
        user = await event.get_sender()
        chat = await event.get_chat()
        
        # Find user's group
        roles = load_user_roles()
        addresses = load_addresses()
        groups = load_groups()
        
        user_group_id = None
        
        for group_id, role_data in roles.items():
            for uid in role_data:
                if int(uid) == user.id:
                    user_group_id = group_id
                    break
            if user_group_id:
                break
        
        if not user_group_id:
            await event.reply("❌ No active escrow session found", parse_mode='html')
            return
        
        # Get addresses for this group
        group_addresses = addresses.get(user_group_id, {})
        group_info = groups.get(user_group_id, {})
        group_name = group_info.get('name', 'Unknown Group')
        
        if not group_addresses or ('buyer' not in group_addresses and 'seller' not in group_addresses):
            await event.reply(NO_ADDRESSES_SET, parse_mode='html')
            return
        
        # Format response
        buyer_data = group_addresses.get('buyer', {})
        seller_data = group_addresses.get('seller', {})
        
        buyer_mention = f"<a href='tg://user?id={buyer_data.get('user_id', '')}'>{buyer_data.get('username', 'Unknown')}</a>" if buyer_data else "❌ Not set"
        seller_mention = f"<a href='tg://user?id={seller_data.get('user_id', '')}'>{seller_data.get('username', 'Unknown')}</a>" if seller_data else "❌ Not set"
        
        buyer_address = buyer_data.get('address', 'Not set')
        seller_address = seller_data.get('address', 'Not set')
        buyer_chain = buyer_data.get('chain', 'N/A')
        seller_chain = seller_data.get('chain', 'N/A')
        
        await event.reply(
            ADDRESSES_VIEW.format(
                buyer_mention=buyer_mention,
                buyer_address=buyer_address,
                buyer_chain=buyer_chain,
                seller_mention=seller_mention,
                seller_address=seller_address,
                seller_chain=seller_chain,
                group_name=group_name
            ),
            parse_mode='html'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_view_addresses: {e}")
        await event.reply("❌ Error viewing addresses", parse_mode='html')

def setup_address_handlers(client):
    """Setup address command handlers - DON'T DELETE COMMANDS"""
    
    @client.on(events.NewMessage(pattern=r'^/buyer(\s|$)'))
    async def buyer_handler(event):
        await handle_buyer_address(event, client)
    
    @client.on(events.NewMessage(pattern=r'^/seller(\s|$)'))
    async def seller_handler(event):
        await handle_seller_address(event, client)
    
    @client.on(events.NewMessage(pattern=r'^/addresses(\s|$)'))
    async def addresses_handler(event):
        await handle_view_addresses(event, client)
    
    logger.info("✅ Address handlers setup complete - Commands will not be deleted")
