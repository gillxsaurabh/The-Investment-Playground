# CogniCap - Trading Portfolio Dashboard

A web application to view your Zerodha Kite trading portfolio with a beautiful dashboard.

## 📋 Table of Contents
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [First Time Login](#first-time-login)
- [Features](#features)

## 📁 Project Structure

```
CogniCap/
├── backend/
│   ├── app.py              # Flask API server
│   ├── requirements.txt    # Python dependencies
│   └── access_token.json   # Stored access token
├── frontend/
│   └── cognicap-app/       # Angular application
├── config.py               # Configuration
├── kite_auth.py           # Authentication helper
├── main.py                # CLI application
├── setup.sh               # Initial setup script
├── start.sh               # Application startup script
└── .env                   # Environment variables
```

## 🔧 Prerequisites

Before running the application, ensure you have the following installed:

- **Python 3.8+** - [Download Python](https://www.python.org/downloads/)
- **Node.js 18+** and **npm** - [Download Node.js](https://nodejs.org/)
- **Zerodha trading account** with API access - [Get API Keys](https://kite.trade/)

## 📦 Installation

### First Time Setup

If you haven't set up the project yet, run the setup script:

```bash
chmod +x setup.sh
./setup.sh
```

This will install all backend and frontend dependencies.

### Manual Installation

If you prefer to install dependencies manually:

#### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python3 -m venv venv
```

3. Activate the virtual environment:
```bash
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

4. Install Python dependencies:
```bash
pip install -r requirements.txt
```

5. Return to project root:
```bash
cd ..
```

#### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend/cognicap-app
```

2. Install Node.js dependencies:
```bash
npm install
```

3. Return to project root:
```bash
cd ../..
```

## 🚀 Running the Application

### Option 1: Quick Start (Recommended)

Use the startup script to run both backend and frontend:

```bash
chmod +x start.sh
./start.sh
```

This will automatically:
- ✅ Activate the Python virtual environment
- ✅ Start the backend server on `http://localhost:5000`
- ✅ Start the frontend on `http://localhost:4200`

Press `Ctrl+C` to stop both servers.

### Option 2: Manual Start

Run backend and frontend in separate terminal windows:

#### Terminal 1 - Backend Server

1. Navigate to backend directory:
```bash
cd backend
```

2. Activate the virtual environment:
```bash
source venv/bin/activate
```
   You should see `(venv)` prefix in your terminal prompt.

3. Start the Flask server:
```bash
python3 app.py
```
   ✅ Backend server will start on `http://localhost:5000`

#### Terminal 2 - Frontend Application

1. Open a new terminal window

2. Navigate to frontend directory:
```bash
cd frontend/cognicap-app
```

3. Start the Angular development server:
```bash
npm start
```
   OR
```bash
ng serve
```
   ✅ Frontend will start on `http://localhost:4200`

4. Open your browser and visit: `http://localhost:4200`

### Stopping the Application

**If using start.sh:**
- Press `Ctrl+C` in the terminal

**If running manually:**
- Press `Ctrl+C` in each terminal window (backend and frontend)

## 🎯 First Time Login

1. **Open the application** in your browser:
   ```
   http://localhost:4200
   ```

2. **Get Zerodha Login URL:**
   - Click the **"Get Login URL"** button
   - A new window/tab will open with Zerodha login page

3. **Login with Zerodha:**
   - Enter your Zerodha user ID, password, and PIN
   - Complete the authentication

4. **Get Request Token:**
   - After successful login, you'll be redirected to a URL like:
   ```
   http://127.0.0.1/?request_token=XXXXXXXXXX&action=login&status=success
   ```
   - **Copy** the `request_token` value (the part after `request_token=` and before `&action`)

5. **Authenticate in CogniCap:**
   - Return to the CogniCap login page
   - Paste the request token in the input field
   - Click **"Login to Dashboard"**

6. **Access Your Dashboard:**
   - 🎉 You'll be redirected to your portfolio dashboard with live holdings!
   - Your token is saved for the trading day - no need to login again until the next trading day

## 📱 Using the Dashboard

Once logged in, you can:
- ✅ View **portfolio summary** (total investment, current value, P&L)
- ✅ See all your **holdings** with real-time prices
- ✅ Track **profit/loss** for each stock (absolute and percentage)
- ✅ **Refresh data** anytime for latest prices
- ✅ **Automatic token management** - saved for the trading day

## 🔌 API Endpoints

The backend provides the following REST API endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/auth/login-url` | Get Zerodha login URL |
| `POST` | `/api/auth/authenticate` | Authenticate with request token |
| `POST` | `/api/auth/verify` | Verify existing access token |
| `POST` | `/api/portfolio/holdings` | Get current holdings |
| `POST` | `/api/portfolio/positions` | Get open positions |
| `POST` | `/api/portfolio/summary` | Get portfolio summary |

## ✨ Features

- ✅ **Secure token-based authentication** with Zerodha Kite API
- ✅ **Daily token auto-save and reuse** - login once per day
- ✅ **Portfolio holdings view** with real-time data
- ✅ **Real-time P&L tracking** for all holdings
- ✅ **Responsive Material Design UI** using Angular Material
- ✅ **Protected routes** with Angular guards
- 📊 Beautiful charts and analytics (coming soon)
- 📈 Historical performance tracking (coming soon)

## 🔒 Security

- 🔐 API keys stored in `.env` file (not committed to git)
- 🔐 Access tokens saved locally and automatically refreshed
- 🔐 CORS enabled for secure frontend-backend communication
- 🔐 Token validation on each API request
- 🔐 Automatic token expiry handling

## 🛠️ Tech Stack

**Backend:**
- **Flask** - Python web framework
- **Flask-CORS** - Cross-origin resource sharing
- **KiteConnect** - Official Zerodha API client
- **Python-dotenv** - Environment variable management

**Frontend:**
- **Angular 18** - Modern web framework
- **Angular Material** - Material Design components
- **TypeScript** - Type-safe JavaScript
- **RxJS** - Reactive programming
- **SCSS** - Enhanced CSS

## 🐛 Troubleshooting

### Backend Issues

**Virtual environment not activated:**
```bash
cd backend
source venv/bin/activate  # You should see (venv) in prompt
```

**Port 5000 already in use:**
```bash
# Find and kill the process using port 5000
lsof -ti:5000 | xargs kill -9
```

**Missing dependencies:**
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend Issues

**Port 4200 already in use:**
```bash
# Kill the process using port 4200
lsof -ti:4200 | xargs kill -9
```

**Missing node modules:**
```bash
cd frontend/cognicap-app
npm install
```

**Angular CLI not found:**
```bash
npm install -g @angular/cli
```

### Authentication Issues

**Token expired or invalid:**
- Access tokens are valid only for the trading day
- Simply login again with a fresh request token
- The application will automatically save the new token

**Request token issues:**
- Request tokens expire quickly (few minutes)
- Get a fresh login URL and complete the process quickly
- Copy the entire token value correctly

## 📝 Notes

- Access tokens are valid only for the current trading day
- You'll need to re-authenticate at the start of each trading day
- Make sure both backend and frontend are running for the app to work
- Keep your API keys secure and never commit them to version control

## 📄 License

This project is for educational and personal use only.
