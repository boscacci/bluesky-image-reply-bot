# Bluesky Timeline Web App

A beautiful Flask web application that displays your Bluesky timeline with embedded images in a modern, responsive interface.

## Features

- 🔐 Secure authentication using AWS SSM Parameter Store
- 📱 Beautiful web interface for viewing Bluesky posts
- 🖼️ Displays embedded images with metadata
- 📊 Shows engagement metrics (likes, reposts, replies)
- 🔗 Direct links to view posts on Bluesky
- 📱 Responsive design that works on all devices
- ⚡ Fast image loading with lazy loading
- 🎨 Modern UI with Bootstrap 5

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure AWS Credentials

Make sure you have AWS credentials configured:

```bash
aws configure
```

Or set environment variables:
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

### 3. Store Your Bluesky Password

Store your Bluesky password in AWS SSM Parameter Store:

```bash
aws ssm put-parameter \
    --name "BLUESKY_PASSWORD_BIKELIFE" \
    --value "your_bluesky_password" \
    --type "SecureString"
```

### 4. Configure Your Handle

Edit `src/bluesky_bot/config.py` and update the `BLUESKY_HANDLE` variable:

```python
BLUESKY_HANDLE = 'your-handle.bsky.social'
```

### 5. Run the Web App

Run the application:

```bash
python app.py
```

### 6. Open in Browser

Open your browser and go to: http://localhost:5000

## Usage

- **Refresh**: Click the refresh button or press Ctrl+R to load new posts
- **Post Count**: Select how many posts to fetch (5, 10, or 15)
- **View Images**: Click on any image to view it in full size
- **View on Bluesky**: Click "View on Bluesky" to open the original post
- **Responsive**: The app works great on desktop, tablet, and mobile

## API Endpoints

- `GET /` - Main web interface
- `GET /api/posts?count=N` - Fetch N posts with images
- `GET /api/image/<filename>` - Serve downloaded images
- `GET /api/status` - Check bot connection status

## Configuration

You can modify settings in `src/bluesky_bot/config.py`:

- `BLUESKY_HANDLE`: Your Bluesky handle
- `AWS_REGION`: AWS region for SSM
- `FLASK_HOST`: Host to bind the Flask app (default: 0.0.0.0)
- `FLASK_PORT`: Port to run the Flask app (default: 5000)
- `FLASK_DEBUG`: Enable debug mode (default: True)

## Production Deployment

For production deployment, use Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Security

- Passwords are stored securely in AWS SSM Parameter Store
- Images are downloaded to temporary directories
- No sensitive data is logged or stored permanently
- CORS is enabled for cross-origin requests

## Troubleshooting

### Common Issues

1. **Authentication Failed**: Check your Bluesky handle and password in AWS SSM
2. **No Images Found**: The app only shows posts with embedded images
3. **AWS Errors**: Ensure your AWS credentials are properly configured
4. **Port Already in Use**: Change the port in config.py or kill the process using port 5000

### Debug Mode

Enable debug mode in `config.py` for detailed error messages:

```python
FLASK_DEBUG = True
```

## Browser Compatibility

- Chrome/Chromium (recommended)
- Firefox
- Safari
- Edge

The app uses modern web standards and requires JavaScript to be enabled.
