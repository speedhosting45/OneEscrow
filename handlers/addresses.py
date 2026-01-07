#!/usr/bin/env python3
"""
Advanced Address Handler for Escrow Bot - Multi-Chain Support
Supports: BTC, LTC, ETH, BSC, Polygon, USDT BEP-20, USDT TRC-20
"""
import re
import json
import os
import logging
import time
import asyncio
import aiohttp
from typing import Dict, Optional, Tuple, List
from datetime import datetime
from telethon import events
from colorama import init, Fore, Style, Back

# Initialize colorama for colored terminal output
init(autoreset=True)

# --- Enhanced Colored Logging ---
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors"""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Back.RED + Fore.WHITE
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, Fore.WHITE)
        message = super().format(record)
        return f"{color}{message}{Style.RESET_ALL}"

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Console handler with colors
console_handler = logging.StreamHandler()
console_handler.setFormatter(ColoredFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
))
logger.addHandler(console_handler)

# File handler for persistent logs
os.makedirs('logs', exist_ok=True)
file_handler = logging.FileHandler(
    f'logs/address_handler_{datetime.now().strftime("%Y%m%d")}.log',
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger.addHandler(file_handler)

# --- Paths ---
USER_ADDRESSES_FILE = 'data/user_addresses.json'
USER_ROLES_FILE = 'data/user_roles.json'
ACTIVE_GROUPS_FILE = 'data/active_groups.json'

# --- API Keys (Get from environment) ---
API_KEYS = {
    'etherscan': os.getenv('ETHERSCAN_API_KEY', 'DFPIRXHE54RBAZP9NIMYE3V5Z5K9U4Y126'),
    'bscscan': os.getenv('BSCSCAN_API_KEY', '7I7X2FJJVPCX64C1TSS57CNRQ2UY2A1WZ4'),
    'polygonscan': os.getenv('POLYGONSCAN_API_KEY', 'HPTF5DRNK2S79EY5UMBE4Y4I8GPYX4HSS7'),
    'blockcypher': os.getenv('BLOCKCYPHER_API_KEY', '7434a8ddf7244987b413e22353d3e266'),
    'tronscan': None  # TronScan doesn't require API key for basic queries
}

# --- Response Texts ---
TEXTS = {
    'BUYER_PROMPT': "👤 <b>Buyer Address Required</b>\n\nPlease send: <code>/buyer [your_address]</code>\n\nSupported formats:\n• BTC, LTC\n• ETH, BSC, Polygon\n• USDT (BEP-20/ERC-20/TRC-20)",
    'SELLER_PROMPT': "👤 <b>Seller Address Required</b>\n\nPlease send: <code>/seller [your_address]</code>\n\nSupported formats:\n• BTC, LTC\n• ETH, BSC, Polygon\n• USDT (BEP-20/ERC-20/TRC-20)",
    'PROCESSING': "🔍 <b>Processing Address...</b>\n\n<i>Verifying format and network...</i>",
    'VALIDATING': "🔄 <b>Validating on Blockchain...</b>\n\n<i>Checking activity and balance...</i>",
    'SAVED': """✅ <b>{role} Address Saved Successfully!</b>

<b>Address:</b> <code>{address}</code>
<b>Network:</b> {chain}
<b>User:</b> {user_mention}
<b>Status:</b> {status}

{wallet_info}

⚠️ <b>Important:</b> This address is now locked for this escrow session.""",
    'INVALID_FORMAT': "❌ <b>Invalid Address Format</b>\n\n<code>{address}</code>\n\nThis doesn't match any known cryptocurrency address format.",
    'NO_ROLE': "❌ <b>Access Denied</b>\n\nYou don't have the required role for this command.\nContact the group admin.",
    'ALREADY_SET': """⚠️ <b>Address Already Registered</b>

<b>Current {role} Address:</b> <code>{address}</code>
<b>Network:</b> {chain}
<b>Set by:</b> {user_mention}

