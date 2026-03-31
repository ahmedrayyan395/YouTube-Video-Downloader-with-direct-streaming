import os
# from dotenv import load_dotenv

# load_dotenv()

class Config:
    # SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    SECRET_KEY="MY_secret_key"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 * 1024  # 16GB max file size
    DOWNLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'downloads')
    ALLOWED_EXTENSIONS = {'mp4', 'webm', 'mkv'}
    
    # For future ad integration
    ENABLE_ADS = os.getenv('ENABLE_ADS', 'False').lower() == 'true'
    AD_PROVIDER = os.getenv('AD_PROVIDER', 'google')  # google, custom, etc.
    
    @staticmethod
    def init_download_folder():
        if not os.path.exists(Config.DOWNLOAD_FOLDER):
            os.makedirs(Config.DOWNLOAD_FOLDER)