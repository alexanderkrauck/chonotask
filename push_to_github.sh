#!/bin/bash

# Instructions to push ChronoTask to GitHub
# 
# 1. First, create a new repository on GitHub:
#    - Go to https://github.com/new
#    - Name: ChronoTask
#    - Description: Python task scheduler with cron-like scheduling, HTTP/MCP APIs, and Docker support
#    - Make it public or private as you prefer
#    - Do NOT initialize with README, .gitignore, or license (we already have these)
#
# 2. After creating the repository, GitHub will show you the repository URL.
#    Replace YOUR_GITHUB_USERNAME in the command below with your actual GitHub username:

echo "Adding GitHub remote..."
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/ChronoTask.git

echo "Pushing to GitHub..."
git push -u origin main

echo "Done! Your ChronoTask project is now on GitHub."
echo "You can view it at: https://github.com/YOUR_GITHUB_USERNAME/ChronoTask"