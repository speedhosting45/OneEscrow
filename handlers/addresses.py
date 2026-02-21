# handlers/addresses.py
"""
Address handlers for OneEscrow Bot
This is a plugin that integrates with the main bot
"""

import re
import json
import os
import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime
from telethon import events, Button

# Configure colorful logging
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors"""
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    green = "\x1b[38;5;40m"
    cyan = "\x1b[38;5;51m"
    magenta = "\x1b[38;5;201m"
    reset = "\x1b[0m"

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.grey + self.fmt + self.reset,
            logging.INFO: self.green + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%H:%M:%S')
        return formatter.format(record)

# Setup logger
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Data files
USER_ADDRESSES_FILE = os.path.join(BASE_DIR, 'data/user_addresses.json')
USER_ROLES_FILE = os.path.join(BASE_DIR, 'data/user_roles.json')
ACTIVE_GROUPS_FILE = os.path.join(BASE_DIR, 'data/active_groups.json')
MESSAGES_LOG_FILE = os.path.join(BASE_DIR, 'data/messages_log.json')

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
            'color': '\x1b[38;5;226m'  # Yellow
        },
        'ETH': {
            'name': 'Ethereum',
            'regex': r'^0x[a-fA-F0-9]{40}$',
            'explorer': 'https://etherscan.io/address/{address}',
            'color': '\x1b[38;5;105m'  # Light blue
        },
        'BSC': {
            'name': 'BNB Smart Chain',
            'regex': r'^0x[a-fA-F0-9]{40}$',
            'explorer': 'https://bscscan.com/address/{address}',
            'color': '\x1b[38;5;220m'  # Gold
        },
        'TRX': {
            'name': 'Tron',
            'regex': r'^T[a-zA-Z0-9]{33}$',
            'explorer': 'https://tronscan.org/#/address/{address}',
            'color': '\x1b[38;5;197m'  # Red
        },
        'LTC': {
            'name': 'Litecoin',
            'regex': r'^(ltc1|[LM])[a-zA-HJ-NP-Z0-9]{26,33}$',
            'explorer': 'https://blockchair.com/litecoin/address/{address}',
            'color': '\x1b[38;5;39m'  # Blue
        },
        'MATIC': {
            'name': 'Polygon',
            'regex': r'^0x[a-fA-F0-9]{40}$',
            'explorer': 'https://polygonscan.com/address/{address}',
            'color': '\x1b[38;5;129m'  # Purple
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
        
        logger.info(f"[ 🔍 ] Checking command: user={user_id}, wanted={command_role}, has={user_role}")
        
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

Please wait for admin to assign you a role using /begin command."""
    
    @staticmethod
    def address_saved_success(user_name: str, role: str, address: str, chain: str):
        return f"""✅ **{role.upper()} ADDRESS SAVED SUCCESSFULLY!**

**User:** {user_name}
**Role:** {role.upper()}
**Chain:** {chain}
**Address:** `{address}`

⚠️ *This address is now locked for this escrow session.*"""
    
    @staticmethod
    def group_notification(user_name: str, role: str, address: str, chain: str):
        message = f"""📢 **NEW {role.upper()} REGISTERED!**

**User:** {user_name}
**Chain:** {chain}
**Address:** `{address[:12]}...{address[-6:]}`

✅ Address verified and saved!"""
        
        return message
    
    @staticmethod
    def chain_mismatch(buyer_chain: str, seller_chain: str):
        return f"""❌ **CHAIN MISMATCH DETECTED!**

Buyer Chain: **{buyer_chain}**
Seller Chain: **{seller_chain}**

⚠️ **Both parties must use the same blockchain!**

Please coordinate and use the same chain."""
    
    @staticmethod
    def escrow_ready(group_name: str, buyer: Dict, seller: Dict, group_id: str):
        """Create escrow ready message"""
        
        message = f"""🎉 **ESCROW SETUP COMPLETE!**

**Group:** {group_name}
**Chain:** {buyer['chain_name']}
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
        
        return message

# ==================== ADDRESS HANDLER ====================
class AddressHandler:
    """Main address handler for buyer/seller commands"""
    
    def __init__(self, client):
        self.client = client
        self.validator = BlockchainValidator()
        logger.info("[ 📝 ] " + "="*50)
        logger.info("[ 📝 ] Address Handler initialized")
        logger.info("[ 📝 ] " + "="*50)
    
    def setup_handlers(self):
        """Setup command handlers"""
        
        @self.client.on(events.NewMessage(pattern=r'^/buyer(\s+|$)'))
        async def buyer_handler(event):
            await self.handle_address_command(event, 'buyer')
        
        @self.client.on(events.NewMessage(pattern=r'^/seller(\s+|$)'))
        async def seller_handler(event):
            await self.handle_address_command(event, 'seller')
        
        @self.client.on(events.NewMessage(pattern=r'^/addresses$'))
        async def addresses_handler(event):
            await self.show_addresses(event)
        
        logger.info("[ 📝 ] Address command handlers registered")
    
    async def handle_address_command(self, event, role: str):
        """Handle /buyer or /seller command"""
        try:
            user = await event.get_sender()
            chat = await event.get_chat()
            
            user_id = user.id
            chat_id = str(event.chat_id)
            
            # Color based on role
            role_color = '\x1b[38;5;51m' if role == 'buyer' else '\x1b[38;5;201m'
            logger.info(f"[ {role_color}{role.upper()}\x1b[0m ] Command from user {user_id} in chat {chat_id}")
            
            # Check if in group
            if not hasattr(chat, 'title'):
                await event.reply("❌ This command only works in groups!")
                return
            
            # Check user's role
            user_role = RoleManager.get_user_role(user_id, chat_id)
            
            if not user_role:
                await event.reply(MessageTemplates.no_role())
                logger.warning(f"[ ⚠️ ] User {user_id} has no role in chat {chat_id}")
                return
            
            if user_role != role:
                await event.reply(MessageTemplates.wrong_role(user_role, role))
                logger.warning(f"[ ⚠️ ] Role mismatch: user={user_role}, command={role}")
                return
            
            # Get address from command
            parts = event.text.split(maxsplit=1)
            if len(parts) < 2:
                await event.reply(f"Usage: /{role} [your_wallet_address]")
                logger.info(f"[ ℹ️ ] Missing address in /{role} command")
                return
            
            address = parts[1].strip()
            
            # Show processing message
            processing_msg = await event.reply(MessageTemplates.processing())
            
            # Validate address
            is_valid, chain_code, chain_name = await self.validator.verify_address(address)
            
            if not is_valid:
                await processing_msg.edit(MessageTemplates.invalid_format())
                logger.warning(f"[ ⚠️ ] Invalid address format from user {user_id}")
                return
            
            # Get chain color
            chain_color = BlockchainValidator.CHAINS.get(chain_code, {}).get('color', '\x1b[38;5;255m')
            logger.info(f"[ {chain_color}{chain_code}\x1b[0m ] Valid address from user {user_id}")
            
            # Check if user already has address saved
            addresses = load_json(USER_ADDRESSES_FILE, {})
            chat_addresses = addresses.get(chat_id, {})
            
            if role in chat_addresses and chat_addresses[role].get('user_id') == user_id:
                # User already has address saved
                await processing_msg.edit(
                    f"⚠️ **Address Already Set!**\n\n"
                    f"You already have a {role} address saved:\n"
                    f"`{chat_addresses[role]['address'][:16]}...{chat_addresses[role]['address'][-8:]}`\n"
                    f"**Chain:** {chat_addresses[role]['chain_name']}\n\n"
                    f"*Contact admin to change address.*"
                )
                logger.info(f"[ ℹ️ ] User {user_id} already has {role} address")
                return
            
            # Prepare address data
            address_data = {
                'user_id': user_id,
                'user_name': user.first_name or f"User_{user_id}",
                'address': address,
                'chain': chain_code,
                'chain_name': chain_name,
                'timestamp': time.time(),
                'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Save address
            if chat_id not in addresses:
                addresses[chat_id] = {}
            
            addresses[chat_id][role] = address_data
            save_json(USER_ADDRESSES_FILE, addresses)
            
            # Send success message to user
            await processing_msg.edit(
                MessageTemplates.address_saved_success(
                    user.first_name or f"User_{user_id}", 
                    role, 
                    address, 
                    chain_name
                ),
                link_preview=False
            )
            
            # Send notification to group
            await self.send_group_notification(chat, role, address_data)
            
            logger.info(f"[ ✅ ] {role.upper()} address saved for user {user_id} on {chain_code}")
            
            # Check if escrow is ready (both addresses set)
            await self.check_escrow_ready(chat)
            
        except Exception as e:
            logger.error(f"[ ❌ ] Error in handle_address_command: {e}", exc_info=True)
            try:
                await event.reply("❌ An error occurred. Please try again.")
            except:
                pass
    
    async def send_group_notification(self, chat, role: str, address_data: Dict):
        """Send notification to group"""
        try:
            message = MessageTemplates.group_notification(
                address_data['user_name'],
                role,
                address_data['address'],
                address_data['chain_name']
            )
            
            await self.client.send_message(
                chat.id,
                message,
                parse_mode='markdown'
            )
            
            logger.info(f"[ 📢 ] Group notification sent for {role}")
            
        except Exception as e:
            logger.error(f"[ ❌ ] Error sending group notification: {e}")
    
    async def show_addresses(self, event):
        """Show all addresses in the current chat"""
        try:
            chat = await event.get_chat()
            chat_id = str(event.chat_id)
            
            addresses = load_json(USER_ADDRESSES_FILE, {})
            chat_addresses = addresses.get(chat_id, {})
            
            if not chat_addresses:
                await event.reply("📭 No addresses saved in this group yet.")
                return
            
            message = f"**📋 Addresses in {chat.title}**\n\n"
            
            if 'buyer' in chat_addresses:
                buyer = chat_addresses['buyer']
                message += f"**Buyer:** {buyer['user_name']}\n"
                message += f"`{buyer['address'][:20]}...`\n"
                message += f"Chain: {buyer['chain_name']}\n\n"
            
            if 'seller' in chat_addresses:
                seller = chat_addresses['seller']
                message += f"**Seller:** {seller['user_name']}\n"
                message += f"`{seller['address'][:20]}...`\n"
                message += f"Chain: {seller['chain_name']}\n"
            
            await event.reply(message, parse_mode='markdown')
            
        except Exception as e:
            logger.error(f"[ ❌ ] Error showing addresses: {e}")
            await event.reply("❌ Error loading addresses.")
    
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
            
            logger.info(f"[ 🔍 ] Checking escrow for chat {chat.id}: buyer={buyer['chain']}, seller={seller['chain']}")
            
            # Check chain match
            if buyer['chain'] != seller['chain']:
                await self.client.send_message(
                    chat.id,
                    MessageTemplates.chain_mismatch(buyer['chain_name'], seller['chain_name']),
                    parse_mode='markdown'
                )
                logger.warning(f"[ ⚠️ ] Chain mismatch in chat {chat.id}: {buyer['chain']} vs {seller['chain']}")
                return
            
            # Send escrow ready message
            await self.send_escrow_ready(chat, buyer, seller)
            
        except Exception as e:
            logger.error(f"[ ❌ ] Error checking escrow ready: {e}")
    
    async def send_escrow_ready(self, chat, buyer: Dict, seller: Dict):
        """Send escrow ready message"""
        try:
            message = MessageTemplates.escrow_ready(
                chat.title,
                buyer,
                seller,
                str(chat.id)
            )
            
            await self.client.send_message(
                chat.id,
                message,
                parse_mode='markdown'
            )
            
            logger.info(f"[ 🎉 ] Escrow ready in {chat.title}")
            logger.info(f"[ 👤 ] Buyer: {buyer['user_name']} ({buyer['chain']})")
            logger.info(f"[ 👤 ] Seller: {seller['user_name']} ({seller['chain']})")
            
        except Exception as e:
            logger.error(f"[ ❌ ] Error sending escrow ready: {e}")

# ==================== MAIN EXPORT FUNCTION ====================
def setup_address_handlers(client):
    """
    Main function to setup address handlers
    This is what main.py imports and calls
    """
    try:
        # Create handler instance
        handler = AddressHandler(client)
        
        # Setup the handlers
        handler.setup_handlers()
        
        logger.info("[ ✅ ] " + "="*50)
        logger.info("[ ✅ ] Address handlers setup complete!")
        logger.info("[ ✅ ] Commands: /buyer, /seller, /addresses")
        logger.info("[ ✅ ] " + "="*50)
        
        return handler
        
    except Exception as e:
        logger.error(f"[ ❌ ] Failed to setup address handlers: {e}")
        raise

# For testing
if __name__ == "__main__":
    print("""
    📝 Address Handlers Module for OneEscrow Bot
    ==============================================
    
    This module exports:
    • setup_address_handlers(client) - Main function to setup handlers
    
    Commands added:
    • /buyer [address] - For buyers to set their wallet
    • /seller [address] - For sellers to set their wallet
    • /addresses - Show all addresses in current chat
    
    Features:
    • Colorful logging
    • Blockchain address validation
    • Role-based access control
    • Chain matching enforcement
    """)
