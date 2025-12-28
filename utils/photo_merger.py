# utils/photo_merger.py
from PIL import Image, ImageDraw
import requests
from io import BytesIO
import json
import os

class PhotoMerger:
    def __init__(self, config_path="config/pfp_config.json", base_image_path="assets/base_start.png"):
        """Initialize photo merger with config"""
        self.config_path = config_path
        self.base_image_path = base_image_path
        
        # Load config
        self.config = self.load_config()
        
        # Check if assets exist
        self.check_assets()
    
    def load_config(self):
        """Load configuration from JSON file"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        else:
            # Default config
            return {
                "BUYER_PFP": {
                    "center_x": 470,
                    "center_y": 384,
                    "radius": 177
                },
                "SELLER_PFP": {
                    "center_x": 920,
                    "center_y": 384,
                    "radius": 177
                }
            }
    
    def check_assets(self):
        """Check if required assets exist"""
        if not os.path.exists(self.base_image_path):
            print(f"[WARNING] Base image not found: {self.base_image_path}")
            # Create a simple base image as fallback
            self.create_fallback_base_image()
    
    def create_fallback_base_image(self):
        """Create a fallback base image if the original is missing"""
        try:
            # Create a 1400x800 transparent base image
            base_img = Image.new('RGBA', (1400, 800), (255, 255, 255, 255))
            draw = ImageDraw.Draw(base_img)
            
            # Add some simple text
            draw.text((700, 400), "ESCROW SESSION", fill=(0, 0, 0, 255), anchor="mm")
            
            # Save it
            base_img.save(self.base_image_path)
            print(f"[INFO] Created fallback base image at {self.base_image_path}")
        except Exception as e:
            print(f"[ERROR] Could not create fallback image: {e}")
    
    def download_profile_picture(self, client, user_id, size=(400, 400)):
        """Download user's profile picture"""
        try:
            # Get user entity
            user = client.loop.run_until_complete(client.get_entity(user_id))
            
            # Download profile photo
            if user.photo:
                photo = client.loop.run_until_complete(client.download_profile_photo(
                    user,
                    file=BytesIO(),
                    download_big=True
                ))
                
                if photo:
                    # Open and resize the image
                    image = Image.open(BytesIO(photo))
                    image = image.resize(size, Image.Resampling.LANCZOS)
                    
                    # Convert to RGBA if needed
                    if image.mode != 'RGBA':
                        image = image.convert('RGBA')
                    
                    return image
            
            # If no profile photo, create a default one
            return self.create_default_pfp(user_id, size)
            
        except Exception as e:
            print(f"[ERROR] Downloading profile picture for {user_id}: {e}")
            return self.create_default_pfp(user_id, size)
    
    def create_default_pfp(self, user_id, size=(400, 400)):
        """Create a default profile picture with initials"""
        # Create a circle with random color based on user ID
        import hashlib
        
        # Generate color from user ID
        hash_obj = hashlib.md5(str(user_id).encode())
        hex_dig = hash_obj.hexdigest()
        color = tuple(int(hex_dig[i:i+2], 16) for i in (0, 2, 4))
        
        # Create image
        image = Image.new('RGBA', size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw circle
        center_x, center_y = size[0] // 2, size[1] // 2
        radius = min(center_x, center_y) - 10
        
        draw.ellipse(
            [(center_x - radius, center_y - radius),
             (center_x + radius, center_y + radius)],
            fill=color + (255,)
        )
        
        # Add user ID initials
        initials = f"U{user_id % 100:02d}"
        draw.text(
            (center_x, center_y),
            initials,
            fill=(255, 255, 255, 255),
            anchor="mm",
            font_size=60
        )
        
        return image
    
    def create_circular_mask(self, size, radius):
        """Create a circular mask"""
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        center_x, center_y = size[0] // 2, size[1] // 2
        draw.ellipse(
            [(center_x - radius, center_y - radius),
             (center_x + radius, center_y + radius)],
            fill=255
        )
        return mask
    
    def merge_photos(self, buyer_pfp, seller_pfp):
        """Merge profile pictures onto base image"""
        try:
            # Load base image
            base_img = Image.open(self.base_image_path).convert('RGBA')
            
            # Get coordinates from config
            buyer_config = self.config.get("BUYER_PFP", {})
            seller_config = self.config.get("SELLER_PFP", {})
            
            buyer_x = buyer_config.get("center_x", 470)
            buyer_y = buyer_config.get("center_y", 384)
            buyer_radius = buyer_config.get("radius", 177)
            
            seller_x = seller_config.get("center_x", 920)
            seller_y = seller_config.get("center_y", 384)
            seller_radius = seller_config.get("radius", 177)
            
            # Resize profile pictures to match circle diameters
            buyer_size = (buyer_radius * 2, buyer_radius * 2)
            seller_size = (seller_radius * 2, seller_radius * 2)
            
            buyer_pfp = buyer_pfp.resize(buyer_size, Image.Resampling.LANCZOS)
            seller_pfp = seller_pfp.resize(seller_size, Image.Resampling.LANCZOS)
            
            # Create circular masks
            buyer_mask = self.create_circular_mask(buyer_size, buyer_radius)
            seller_mask = self.create_circular_mask(seller_size, seller_radius)
            
            # Calculate positions (center to top-left)
            buyer_pos = (buyer_x - buyer_radius, buyer_y - buyer_radius)
            seller_pos = (seller_x - seller_radius, seller_y - seller_radius)
            
            # Paste buyer PFP
            base_img.paste(buyer_pfp, buyer_pos, buyer_mask)
            
            # Paste seller PFP
            base_img.paste(seller_pfp, seller_pos, seller_mask)
            
            return base_img
            
        except Exception as e:
            print(f"[ERROR] Merging photos: {e}")
            raise
    
    def generate_group_photo(self, client, buyer_id, seller_id):
        """Generate group photo with both profile pictures"""
        try:
            print(f"[PHOTO] Downloading profile pictures: Buyer={buyer_id}, Seller={seller_id}")
            
            # Download profile pictures
            buyer_pfp = self.download_profile_picture(client, buyer_id)
            seller_pfp = self.download_profile_picture(client, seller_id)
            
            # Merge onto base image
            merged_image = self.merge_photos(buyer_pfp, seller_pfp)
            
            # Convert to bytes
            img_bytes = BytesIO()
            merged_image.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            return True, img_bytes, "✅ Group photo generated with profile pictures"
            
        except Exception as e:
            return False, None, f"❌ Error generating group photo: {e}"
