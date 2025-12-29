#!/usr/bin/env python3
"""
Address Handler for Escrow Bot - V2 API Fixed & Optimized
"""
import re
import json
import os
import logging
import time
import asyncio
import aiohttp
from telethon import events

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
USER_ADDRESSES_FILE = 'data/user_addresses.json'
USER_ROLES_FILE = 'data/user_roles.json'
ACTIVE_GROUPS_FILE = 'data/active_groups.json'

# --- Configuration ---
# NOTE: Etherscan V2 uses a single API key for all EVM chains (ETH, BSC, Polygon, etc.)
# You should generate a new key from https://etherscan.io/myapikey if your old ones fail.
API_KEYS = {
    'evm_unified': os.getenv('ETHERSCAN_API_KEY', 'DFPIRXHE54RBAZP9NIMYE3V5Z5K9U4Y126'),
    'blockcypher': os.getenv('BLOCKCYPHER_API_KEY', '7434a8ddf7244987b413e22353d3e266')
}

# Fallback text constants if utils.texts is missing
try:
    from utils.texts import (
        BUYER_ADDRESS_PROMPT, SELLER_ADDRESS_PROMPT,
        ADDRESS_SAVED, INVALID_ADDRESS,
        NO_ROLE, ADDRESS_ALREADY_SET,
        ADDRESSES_VIEW, NO_ADDRESSES_SET,
        ADDRESS_VERIFICATION_FAILED
    )
except ImportError:
    BUYER_ADDRESS_PROMPT = "Please send your Buyer address."
    SELLER_ADDRESS_PROMPT = "Please send your Seller address."
    ADDRESS_SAVED = "✅ <b>{role} Address Saved!</b>\n\nAddress: <code>{address}</code>\nNetwork: <b>{chain}</b>\nUser: {user_mention}"
    INVALID_ADDRESS = "❌ <b>Invalid Address Format</b>\nThe address <code>{address}</code> is not a valid crypto address."
    NO_ROLE = "❌ You do not have the required role for this command."
    ADDRESS_ALREADY_SET = "⚠️ <b>{role} Address Already Set</b>\n\nCurrent: <code>{address}</code>"
    ADDRESSES_VIEW = "📋 <b>Escrow Addresses ({group_name})</b>\n\n<b>Buyer:</b> {buyer_mention}\n<code>{buyer_address}</code> ({buyer_chain})\n\n<b>Seller:</b> {seller_mention}\n<code>{seller_address}</code> ({seller_chain})"
    NO_ADDRESSES_SET = "❌ No addresses set for this group yet."
    ADDRESS_VERIFICATION_FAILED = "⚠️ <b>Verification Failed</b>\nAddress <code>{address}</code> could not be verified on {chain}."

# ----------------- DATA MANAGEMENT -----------------

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def load_addresses(): return load_json(USER_ADDRESSES_FILE)
def save_addresses(data): save_json(USER_ADDRESSES_FILE, data)
def load_user_roles(): return load_json(USER_ROLES_FILE)
def load_groups(): return load_json(ACTIVE_GROUPS_FILE)

# ----------------- VALIDATION LOGIC -----------------

