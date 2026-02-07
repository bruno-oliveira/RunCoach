#!/bin/bash

# Setup script for RunCoach environment variables

echo "================================================"
echo "RunCoach Environment Setup"
echo "================================================"
echo ""

# Check if .env file exists
if [ -f .env ]; then
    echo "✓ .env file exists"
    source .env
else
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    source .env
fi

echo ""
echo "Current Configuration:"
echo "-------------------"
grep -E "^(GOOGLE_CLIENT_ID|SECRET_KEY)" .env | sed 's/=.*/=***HIDDEN***/'
echo ""

# Ask for Google Client ID
if [[ "$GOOGLE_CLIENT_ID" == *"your-google"* ]]; then
    echo "⚠️  Google Client ID needs to be set!"
    echo ""
    echo "To get your Google Client ID:"
    echo "1. Go to: https://console.cloud.google.com/"
    echo "2. Create a project or select existing"
    echo "3. Enable 'Google+ API'"
    echo "4. Go to Credentials → Create OAuth client ID"
    echo "5. Select 'Web application'"
    echo "6. Add authorized JavaScript origins:"
    echo "   - http://localhost:8000"
    echo "   - https://your-app-name.fly.dev"
    echo "7. Copy the Client ID"
    echo ""
    read -p "Enter your Google Client ID: " google_id

    if [ -n "$google_id" ]; then
        # Update .env file
        sed -i '' "s/^GOOGLE_CLIENT_ID=.*/GOOGLE_CLIENT_ID=$google_id/" .env
        echo "✓ Google Client ID updated in .env"
    fi
else
    echo "✓ Google Client ID is configured"
fi

echo ""
echo "Checking Secret Key..."
if [[ "$SECRET_KEY" == *"your-secret"* ]] || [[ "$SECRET_KEY" == *"dev-secret"* ]]; then
    echo "⚠️  Secret key is using default/placeholder"
    read -p "Generate a new secure secret key? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        new_key=$(openssl rand -hex 32)
        sed -i '' "s/^SECRET_KEY=.*/SECRET_KEY=$new_key/" .env
        echo "✓ New secret key generated"
    fi
else
    echo "✓ Secret key is configured"
fi

echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Restart the server to apply changes:"
echo "  python3 -m uvicorn app.main:app --reload --port 8000"
echo ""
