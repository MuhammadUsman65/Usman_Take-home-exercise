# Take-Home Assessment Setup Guide

instructions for setting up the environment and running this assignment

---

## Prerequisites

Ensure you have **Python 3.11+** installed on your system.

## Step 1 Setting up venv (so there is no package conflict)

### On macOS/Linux
python3 -m venv venv

### On Windows
python -m venv venv

## Step 2 activate the virtual environment

### On macOS/Linux
source venv/bin/activate

### On Windows powershell
venv\Scripts\activate.ps1

## Install relevant dependencies
pip install -r requirements.txt

## Set up data folder
in the root of the project create data folder and add the knowledge files there (`customers.json`,`knowledge.md`, `questions.txt`)

## Setup the .env file inside the root
1. create the .env file (touch .env)
2. add GROQ_API_KEY= (not in quotation marks)
3. add LLM_MODEL= openai/gpt-oss-120b

## Run the Test cases:
1. pytest -v (inside the root directory)
2. python main.py (to run the code)