class AddressValidator:
    """
    Advanced Cryptocurrency Address Validator
    Uses Etherscan V2 Unified API for robust EVM detection.
    """
    
    PATTERNS = {
        'EVM': r'^0x[a-fA-F0-9]{40}$', 
        'TRX': r'^T[0-9a-zA-Z]{33}$',
        'BTC': [r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$', r'^bc1[ac-hj-np-z02-9]{11,71}$'],
        'LTC': [r'^[LM][a-km-zA-HJ-NP-Z1-9]{26,33}$', r'^ltc1[ac-hj-np-z02-9]{11,71}$']
    }
    
    @staticmethod
    def validate_format(address: str) -> str:
        address = address.strip()
        if re.match(AddressValidator.PATTERNS['EVM'], address): return 'EVM'
        if re.match(AddressValidator.PATTERNS['TRX'], address): return 'TRX'
        for p in AddressValidator.PATTERNS['BTC']:
            if re.match(p, address): return 'BTC'
        for p in AddressValidator.PATTERNS['LTC']:
            if re.match(p, address): return 'LTC'
        return 'Unknown'

    @staticmethod
    async def get_evm_stats(session, address, chain_name):
        """
        Fetches stats using Etherscan V2 Unified API.
        Chain IDs: ETH=1, BSC=56
        """
        # unified V2 endpoint
        url = 'https://api.etherscan.io/v2/api'
        
        chain_id = '1' if chain_name == 'ETH' else '56'
        
        params = {
            'chainid': chain_id,
            'module': 'proxy',
            'action': 'eth_getTransactionCount',
            'address': address,
            'tag': 'latest',
            'apikey': API_KEYS['evm_unified']
        }

        try:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # ERROR HANDLING FIX: Check if result is actual hex or an error string
                    result = data.get('result', '')
                    
                    # If the API returns a text error (like "Invalid API Key"), it won't start with 0x
                    if not isinstance(result, str) or not result.startswith('0x'):
                        logger.warning(f"API V2 Error for {chain_name}: {result}")
                        return 0, False, False

                    # Safe conversion
                    count = int(result, 16)
                    
                    # Check for contract code
                    code_params = params.copy()
                    code_params['action'] = 'eth_getCode'
                    
                    async with session.get(url, params=code_params, timeout=10) as code_resp:
                        if code_resp.status == 200:
                            code_data = await code_resp.json()
                            code_res = code_data.get('result', '0x')
                            is_contract = len(code_res) > 2 if (isinstance(code_res, str) and code_res.startswith('0x')) else False
                            return count, is_contract, True
                            
        except Exception as e:
            logger.warning(f"Exception checking stats for {chain_name}: {e}")
            
        return 0, False, False

    @staticmethod
    async def smart_detect_chain(address: str, detected_type: str) -> tuple:
        async with aiohttp.ClientSession() as session:
            
            # --- HANDLE EVM (ETH / BSC) ---
            if detected_type == 'EVM':
                eth_task = AddressValidator.get_evm_stats(session, address, 'ETH')
                bsc_task = AddressValidator.get_evm_stats(session, address, 'BSC')
                
                results = await asyncio.gather(eth_task, bsc_task)
                (eth_txs, eth_is_contract, eth_ok), (bsc_txs, bsc_is_contract, bsc_ok) = results
                
                warning = None
                if eth_is_contract or bsc_is_contract:
                    warning = "⚠️ <b>Warning:</b> Contract Address detected. Do not send tokens unless sure."

                # Decision Logic
                if eth_txs > 0 and bsc_txs == 0:
                    return True, 'ETH (ERC20)', warning
                elif bsc_txs > 0 and eth_txs == 0:
                    return True, 'USDT (BEP20)', warning
                elif eth_txs > 0 and bsc_txs > 0:
                    if bsc_txs >= eth_txs:
                         return True, 'USDT (BEP20)', f"{warning or ''}\nℹ️ <i>Active on both. Selected BSC (Higher usage).</i>"
                    else:
                         return True, 'ETH (ERC20)', f"{warning or ''}\nℹ️ <i>Active on both. Selected ETH (Higher usage).</i>"
                elif eth_ok or bsc_ok:
                    # Valid format, no txs (Fresh wallet) - Default to BEP20
                    return True, 'USDT (BEP20/ERC20)', "ℹ️ <i>New wallet (0 txs).</i>"
                else:
                    # If APIs failed entirely, still accept valid format but warn
                    return True, 'EVM (Unverified)', "⚠️ <i>API unreachable, format valid.</i>"

            # --- HANDLE TRON ---
            elif detected_type == 'TRX':
                url = f'https://apilist.tronscan.org/api/account?address={address}'
                try:
                    async with session.get(url, timeout=10) as resp:
                        data = await resp.json()
                        if 'balances' in data or 'bandwidth' in data:
                            return True, 'USDT (TRC20)', None
                except:
                    return True, 'USDT (TRC20)', "⚠️ API Verification skipped"

            # --- HANDLE BTC ---
            elif detected_type == 'BTC':
                url = f'https://blockchain.info/rawaddr/{address}?limit=0'
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200: return True, 'BTC', None
                except:
                    return True, 'BTC', "⚠️ API Verification skipped"

            # --- HANDLE LTC ---
            elif detected_type == 'LTC':
                url = f'https://api.blockcypher.com/v1/ltc/main/addrs/{address}/balance'
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200: return True, 'LTC', None
                except:
                    return True, 'LTC', "⚠️ API Verification skipped"

        return False, 'Unknown', None

# ----------------- HANDLERS -----------------

async def handle_address_command(event, role_key):
    try:
        user = await event.get_sender()
        text = event.text.strip()
        
        if len(text.split()) < 2:
            prompt = BUYER_ADDRESS_PROMPT if role_key == 'buyer' else SELLER_ADDRESS_PROMPT
            await event.reply(prompt, parse_mode='html')
            return
            
        address = text.split(maxsplit=1)[1].strip()
        detected_type = AddressValidator.validate_format(address)
        
        if detected_type == 'Unknown':
            await event.reply(INVALID_ADDRESS.format(address=address), parse_mode='html')
            return
            
        msg = await event.reply("🔍 <i>Verifying address...</i>", parse_mode='html')
        is_valid, final_chain, warning = await AddressValidator.smart_detect_chain(address, detected_type)
        
        if not is_valid:
            await msg.edit(ADDRESS_VERIFICATION_FAILED.format(address=address, chain=detected_type))
            return

        roles = load_user_roles()
        user_has_role = False
        user_role_data = None
        group_id = None
        
        for gid, role_data in roles.items():
            for uid, data in role_data.items():
                if int(uid) == user.id and data.get('role') == role_key:
                    user_has_role = True
                    user_role_data = data
                    group_id = gid
                    break
            if user_has_role: break
            
        if not user_has_role:
            await msg.edit(NO_ROLE)
            return

        addresses = load_addresses()
        if group_id not in addresses:
            addresses[group_id] = {}
            
        addresses[group_id][role_key] = {
            'address': address,
            'chain': final_chain,
            'user_id': user.id,
            'username': user.username or user.first_name,
            'saved_at': time.time()
        }
        save_addresses(addresses)
        
        response_text = ADDRESS_SAVED.format(
            role=role_key.capitalize(),
            address=address,
            chain=final_chain,
            user_mention=f"<a href='tg://user?id={user.id}'>{user_role_data['name']}</a>"
        )
        if warning: response_text += f"\n\n{warning}"
            
        await msg.edit(response_text, parse_mode='html')
        logger.info(f"{role_key} saved: {address} ({final_chain})")

    except Exception as e:
        logger.error(f"Handler Error: {e}", exc_info=True)
        await event.reply("❌ Error saving address.", parse_mode='html')

async def handle_view_addresses(event, client):
    try:
        user = await event.get_sender()
        roles = load_user_roles()
        addresses = load_addresses()
        groups = load_groups()
        
        user_group_id = None
        for group_id, role_data in roles.items():
            if str(user.id) in role_data:
                user_group_id = group_id
                break
                
        if not user_group_id:
            await event.reply("❌ No active escrow session.", parse_mode='html')
            return
            
        group_addresses = addresses.get(user_group_id, {})
        group_name = groups.get(user_group_id, {}).get('name', 'Unknown Group')
        
        if not group_addresses:
            await event.reply(NO_ADDRESSES_SET, parse_mode='html')
            return
            
        def fmt(key):
            d = group_addresses.get(key)
            if not d: return "❌ Not set", "...", "N/A"
            return (f"<a href='tg://user?id={d['user_id']}'>{d['username']}</a>", d['address'], d['chain'])

        b_m, b_a, b_c = fmt('buyer')
        s_m, s_a, s_c = fmt('seller')
        
        await event.reply(ADDRESSES_VIEW.format(
            group_name=group_name,
            buyer_mention=b_m, buyer_address=b_a, buyer_chain=b_c,
            seller_mention=s_m, seller_address=s_a, seller_chain=s_c
        ), parse_mode='html', link_preview=False)
        
    except Exception as e:
        logger.error(f"View Error: {e}")
        await event.reply("❌ Error retrieving addresses.")

def setup_address_handlers(client):
    @client.on(events.NewMessage(pattern=r'^/buyer(\s|$)'))
    async def b(e): await handle_address_command(e, 'buyer')
    
    @client.on(events.NewMessage(pattern=r'^/seller(\s|$)'))
    async def s(e): await handle_address_command(e, 'seller')
    
    @client.on(events.NewMessage(pattern=r'^/addresses(\s|$)'))
    async def v(e): await handle_view_addresses(e, client)
