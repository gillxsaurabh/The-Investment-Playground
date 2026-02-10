#!/bin/bash

echo "Starting CogniCap..."

# Start backend in background
echo "Starting Backend Server..."
cd backend
source venv/bin/activate
python3 app.py &
BACKEND_PID=$!
cd ..

# Wait for backend to start
sleep 3

# Start frontend
echo "Starting Frontend..."
cd frontend/cognicap-app
npm start &
FRONTEND_PID=$!

echo ""
echo "CogniCap is running!"
echo "   Backend:  http://localhost:5000"
echo "   Frontend: http://localhost:4200"
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
