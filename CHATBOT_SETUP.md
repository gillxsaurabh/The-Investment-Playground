# CogniCap - AI Chatbot Setup Guide

## 🤖 Setting Up the Gemini AI Chatbot

The chatbot is now integrated into the dashboard on the right side. Follow these steps to configure it:

### 1. Get Your Gemini API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the generated API key

### 2. Configure the Backend

**Option A: Using Environment Variables (Recommended)**

Create a `.env` file in the `backend/` directory:

```bash
cd backend
cp .env.example .env
```

Then edit the `.env` file and add your API key:

```bash
GEMINI_API_KEY=your_actual_api_key_here
```

**Option B: Direct Configuration**

Edit `backend/app.py` and replace the line:

```python
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
```

With:

```python
GEMINI_API_KEY = 'your_actual_api_key_here'
```

### 3. Install Required Dependencies

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

This will install the `google-generativeai` package needed for the chatbot.

### 4. Restart the Backend Server

If the backend is already running, restart it:

```bash
# Stop the current server (Ctrl+C)
# Then restart
python3 app.py
```

Or use the start script from the root directory:

```bash
./start.sh
```

### 5. Test the Chatbot

1. Login to your dashboard
2. Look for the chat widget on the bottom-right corner
3. Type a message and press Enter or click the send button
4. The AI assistant will respond to your queries

## 💬 Chatbot Features

- **Real-time conversation**: Ask questions about trading, stocks, or your portfolio
- **Conversation history**: Maintains context throughout the session
- **Minimizable**: Click the minimize button to hide/show the chat
- **Clear chat**: Click the refresh button to start a new conversation
- **Typing indicator**: Shows when the AI is thinking

## 🔧 Troubleshooting

### Error: "Gemini API key not configured"

This means the backend can't find your API key. Make sure:
- You've created the `.env` file in the `backend/` directory
- The API key is correctly set in the `.env` file
- You've restarted the backend server after adding the key

### Chat not responding

1. Check the browser console for errors (F12 → Console)
2. Verify the backend is running on port 5000
3. Check that your Gemini API key is valid and has not exceeded quota

### API Key Limits

Free tier Gemini API has rate limits:
- 60 requests per minute
- 1500 requests per day

If you exceed these, you'll need to wait or upgrade your plan.

## 🚀 Next Steps

The basic chatbot is now set up. Future enhancements will include:
- Integration with portfolio data
- Custom agents for specific tasks
- Voice input/output
- Multi-language support