To change, ask admin to clear first.""",
    'VIEW_ADDRESSES': """📋 <b>Escrow Addresses</b>
🏷️ <b>Group:</b> {group_name}

<b>Buyer:</b> {buyer_mention}
<code>{buyer_address}</code>
<b>Network:</b> {buyer_chain}
<b>Status:</b> {buyer_status}

<b>Seller:</b> {seller_mention}
<code>{seller_address}</code>
<b>Network:</b> {seller_chain}
<b>Status:</b> {seller_status}

<i>Last updated: {last_updated}</i>""",
    'NO_ADDRESSES': "📭 <b>No Addresses Set</b>\n\nBuyer and seller addresses haven't been set yet.",
    'DUPLICATE_USER': """❌ <b>Duplicate Role Detected</b>

You are already registered as <b>{existing_role}</b> in this group.

Current address: <code>{existing_address}</code>
Network: {existing_chain}

⚠️ One user cannot be both buyer and seller in the same escrow session.""",
    'WALLET_INFO': """📊 <b>Wallet Details:</b>
• Type: {wallet_type}
• Transactions: {tx_count}
• Balance: ≈ ${balance_usd}
• First Tx: {first_tx_date}
• Last Active: {last_tx_date}""",
    'VERIFICATION_FAILED': "❌ <b>Verification Failed</b>\n\nAddress <code>{address}</code> could not be verified on {chain}.\n\nPossible reasons:\n• Invalid address\n• Network issue\n• New wallet (0 transactions)"
}

# --- Data Management ---
def load_json(filepath: str) -> Dict:
    """Load JSON file safely"""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading {filepath}: {e}")
            return {}
    return {}

def save_json(filepath: str, data: Dict) -> bool:
    """Save JSON file safely"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        logger.error(f"Error saving {filepath}: {e}")
        return False

def load_addresses(): return load_json(USER_ADDRESSES_FILE)
def save_addresses(data): return save_json(USER_ADDRESSES_FILE, data)
def load_user_roles(): return load_json(USER_ROLES_FILE)
def load_groups(): return load_json(ACTIVE_GROUPS_FILE)

