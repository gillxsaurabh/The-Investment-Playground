# CogniCap - Quick Start Guide

## 1. Run the Application

```bash
./start.sh
```

## 2. Login

1. Open browser: http://localhost:4200
2. Click "Get Login URL"
3. Login to Zerodha (new window)
4. Copy `request_token` from URL
5. Paste and click "Login to Dashboard"

## 3. View Your Portfolio

You'll see:
- 💰 Total Investment
- 📈 Current Value
- ✅ Total P&L
- 📦 All Holdings

## Troubleshooting

### Backend won't start
```bash
cd backend
source venv/bin/activate
python3 app.py
```

### Frontend won't start
```bash
cd frontend/cognicap-app
npm install
npm start
```

### Port already in use
Kill the process:
```bash
# For port 5000 (backend)
lsof -ti:5000 | xargs kill -9

# For port 4200 (frontend)
lsof -ti:4200 | xargs kill -9
```

## Daily Usage

Token is saved automatically! Just:
1. Run `./start.sh`
2. Open http://localhost:4200
3. You're in! (No need to login again same day)

Next day, you'll need to get a new token (Zerodha's policy).

---
Made with ❤️ for traders
