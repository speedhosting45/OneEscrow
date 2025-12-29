#!/usr/bin/env python3
"""
Profile Picture Logo Generator for Escrow Groups
"""
import json
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os

class PFPGenerator:
    def __init__(self, template_path="assets/tg1.png", font_path="assets/Skynight.otf"):
        self.config = {
            "BUYER": {
                "start_x": 568,
                "start_y": 476,
                "max_width": 240
            },
            "SELLER": {
                "start_x": 575,
                "start_y": 556,
                "max_width": 240
            }
        }
        self.font_size = 40
        self.font_path = font_path
        self.image_path = template_path
        self.baseline_fix = 5
        self.text_color = (0, 0, 0)  # BLACK
        self.font = None
        self.template = None
        
        # Ensure assets directory exists
        os.makedirs("assets", exist_ok=True)
        
    def load_resources(self):
        """Load font and template image"""
        try:
            # Check if files exist
            if not os.path.exists(self.font_path):
                print(f"[PFPGEN] Font file not found: {self.font_path}, using default")
                self.font = ImageFont.load_default()
            else:
                self.font = ImageFont.truetype(self.font_path, self.font_size)
            
            if not os.path.exists(self.image_path):
                return False, f"❌ Template image not found: {self.image_path}"
            
            self.template = Image.open(self.image_path)
            return True, "✅ Resources loaded"
        except Exception as e:
            return False, f"❌ Failed to load resources: {e}"
    
    def format_username(self, username, user_id):
        """Format username - if >15 chars, use user ID"""
        if len(username) > 15:
            # Use user ID if username is too long
            return f"ID: {user_id}"
        return username
    
    def generate_logo(self, buyer_username, buyer_user_id, seller_username, seller_user_id):
        """
        Generate logo with formatted usernames
        
        Args:
            buyer_username: Buyer display name
            buyer_user_id: Buyer Telegram ID
            seller_username: Seller display name  
            seller_user_id: Seller Telegram ID
            
        Returns:
            tuple: (success: bool, image_bytes: BytesIO or None, message: str)
        """
        if not self.font or not self.template:
            success, msg = self.load_resources()
            if not success:
                return False, None, msg
        
        try:
            # Create fresh copy of template
            img = self.template.copy()
            draw = ImageDraw.Draw(img)
            
            # Get coordinates from config
            buyer_x = self.config["BUYER"]["start_x"]
            buyer_y = self.config["BUYER"]["start_y"]
            seller_x = self.config["SELLER"]["start_x"]
            seller_y = self.config["SELLER"]["start_y"]
            
            # Format usernames
            buyer_display = self.format_username(buyer_username, buyer_user_id)
            seller_display = self.format_username(seller_username, seller_user_id)
            
            # Draw text with baseline fix
            draw.text(
                (buyer_x, buyer_y + self.baseline_fix),
                buyer_display,
                font=self.font,
                fill=self.text_color
            )
            
            draw.text(
                (seller_x, seller_y + self.baseline_fix),
                seller_display,
                font=self.font,
                fill=self.text_color
            )
            
            # Convert to bytes
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            return True, img_bytes, "✅ Logo generated successfully"
            
        except Exception as e:
            return False, None, f"❌ Error generating logo: {e}"
    
    def generate_and_save(self, buyer_username, buyer_user_id, seller_username, seller_user_id, output_path="generated_pfp_logo.png"):
        """Generate logo and save to file"""
        success, image_bytes, message = self.generate_logo(
            buyer_username, buyer_user_id, 
            seller_username, seller_user_id
        )
        
        if success:
            with open(output_path, "wb") as f:
                f.write(image_bytes.getvalue())
            return True, f"✅ Logo saved as {output_path}"
        else:
            return False, message
    
    def get_config_info(self):
        """Get formatted configuration info"""
        info = "📋 **Current Configuration:**\n"
        info += f"```json\n{json.dumps(self.config, indent=2)}\n```\n"
        info += f"**Font:** {self.font_path} ({self.font_size}px)\n"
        info += f"**Text Color:** BLACK (0,0,0)\n"
        info += f"**Baseline Fix:** {self.baseline_fix}px\n"
        info += f"**Template:** {self.image_path}\n"
        return info
    
    def update_config(self, new_config):
        """Update configuration"""
        try:
            # Validate config structure
            if "BUYER" not in new_config or "SELLER" not in new_config:
                return False, "❌ Invalid config format"
            
            # Update config
            self.config = new_config
            return True, "✅ Configuration updated"
        except Exception as e:
            return False, f"❌ Error updating config: {e}"