# --- Address Validator Class ---
class AdvancedAddressValidator:
    """Multi-chain cryptocurrency address validator with blockchain verification"""
    
    # Comprehensive regex patterns
    PATTERNS = {
        'BTC': [
            r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$',  # Legacy
            r'^bc1[ac-hj-np-z02-9]{11,71}$',       # Bech32
            r'^bc1p[ac-hj-np-z02-9]{11,71}$'       # Bech32m (Taproot)
        ],
        'LTC': [
            r'^[LM3][a-km-zA-HJ-NP-Z1-9]{26,33}$',  # Legacy
            r'^ltc1[ac-hj-np-z02-9]{11,71}$'        # Bech32
        ],
        'EVM': r'^0x[a-fA-F0-9]{40}$',  # ETH, BSC, Polygon, etc.
        'TRX': r'^T[0-9a-zA-Z]{33}$',   # Tron addresses
        'DOGE': r'^D[5-9A-HJ-NP-U][1-9A-HJ-NP-Za-km-z]{32}$',
        'XRP': r'^r[0-9a-zA-Z]{24,34}$',
    }
    
    # Chain configurations
    CHAIN_CONFIGS = {
        'BTC': {
            'name': 'Bitcoin',
            'symbol': 'BTC',
            'api_urls': [
                'https://blockchain.info/rawaddr/{address}?limit=0',
                'https://api.blockcypher.com/v1/btc/main/addrs/{address}'
            ],
            'explorer': 'https://blockchain.com/explorer/addresses/btc/{address}'
        },
        'LTC': {
            'name': 'Litecoin',
            'symbol': 'LTC',
            'api_urls': [
                'https://api.blockcypher.com/v1/ltc/main/addrs/{address}',
                'https://chain.so/api/v2/address/LTC/{address}'
            ],
            'explorer': 'https://blockchair.com/litecoin/address/{address}'
        },
        'ETH': {
            'name': 'Ethereum',
            'symbol': 'ETH',
            'api_urls': [
                f'https://api.etherscan.io/api?module=account&action=balance&address={{address}}&tag=latest&apikey={API_KEYS["etherscan"]}',
                f'https://api.etherscan.io/api?module=account&action=txlist&address={{address}}&startblock=0&endblock=99999999&page=1&offset=1&sort=asc&apikey={API_KEYS["etherscan"]}'
            ],
            'explorer': 'https://etherscan.io/address/{address}'
        },
        'BSC': {
            'name': 'BNB Smart Chain',
            'symbol': 'BNB',
            'api_urls': [
                f'https://api.bscscan.com/api?module=account&action=balance&address={{address}}&tag=latest&apikey={API_KEYS["bscscan"]}',
                f'https://api.bscscan.com/api?module=account&action=txlist&address={{address}}&startblock=0&endblock=99999999&page=1&offset=1&sort=asc&apikey={API_KEYS["bscscan"]}'
            ],
            'explorer': 'https://bscscan.com/address/{address}'
        },
        'POLYGON': {
            'name': 'Polygon',
            'symbol': 'MATIC',
            'api_urls': [
                f'https://api.polygonscan.com/api?module=account&action=balance&address={{address}}&tag=latest&apikey={API_KEYS["polygonscan"]}',
                f'https://api.polygonscan.com/api?module=account&action=txlist&address={{address}}&startblock=0&endblock=99999999&page=1&offset=1&sort=asc&apikey={API_KEYS["polygonscan"]}'
            ],
            'explorer': 'https://polygonscan.com/address/{address}'
        },
        'TRX': {
            'name': 'Tron',
            'symbol': 'TRX',
            'api_urls': [
                'https://apilist.tronscan.org/api/account?address={address}',
                'https://api.trongrid.io/v1/accounts/{address}'
            ],
            'explorer': 'https://tronscan.org/#/address/{address}'
        }
    }
    
    @staticmethod
    def detect_format(address: str) -> Tuple[str, str]:
        """Detect address format and chain type"""
        address = address.strip()
        
        # Check BTC
        for pattern in AdvancedAddressValidator.PATTERNS['BTC']:
            if re.match(pattern, address):
                return 'BTC', 'Bitcoin'
        
        # Check LTC
        for pattern in AdvancedAddressValidator.PATTERNS['LTC']:
            if re.match(pattern, address):
                return 'LTC', 'Litecoin'
        
        # Check EVM (ETH, BSC, Polygon, etc.)
        if re.match(AdvancedAddressValidator.PATTERNS['EVM'], address):
            return 'EVM', 'EVM Compatible'
        
        # Check TRX
        if re.match(AdvancedAddressValidator.PATTERNS['TRX'], address):
            return 'TRX', 'Tron'
        
        # Check DOGE
        if re.match(AdvancedAddressValidator.PATTERNS['DOGE'], address):
            return 'DOGE', 'Dogecoin'
        
        # Check XRP
        if re.match(AdvancedAddressValidator.PATTERNS['XRP'], address):
            return 'XRP', 'Ripple'
        
        return 'UNKNOWN', 'Unknown Format'
    
    @staticmethod
    async def verify_evm_chain(address: str) -> Tuple[str, Dict]:
        """Determine specific EVM chain (ETH, BSC, Polygon)"""
        async with aiohttp.ClientSession() as session:
            chains_to_check = ['ETH', 'BSC', 'POLYGON']
            results = {}
            
            for chain in chains_to_check:
                config = AdvancedAddressValidator.CHAIN_CONFIGS.get(chain)
                if not config or not config['api_urls']:
                    continue
                
                try:
                    url = config['api_urls'][0].format(address=address)
                    timeout = aiohttp.ClientTimeout(total=10)
                    
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Different APIs return different formats
                            if chain == 'ETH':
                                if data.get('status') == '1' or data.get('message') == 'OK':
                                    balance = int(data.get('result', 0)) / 10**18
                                    if balance > 0 or await AdvancedAddressValidator.check_evm_activity(session, address, chain):
                                        results[chain] = {
                                            'balance': balance,
                                            'valid': True,
                                            'name': config['name']
                                        }
                            elif chain == 'BSC':
                                if data.get('status') == '1':
                                    balance = int(data.get('result', 0)) / 10**18
                                    if balance > 0 or await AdvancedAddressValidator.check_evm_activity(session, address, chain):
                                        results[chain] = {
                                            'balance': balance,
                                            'valid': True,
                                            'name': config['name']
                                        }
                            elif chain == 'POLYGON':
                                if data.get('status') == '1':
                                    balance = int(data.get('result', 0)) / 10**18
                                    if balance > 0 or await AdvancedAddressValidator.check_evm_activity(session, address, chain):
                                        results[chain] = {
                                            'balance': balance,
                                            'valid': True,
                                            'name': config['name']
                                        }
                except Exception as e:
                    logger.debug(f"Chain {chain} check failed: {e}")
                    continue
            
            # Decision logic
            if not results:
                return 'EVM (Unverified)', {}
            
            # Prefer chains with balance
            for chain in ['ETH', 'BSC', 'POLYGON']:
                if chain in results and results[chain]['balance'] > 0:
                    return f"{results[chain]['name']} (ERC-20)", results[chain]
            
            # If all have 0 balance, check activity
            for chain in ['ETH', 'BSC', 'POLYGON']:
                if chain in results and await AdvancedAddressValidator.check_evm_activity(session, address, chain):
                    return f"{results[chain]['name']} (ERC-20/BEP-20)", results[chain]
            
            # Default to first valid chain
            first_chain = list(results.keys())[0]
            return f"{results[first_chain]['name']} (Unused)", results[first_chain]
    
    @staticmethod
    async def check_evm_activity(session: aiohttp.ClientSession, address: str, chain: str) -> bool:
        """Check if address has any transactions on EVM chain"""
        config = AdvancedAddressValidator.CHAIN_CONFIGS.get(chain)
        if not config or len(config['api_urls']) < 2:
            return False
        
        try:
            url = config['api_urls'][1].format(address=address)
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if chain == 'ETH':
                        return data.get('status') == '1' and len(data.get('result', [])) > 0
                    elif chain in ['BSC', 'POLYGON']:
                        return data.get('status') == '1' and len(data.get('result', [])) > 0
        except:
            pass
        return False
    
    @staticmethod
    async def get_wallet_info(address: str, chain_type: str) -> Dict:
        """Get detailed wallet information"""
        wallet_info = {
            'wallet_type': 'Unknown',
            'tx_count': 0,
            'balance_usd': 'N/A',
            'first_tx_date': 'Never',
            'last_tx_date': 'Never',
            'status': 'Unverified'
        }
        
        if chain_type == 'UNKNOWN':
            return wallet_info
        
        async with aiohttp.ClientSession() as session:
            try:
                if chain_type == 'BTC':
                    url = f'https://blockchain.info/rawaddr/{address}?limit=1'
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            wallet_info.update({
                                'wallet_type': 'Bitcoin Wallet',
                                'tx_count': data.get('n_tx', 0),
                                'balance_usd': f"${data.get('final_balance', 0) / 10**8:.2f}",
                                'first_tx_date': 'Active' if data.get('n_tx', 0) > 0 else 'New',
                                'last_tx_date': 'Recent' if data.get('n_tx', 0) > 0 else 'None',
                                'status': '✅ Verified' if data.get('n_tx', 0) > 0 else '🆕 New'
                            })
                
                elif chain_type == 'LTC':
                    url = f'https://api.blockcypher.com/v1/ltc/main/addrs/{address}'
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            wallet_info.update({
                                'wallet_type': 'Litecoin Wallet',
                                'tx_count': data.get('n_tx', 0),
                                'balance_usd': f"${data.get('balance', 0) / 10**8:.2f}",
                                'first_tx_date': 'Active' if data.get('n_tx', 0) > 0 else 'New',
                                'last_tx_date': 'Recent' if data.get('n_tx', 0) > 0 else 'None',
                                'status': '✅ Verified' if data.get('n_tx', 0) > 0 else '🆕 New'
                            })
                
                elif chain_type == 'EVM':
                    # Try ETH first
                    config = AdvancedAddressValidator.CHAIN_CONFIGS.get('ETH')
                    if config and API_KEYS['etherscan']:
                        url = f'https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&page=1&offset=10&sort=asc&apikey={API_KEYS["etherscan"]}'
                        async with session.get(url, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get('status') == '1':
                                    txs = data.get('result', [])
                                    wallet_info.update({
                                        'wallet_type': 'Ethereum Wallet',
                                        'tx_count': len(txs),
                                        'first_tx_date': datetime.fromtimestamp(int(txs[0]['timeStamp'])).strftime('%Y-%m-%d') if txs else 'New',
                                        'last_tx_date': datetime.fromtimestamp(int(txs[-1]['timeStamp'])).strftime('%Y-%m-%d') if txs else 'None',
                                        'status': '✅ Verified' if txs else '🆕 New'
                                    })
                
                elif chain_type == 'TRX':
                    url = f'https://apilist.tronscan.org/api/account?address={address}'
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            if 'balances' in data:
                                wallet_info.update({
                                    'wallet_type': 'Tron Wallet (TRC-20)',
                                    'tx_count': data.get('totalTransactionCount', 0),
                                    'status': '✅ Verified' if data.get('totalTransactionCount', 0) > 0 else '🆕 New'
                                })
            
            except Exception as e:
                logger.debug(f"Wallet info error: {e}")
        
        return wallet_info

# --- Handler Functions ---
async def handle_address_command(event, role_key: str):
    """Handle /buyer and /seller commands"""
    try:
        user = await event.get_sender()
        user_id = user.id
        command = event.text.strip()
        
        logger.info(f"{Fore.CYAN}[{role_key.upper()}] Command from {user_id} ({user.username or user.first_name})")
        
        # Check if command has address
        if len(command.split()) < 2:
            prompt = TEXTS['BUYER_PROMPT'] if role_key == 'buyer' else TEXTS['SELLER_PROMPT']
            await event.reply(prompt, parse_mode='html')
            return
        
        address = command.split(maxsplit=1)[1].strip()
        logger.info(f"Address submitted: {address[:10]}...")
        
        # Step 1: Format validation
        msg = await event.reply(TEXTS['PROCESSING'], parse_mode='html')
        await asyncio.sleep(1.5)
        
        chain_type, chain_name = AdvancedAddressValidator.detect_format(address)
        
        if chain_type == 'UNKNOWN':
            logger.warning(f"Invalid format: {address}")
            await msg.edit(TEXTS['INVALID_FORMAT'].format(address=address), parse_mode='html')
            return
        
        logger.info(f"Format detected: {chain_type} - {chain_name}")
        
        # Step 2: Blockchain verification
        await msg.edit(TEXTS['VALIDATING'], parse_mode='html')
        await asyncio.sleep(2)
        
        # Load data
        roles = load_user_roles()
        addresses = load_addresses()
        
        # Find user's group and role
        user_group_id = None
        user_role_in_group = None
        
        for group_id, role_data in roles.items():
            for uid, data in role_data.items():
                if int(uid) == user_id:
                    user_group_id = group_id
                    user_role_in_group = data.get('role')
                    break
            if user_group_id:
                break
        
        if not user_group_id:
            logger.warning(f"No role found for user {user_id}")
            await msg.edit(TEXTS['NO_ROLE'], parse_mode='html')
            return
        
        # Check for duplicate role (user trying to be both buyer and seller)
        if user_role_in_group and user_role_in_group != role_key:
            logger.warning(f"Duplicate role attempt: {user_id} is {user_role_in_group}, trying to be {role_key}")
            
            # Get existing address
            group_addresses = addresses.get(user_group_id, {})
            existing_address = group_addresses.get(user_role_in_group, {}).get('address', 'Unknown')
            existing_chain = group_addresses.get(user_role_in_group, {}).get('chain', 'Unknown')
            
            await msg.edit(TEXTS['DUPLICATE_USER'].format(
                existing_role=user_role_in_group.capitalize(),
                existing_address=existing_address,
                existing_chain=existing_chain
            ), parse_mode='html')
            return
        
        # Check if address already set for this role in group
        group_addresses = addresses.get(user_group_id, {})
        if role_key in group_addresses:
            existing = group_addresses[role_key]
            if existing['user_id'] == user_id:
                logger.info(f"Address already set for {role_key} by {user_id}")
                
                user_mention = f"<a href='tg://user?id={user_id}'>{user.first_name}</a>"
                
                await msg.edit(TEXTS['ALREADY_SET'].format(
                    role=role_key.capitalize(),
                    address=existing['address'],
                    chain=existing['chain'],
                    user_mention=user_mention
                ), parse_mode='html')
                return
        
        # Verify address and get chain details
        final_chain = chain_name
        wallet_info = {}
        
        if chain_type == 'EVM':
            detected_chain, evm_info = await AdvancedAddressValidator.verify_evm_chain(address)
            final_chain = detected_chain
            wallet_info = await AdvancedAddressValidator.get_wallet_info(address, 'EVM')
        else:
            wallet_info = await AdvancedAddressValidator.get_wallet_info(address, chain_type)
        
        # Prepare wallet info text
        wallet_info_text = TEXTS['WALLET_INFO'].format(**wallet_info) if wallet_info.get('tx_count', 0) >= 0 else ""
        
        # Save address
        if user_group_id not in addresses:
            addresses[user_group_id] = {}
        
        addresses[user_group_id][role_key] = {
            'address': address,
            'chain': final_chain,
            'user_id': user_id,
            'username': user.username or user.first_name,
            'user_mention': f"<a href='tg://user?id={user_id}'>{user.first_name}</a>",
            'saved_at': time.time(),
            'saved_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'wallet_info': wallet_info,
            'status': wallet_info.get('status', '✅ Verified')
        }
        
        if save_addresses(addresses):
            logger.info(f"{Fore.GREEN}✓ {role_key.upper()} address saved: {address[:10]}... ({final_chain}) by {user_id}")
            
            user_mention = f"<a href='tg://user?id={user_id}'>{user.first_name}</a>"
            
            await msg.edit(TEXTS['SAVED'].format(
                role=role_key.capitalize(),
                address=address,
                chain=final_chain,
                user_mention=user_mention,
                status=wallet_info.get('status', '✅ Verified'),
                wallet_info=wallet_info_text
            ), parse_mode='html')
        else:
            logger.error(f"Failed to save address for {user_id}")
            await msg.edit("❌ <b>Database Error</b>\n\nFailed to save address. Please try again.", parse_mode='html')
        
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        try:
            await event.reply("❌ <b>Internal Error</b>\n\nPlease try again later.", parse_mode='html')
        except:
            pass

async def handle_view_addresses(event, client):
    """Handle /addresses command"""
    try:
        user = await event.get_sender()
        user_id = user.id
        
        logger.info(f"{Fore.YELLOW}[VIEW] Request from {user_id}")
        
        roles = load_user_roles()
        addresses = load_addresses()
        groups = load_groups()
        
        # Find user's group
        user_group_id = None
        for group_id, role_data in roles.items():
            if str(user_id) in role_data:
                user_group_id = group_id
                break
        
        if not user_group_id:
            await event.reply("❌ <b>No Active Session</b>\n\nYou're not part of any active escrow session.", parse_mode='html')
            return
        
        group_addresses = addresses.get(user_group_id, {})
        group_info = groups.get(user_group_id, {})
        group_name = group_info.get('name', f"Group {user_group_id}")
        
        if not group_addresses:
            await event.reply(TEXTS['NO_ADDRESSES'], parse_mode='html')
            return
        
        # Format addresses
        def format_address_info(role):
            data = group_addresses.get(role, {})
            if not data:
                return "❌ Not set", "...", "N/A", "Not set", "—"
            
            user_mention = data.get('user_mention', f"User {data.get('user_id', '?')}")
            address = data.get('address', '...')
            chain = data.get('chain', 'Unknown')
            status = data.get('status', '❓ Unknown')
            saved_date = data.get('saved_date', 'Unknown')
            
            return user_mention, address, chain, status, saved_date
        
        b_mention, b_addr, b_chain, b_status, b_date = format_address_info('buyer')
        s_mention, s_addr, s_chain, s_status, s_date = format_address_info('seller')
        
        last_updated = b_date if b_date != 'Unknown' else s_date
        
        await event.reply(TEXTS['VIEW_ADDRESSES'].format(
            group_name=group_name,
            buyer_mention=b_mention,
            buyer_address=b_addr,
            buyer_chain=b_chain,
            buyer_status=b_status,
            seller_mention=s_mention,
            seller_address=s_addr,
            seller_chain=s_chain,
            seller_status=s_status,
            last_updated=last_updated
        ), parse_mode='html', link_preview=False)
        
        logger.info(f"{Fore.GREEN}✓ Addresses viewed by {user_id}")
        
    except Exception as e:
        logger.error(f"View error: {e}")
        await event.reply("❌ <b>Error</b>\n\nFailed to retrieve addresses.", parse_mode='html')

def setup_address_handlers(client):
    """Setup Telegram event handlers"""
    
    @client.on(events.NewMessage(pattern=r'^/buyer(\s|$)'))
    async def buyer_handler(event):
        if event.is_private:
            await handle_address_command(event, 'buyer')
    
    @client.on(events.NewMessage(pattern=r'^/seller(\s|$)'))
    async def seller_handler(event):
        if event.is_private:
            await handle_address_command(event, 'seller')
    
    @client.on(events.NewMessage(pattern=r'^/addresses(\s|$)'))
    async def addresses_handler(event):
        if event.is_private:
            await handle_view_addresses(event, client)
    
    logger.info(f"{Fore.GREEN}✓ Address handlers registered successfully")

# --- Test Function ---
async def test_validator():
    """Test the validator with sample addresses"""
    test_addresses = [
        "0x742d35Cc6634C0532925a3b844Bc9e37F6d5Dc8B",  # ETH
        "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",  # BSC
        "TB7Q5J8Q3h8m8m2rZ8v8q3J8Q3h8m8m2rZ8v8q3J",  # TRX (fake)
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # BTC (Satoshi's)
        "LfmVYLt6qF2dgvmVtLzZ3wC17mZ3DdAq1Z",  # LTC
        "0x0000000000000000000000000000000000000000"  # Invalid
    ]
    
    validator = AdvancedAddressValidator()
    
    for addr in test_addresses:
        print(f"\n{Fore.CYAN}Testing: {addr}")
        chain_type, chain_name = validator.detect_format(addr)
        print(f"Detected: {chain_type} - {chain_name}")
        
        if chain_type != 'UNKNOWN':
            info = await validator.get_wallet_info(addr, chain_type)
            print(f"Info: {info}")

if __name__ == "__main__":
    # Run tests
    asyncio.run(test_validator())
