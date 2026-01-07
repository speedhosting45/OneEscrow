# address_handler.py
"""
Address Handler Plugin for OneEscrow Bot
Integrates with existing role system
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
from telethon import events, Button

# ==================== CONFIGURATION ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Use your existing data paths
USER_ADDRESSES_FILE = os.path.join(BASE_DIR, 'data/user_addresses.json')
USER_ROLES_FILE = os.path.join(BASE_DIR, 'data/user_roles.json')
ACTIVE_GROUPS_FILE = os.path.join(BASE_DIR, 'data/active_groups.json')
MESSAGES_LOG_FILE = os.path.join(BASE_DIR, 'data/messages_log.json')

# ==================== LOGGING ====================
logger = logging.getLogger(__name__)

# ==================== DATA MANAGEMENT ====================
def load_json(filepath: str, default=None):
    """Load JSON with error handling"""
    if default is None:
        default = {}
    
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
    
    return default

def save_json(filepath: str, data: Dict) -> bool:
    """Save JSON with directory creation"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Failed to save {filepath}: {e}")
        return False

# ==================== BLOCKCHAIN VALIDATOR ====================
class BlockchainValidator:
    """Blockchain address validator"""
    
    CHAINS = {
        'BTC': {
            'name': 'Bitcoin',
            'regex': r'^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,59}$',
            'explorer': 'https://blockchain.com/explorer/addresses/btc/{address}',
        },
        'ETH': {
            'name': 'Ethereum',
            'regex': r'^0x[a-fA-F0-9]{40}$',
            'explorer': 'https://etherscan.io/address/{address}',
        },
        'BSC': {
            'name': 'BNB Smart Chain',
            'regex': r'^0x[a-fA-F0-9]{40}$',
            'explorer': 'https://bscscan.com/address/{address}',
        },
        'TRX': {
            'name': 'Tron',
            'regex': r'^T[a-zA-Z0-9]{33}$',
            'explorer': 'https://tronscan.org/#/address/{address}',
        },
        'LTC': {
            'name': 'Litecoin',
            'regex': r'^(ltc1|[LM])[a-zA-HJ-NP-Z0-9]{26,33}$',
            'explorer': 'https://blockchair.com/litecoin/address/{address}',
        },
        'MATIC': {
            'name': 'Polygon',
            'regex': r'^0x[a-fA-F0-9]{40}$',
            'explorer': 'https://polygonscan.com/address/{address}',
        }
    }
    
    @staticmethod
    def detect_chain(address: str) -> Tuple[Optional[str], Optional[str]]:
        """Detect blockchain from address"""
        address = address.strip()
        
        for chain_code, config in BlockchainValidator.CHAINS.items():
            if re.match(config['regex'], address):
                return chain_code, config['name']
        
        return None, None
    
    @staticmethod
    async def verify_address(address: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Verify address and return (is_valid, chain_code, chain_name)"""
        chain_code, chain_name = BlockchainValidator.detect_chain(address)
        
        if not chain_code:
            return False, None, None
        
        # For EVM chains, we could add additional verification here
        # For now, just return the detected chain
        return True, chain_code, chain_name

# ==================== ROLE MANAGER ====================
class RoleManager:
    """Check user roles from existing data"""
    
    @staticmethod
    def get_user_role(user_id: int, group_id: str) -> Optional[str]:
        """Get user's role from existing user_roles.json"""
        try:
            roles = load_json(USER_ROLES_FILE, {})
            group_roles = roles.get(str(group_id), {})
            
            # Check if user has a role
            for uid, role_data in group_roles.items():
                if str(user_id) == uid:
                    return role_data.get('role')
            
            return None
        except Exception as e:
            logger.error(f"Error getting user role: {e}")
            return None
    
    @staticmethod
    def can_use_command(user_id: int, command_role: str, group_id: str) -> bool:
        """Check if user can use command based on their existing role"""
        user_role = RoleManager.get_user_role(user_id, group_id)
        
        # Debug logging
        logger.info(f"Checking command: user={user_id}, wanted={command_role}, has={user_role}")
        
        return user_role == command_role

# ==================== MESSAGE TEMPLATES ====================
class MessageTemplates:
    """Message templates for address handler"""
    
    @staticmethod
    def processing():
        return "🔍 **Processing your address...**"
    
    @staticmethod
    def invalid_format():
        return """❌ **Invalid Address Format!**

Please use a valid address format:
• **Bitcoin (BTC):** `1A1zP1...` or `bc1q...`
• **Ethereum (ETH):** `0x...`
• **BNB Chain (BSC):** `0x...`
• **Tron (TRX):** `T...`
• **Litecoin (LTC):** `L...` or `ltc1q...`
• **Polygon (MATIC):** `0x...`"""
    
    @staticmethod
    def wrong_role(user_role: str, command_role: str):
        return f"""⚠️ **Role Mismatch!**

You are registered as **{user_role.upper()}**, but trying to use **{command_role.upper()}** command.

Please use `/{"buyer" if user_role == "buyer" else "seller"}` instead."""
    
    @staticmethod
    def no_role():
        return """❌ **No Role Assigned!**

You don't have a role in this escrow session.

Please wait for admin to assign you a role (buyer or seller)."""
    
    @staticmethod
    def address_saved_success(user_name: str, role: str, address: str, chain: str):
        explorer = BlockchainValidator.CHAINS.get(chain, {}).get('explorer', '').format(address=address)
        
        return f"""✅ **{role.upper()} ADDRESS SAVED SUCCESSFULLY!**

**User:** {user_name}
**Role:** {role.upper()}
**Chain:** {chain}
**Address:** `{address}`

🔗 [View on Explorer]({explorer})

⚠️ *This address is now locked for this escrow session.*"""
    
    @staticmethod
    def group_notification(user_name: str, role: str, address: str, chain: str):
        explorer = BlockchainValidator.CHAINS.get(chain, {}).get('explorer', '').format(address=address)
        
        buttons = [
            [Button.url(f"🔗 {role.upper()} Wallet", explorer)],
            [Button.url("📊 Check Balance", f"https://debank.com/profile/{address}" if chain in ['ETH', 'BSC', 'MATIC'] else explorer)]
        ]
        
        message = f"""📢 **NEW {role.upper()} REGISTERED!**

**User:** {user_name}
**Chain:** {chain}
**Address:** `{address[:12]}...{address[-6:]}`

✅ Address verified and saved!"""
        
        return message, buttons
    
    @staticmethod
    def chain_mismatch(buyer_chain: str, seller_chain: str):
        return f"""❌ **CHAIN MISMATCH DETECTED!**

Buyer Chain: **{buyer_chain}**
Seller Chain: **{seller_chain}**

⚠️ **Both parties must use the same blockchain!**

Please coordinate and use the same chain."""
    
    @staticmethod
    def escrow_ready(group_name: str, buyer: Dict, seller: Dict, buyer_msg_id: int, seller_msg_id: int, group_id: str):
        """Create escrow ready message with inline buttons"""
        
        # Create message links
        if str(group_id).startswith('-100'):
            # Supergroup format
            buyer_link = f"https://t.me/c/{group_id[4:]}/{buyer_msg_id}"
            seller_link = f"https://t.me/c/{group_id[4:]}/{seller_msg_id}"
        else:
            # Regular group format
            buyer_link = f"https://t.me/c/{group_id}/{buyer_msg_id}"
            seller_link = f"https://t.me/c/{group_id}/{seller_msg_id}"
        
        # Get explorers
        buyer_explorer = BlockchainValidator.CHAINS.get(buyer['chain'], {}).get('explorer', '').format(address=buyer['address'])
        seller_explorer = BlockchainValidator.CHAINS.get(seller['chain'], {}).get('explorer', '').format(address=seller['address'])
        
        # Create buttons
        buttons = [
            [
                Button.url(f"👤 {buyer['user_name']}'s Wallet", buyer_explorer),
                Button.url("📋 Buyer Post", buyer_link)
            ],
            [
                Button.url(f"👤 {seller['user_name']}'s Wallet", seller_explorer),
                Button.url("📋 Seller Post", seller_link)
            ]
        ]
        
        message = f"""🎉 **ESCROW SETUP COMPLETE!**

**Group:** {group_name}
**Chain:** {buyer['chain']}
**Status:** ✅ Ready for Transaction

👥 **Participants:**
• **Buyer:** {buyer['user_name']}
  `{buyer['address'][:12]}...{buyer['address'][-6:]}`
  
• **Seller:** {seller['user_name']}
  `{seller['address'][:12]}...{seller['address'][-6:]}`

✅ **Verification Complete:**
✓ Both addresses verified
✓ Same blockchain network
✓ Ready for deposit

⚠️ **Next Steps:**
1. Buyer sends payment
2. Seller confirms delivery
3. Funds released

⏰ **Auto-confirm in 24h if no disputes.**"""
        
        return message, buttons

# ==================== ADDRESS HANDLER ====================
class AddressHandler:
    """Main address handler for buyer/seller commands"""
    
    def __init__(self, client):
        self.client = client
        self.validator = BlockchainValidator()
        self.setup_handlers()
        logger.info("✅ Address Handler loaded")
    
    def setup_handlers(self):
        """Setup command handlers"""
        
        @self.client.on(events.NewMessage(pattern=r'^/buyer(\s+|$)'))
        async def buyer_handler(event):
            await self.handle_address_command(event, 'buyer')
        
        @self.client.on(events.NewMessage(pattern=r'^/seller(\s+|$)'))
        async def seller_handler(event):
            await self.handle_address_command(event, 'seller')
    
    async def handle_address_command(self, event, role: str):
        """Handle /buyer or /seller command"""
        try:
            user = await event.get_sender()
            chat = await event.get_chat()
            
            user_id = user.id
            chat_id = event.chat_id
            
            logger.info(f"Received /{role} from user {user_id} in chat {chat_id}")
            
            # Check if in group
            if not hasattr(chat, 'title'):
                await event.reply("❌ This command only works in groups!")
                return
            
            # Check user's role
            user_role = RoleManager.get_user_role(user_id, str(chat_id))
            
            if not user_role:
                await event.reply(MessageTemplates.no_role())
                return
            
            if user_role != role:
                await event.reply(MessageTemplates.wrong_role(user_role, role))
                return
            
            # Get address from command
            parts = event.text.split(maxsplit=1)
            if len(parts) < 2:
                await event.reply(f"Usage: /{role} [your_wallet_address]")
                return
            
            address = parts[1].strip()
            
            # Show processing message
            processing_msg = await event.reply(MessageTemplates.processing())
            
            # Validate address
            is_valid, chain_code, chain_name = await self.validator.verify_address(address)
            
            if not is_valid:
                await processing_msg.edit(MessageTemplates.invalid_format())
                return
            
            logger.info(f"Address validated: {chain_code} - {chain_name}")
            
            # Check if user already has address saved
            addresses = load_json(USER_ADDRESSES_FILE, {})
            chat_addresses = addresses.get(str(chat_id), {})
            
            if role in chat_addresses and chat_addresses[role].get('user_id') == user_id:
                # User already has address saved
                await processing_msg.edit(
                    f"⚠️ **Address Already Set!**\n\n"
                    f"You already have a {role} address saved:\n"
                    f"`{chat_addresses[role]['address'][:16]}...{chat_addresses[role]['address'][-8:]}`\n"
                    f"**Chain:** {chat_addresses[role]['chain']}\n\n"
                    f"*Contact admin to change address.*"
                )
                return
            
            # Prepare address data
            address_data = {
                'user_id': user_id,
                'user_name': user.first_name,
                'address': address,
                'chain': chain_code,
                'chain_name': chain_name,
                'timestamp': time.time(),
                'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Save address
            if str(chat_id) not in addresses:
                addresses[str(chat_id)] = {}
            
            addresses[str(chat_id)][role] = address_data
            save_json(USER_ADDRESSES_FILE, addresses)
            
            # Send success message to user
            await processing_msg.edit(
                MessageTemplates.address_saved_success(
                    user.first_name, role, address, chain_name
                ),
                link_preview=False
            )
            
            # Send notification to group
            group_msg_id = await self.send_group_notification(chat, role, address_data)
            
            # Save message info for linking
            self.save_message_info(str(chat_id), role, group_msg_id, user_id, address)
            
            # Check if escrow is ready (both addresses set)
            await self.check_escrow_ready(chat)
            
        except Exception as e:
            logger.error(f"Error in handle_address_command: {e}", exc_info=True)
            try:
                await event.reply("❌ An error occurred. Please try again.")
            except:
                pass
    
    async def send_group_notification(self, chat, role: str, address_data: Dict) -> Optional[int]:
        """Send notification to group and return message ID"""
        try:
            message, buttons = MessageTemplates.group_notification(
                address_data['user_name'],
                role,
                address_data['address'],
                address_data['chain_name']
            )
            
            sent_msg = await self.client.send_message(
                chat.id,
                message,
                buttons=buttons,
                parse_mode='markdown'
            )
            
            logger.info(f"Group notification sent for {role}")
            return sent_msg.id
            
        except Exception as e:
            logger.error(f"Error sending group notification: {e}")
            return None
    
    def save_message_info(self, chat_id: str, role: str, message_id: int, user_id: int, address: str):
        """Save message info for later linking"""
        try:
            messages = load_json(MESSAGES_LOG_FILE, {})
            
            if chat_id not in messages:
                messages[chat_id] = {}
            
            messages[chat_id][role] = {
                'message_id': message_id,
                'user_id': user_id,
                'address': address,
                'timestamp': time.time()
            }
            
            save_json(MESSAGES_LOG_FILE, messages)
            
        except Exception as e:
            logger.error(f"Error saving message info: {e}")
    
    async def check_escrow_ready(self, chat):
        """Check if both buyer and seller addresses are set"""
        try:
            addresses = load_json(USER_ADDRESSES_FILE, {})
            chat_addresses = addresses.get(str(chat.id), {})
            
            # Check if both addresses exist
            if 'buyer' not in chat_addresses or 'seller' not in chat_addresses:
                return
            
            buyer = chat_addresses['buyer']
            seller = chat_addresses['seller']
            
            logger.info(f"Checking escrow for chat {chat.id}: buyer={buyer['chain']}, seller={seller['chain']}")
            
            # Check chain match
            if buyer['chain'] != seller['chain']:
                await self.client.send_message(
                    chat.id,
                    MessageTemplates.chain_mismatch(buyer['chain_name'], seller['chain_name']),
                    parse_mode='markdown'
                )
                return
            
            # Get message IDs
            messages = load_json(MESSAGES_LOG_FILE, {})
            chat_messages = messages.get(str(chat.id), {})
            
            buyer_msg_id = chat_messages.get('buyer', {}).get('message_id')
            seller_msg_id = chat_messages.get('seller', {}).get('message_id')
            
            # Send escrow ready message
            await self.send_escrow_ready(
                chat, buyer, seller, buyer_msg_id, seller_msg_id
            )
            
        except Exception as e:
            logger.error(f"Error checking escrow ready: {e}")
    
    async def send_escrow_ready(self, chat, buyer: Dict, seller: Dict, buyer_msg_id: int, seller_msg_id: int):
        """Send escrow ready message with inline buttons"""
        try:
            message, buttons = MessageTemplates.escrow_ready(
                chat.title,
                buyer,
                seller,
                buyer_msg_id,
                seller_msg_id,
                str(chat.id)
            )
            
            await self.client.send_message(
                chat.id,
                message,
                buttons=buttons,
                parse_mode='markdown'
            )
            
            logger.info(f"Escrow ready message sent for {chat.title}")
            
        except Exception as e:
            logger.error(f"Error sending escrow ready: {e}")

# ==================== PLUGIN LOADER ====================
def load_plugin(client):
    """
    Load the address handler plugin into your existing bot
    
    Usage in main.py:
        from address_handler import load_plugin
        load_plugin(client)
    """
    try:
        handler = AddressHandler(client)
        logger.info("🚀 Address Handler Plugin loaded successfully!")
        return handler
    except Exception as e:
        logger.error(f"Failed to load address handler plugin: {e}")
        raise

# ==================== INTEGRATION GUIDE ====================
"""
HOW TO INTEGRATE WITH YOUR EXISTING BOT:

1. Save this file as 'address_handler.py' in your bot directory

2. In your main.py, add:

# At the top with other imports
from address_handler import load_plugin

# After creating your client, load the plugin
client = TelegramClient(...)
load_plugin(client)

3. That's it! The plugin will automatically:
   - Read roles from your existing user_roles.json
   - Save addresses to user_addresses.json
   - Send group notifications
   - Check chain matching
   - Send final escrow ready message

The plugin uses your existing data structure:
• user_roles.json - for checking user permissions
• user_addresses.json - for storing wallet addresses
• messages_log.json - for storing message IDs for linking

Commands available:
• /buyer [address] - Only for users with 'buyer' role
• /seller [address] - Only for users with 'seller' role

Features:
✅ Role-based command access (reads from your existing roles)
✅ Address validation for multiple blockchains
✅ Group notifications with wallet explorer links
✅ Chain matching enforcement
✅ Message linking in final success message
✅ Inline buttons for easy navigation
✅ Integration with your existing data files
"""

# Simple test
if __name__ == "__main__":
    print("""
    🔌 Address Handler Plugin for OneEscrow Bot
    ==============================================
    
    This plugin adds /buyer and /seller commands that:
    1. Check user's role from existing user_roles.json
    2. Validate wallet addresses
    3. Send group notifications
    4. Check chain matching
    5. Send final escrow ready message with inline buttons
    
    To use:
    1. Save as address_handler.py
    2. In main.py: from address_handler import load_plugin
    3. After client creation: load_plugin(client)
    
    No changes needed to your existing role system!
    """)
