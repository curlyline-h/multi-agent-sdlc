#!/bin/bash
# Bootstrap development environment
echo "Setting up development environment..."
pip install -r backend/requirements-dev.txt -r backend/requirements.txt
pip install -r agents/requirements.txt
cd frontend && npm install
echo "Setup complete!"
