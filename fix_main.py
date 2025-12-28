# Add this code where the error was (around line 386)
    async def send_wallet_setup(self, chat, group_id, user_roles):
        """Send wallet setup message and update group photo"""
        try:
            # Find buyer and seller
            buyer = None
            seller = None
            
            for user_id, data in user_roles.items():
                if data.get("role") == "buyer" and not buyer:
                    buyer = data
                elif data.get("role") == "seller" and not seller:
                    seller = data
            
            if not buyer or not seller:
                return
            
            # Generate custom logo
            from utils.logo_generator import LogoGenerator
            
            generator = LogoGenerator()
            success, image_bytes, message = generator.generate_logo(
                buyer['name'],
                seller['name']
            )
            
            if success:
                # Upload as group photo
                await self.client.upload_profile_photo(
                    file=image_bytes,
                    video=None,
                    video_start_ts=None,
                    video_emoji_markup=None
                )
                
                await chat.send_message(
                    f"✅ **Group setup complete!**\n\n"
                    f"👤 **Buyer:** {buyer['name']}\n"
                    f"👤 **Seller:** {seller['name']}\n"
                    f"💰 **Wallet:** TON Wallet configured\n\n"
                    f"Group photo has been updated with custom logo.",
                    parse_mode='markdown'
                )
            else:
                await chat.send_message(f"❌ Error generating logo: {message}")
                
        except Exception as e:
            print(f"[ERROR] Wallet setup: {e}")
            await chat.send_message("❌ Error setting up wallet")
