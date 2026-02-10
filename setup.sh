#!/bin/bash

echo "🚀 Setting up CogniCap Project..."

# Install backend dependencies
echo "📦 Installing backend dependencies..."
cd backend
pip3 install -r requirements.txt
cd ..

# Create Angular app
echo "📦 Creating Angular frontend..."
cd frontend
npx -p @angular/cli ng new cognicap-app --routing --style=scss --skip-git

# Install Angular Material
echo "📦 Installing Angular Material..."
cd cognicap-app
npm install @angular/material @angular/cdk

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Start backend: cd backend && python3 app.py"
echo "2. Start frontend: cd frontend/cognicap-app && ng serve"
