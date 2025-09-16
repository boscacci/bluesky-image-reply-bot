# Bluesky Home Timeline - Posts with Images from Followed Users

A beautiful, modern Flask web application that fetches and displays posts with images from your Bluesky home timeline (followed users only). This application ensures you only see content from users you follow, providing a personalized and curated experience.

## 🚀 Key Features

- **Home Timeline Only**: Fetches posts exclusively from users you follow (not public timeline)
- **Image-Focused**: Displays posts with embedded images for visual content
- **Modern UI/UX**: Beautiful, responsive design with Bootstrap 5
- **Rate Limiting**: Built-in API rate limiting for security and performance
- **Security**: Comprehensive security measures including directory traversal protection
- **Real-time Status**: Live connection status and health monitoring
- **Configurable**: Adjustable post counts and user limits
- **Professional Logging**: Comprehensive logging for monitoring and debugging

## 🔧 Technical Improvements

### Backend Enhancements
- ✅ **Fixed Critical Issue**: Changed from public timeline to home timeline (followed users only)
- ✅ **Rate Limiting**: Added Flask-Limiter for API protection
- ✅ **Security**: Directory traversal protection and input validation
- ✅ **Logging**: Comprehensive logging with file and console output
- ✅ **Error Handling**: Robust error handling with proper HTTP status codes
- ✅ **Health Checks**: Added health check endpoint for monitoring
- ✅ **Parameter Validation**: Input validation for all API parameters

### Frontend Enhancements
- ✅ **Modern UI**: Enhanced with better loading animations and status indicators
- ✅ **Real-time Status**: Live connection status with color-coded indicators
- ✅ **Success/Error Messages**: User-friendly feedback messages
- ✅ **Responsive Design**: Mobile-friendly responsive layout
- ✅ **Accessibility**: Proper ARIA labels and semantic HTML

## 📁 Project Structure

```
vit-sandbox/
├── src/                    # Source code
│   ├── app.py             # Main Flask application
│   ├── config.py          # Configuration imports
│   ├── bluesky_bot/       # Bluesky bot implementation
│   ├── staged_vision_integration.py  # AI model integration
│   └── theme_config.py    # Theme configuration
├── tests/                  # Test files
│   ├── test_flask_app.py  # Flask app tests
│   ├── test_bluesky_bot.py # Bot tests
│   ├── test_model_caching.py # Model caching tests
│   └── test_cache_config.py # Cache config tests
├── static/                 # Static web assets
├── templates/              # HTML templates
├── docs/                   # Documentation
├── main.py                 # Main entry point
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd vit-sandbox
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   - Set up AWS SSM Parameter Store with your Bluesky password
   - Update `src/bluesky_bot/config.py` with your Bluesky handle
   - Configure AWS region and other settings as needed

4. **Run the application**
   ```bash
   python main.py
   ```

## 📡 API Endpoints

### `GET /api/posts`
Fetches posts with images from your home timeline (followed users only).

**Parameters:**
- `count` (int, 1-50): Number of posts to fetch (default: 5)
- `max_per_user` (int, 1-10): Maximum posts per user (default: 2)

**Response:**
```json
{
  "success": true,
  "posts": [...],
  "count": 5,
  "max_per_user": 2,
  "source": "home_timeline_followed_users_only"
}
```

### `GET /api/image/<filename>`
Serves images from the temporary directory with security checks.

### `GET /api/status`
Returns the current bot status and configuration.

### `GET /health`
Health check endpoint for monitoring.

## 🔒 Security Features

- **Rate Limiting**: 10 requests per minute for posts, 100 for images
- **Directory Traversal Protection**: Prevents access outside temp directory
- **Input Validation**: Validates all API parameters
- **Secure File Serving**: Multiple security checks for image serving
- **AWS SSM Integration**: Secure credential management

## 🎨 UI/UX Features

- **Status Indicators**: Real-time connection status with color coding
- **Loading Animations**: Modern loading spinners with progress bars
- **Success/Error Messages**: User-friendly feedback system
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Image Modal**: Click to view images in full-screen modal
- **Configurable Controls**: Adjust post counts and user limits

## 📊 Monitoring & Logging

- **Comprehensive Logging**: All operations logged to file and console
- **Health Checks**: Built-in health monitoring endpoint
- **Error Tracking**: Detailed error logging with context
- **Performance Metrics**: Request timing and success rates

## 🚀 Deployment

The application is production-ready with:
- Gunicorn WSGI server support
- Environment-based configuration
- Health check endpoints for load balancers
- Comprehensive error handling
- Security best practices

## 🔄 Recent Updates

### Version 2.0.0
- **CRITICAL FIX**: Changed from public timeline to home timeline (followed users only)
- Added rate limiting and security enhancements
- Improved UI/UX with modern design elements
- Added comprehensive logging and monitoring
- Enhanced error handling and validation
- Added health check endpoints

## 📝 Configuration

Key configuration options in `src/bluesky_bot/config.py`:

```python
# AWS Configuration
AWS_REGION = 'us-east-2'
SSM_PARAMETER_NAME = 'BLUESKY_PASSWORD_BIKELIFE'

# Bluesky Configuration
BLUESKY_HANDLE = 'your-handle.bsky.social'

# Flask Settings
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000
FLASK_DEBUG = True
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
1. Check the logs in `bluesky_app.log`
2. Verify your Bluesky credentials in AWS SSM
3. Ensure you're following users on Bluesky to see posts
4. Check the health endpoint: `/health`

---

**Made with ❤️ for the Bluesky community**