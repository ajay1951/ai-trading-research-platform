#!/usr/bin/env python
"""
Quick start script for the Financial Intelligence System.
Runs the dashboard (web + terminal) and starts interactive mode.
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

def main():
    print("\n" + "="*60)
    print("  Multi-Agent Financial Intelligence System")
    print("="*60 + "\n")
    
    # Check env
    env_file = os.path.exists(".env")
    if not env_file:
        print("[WARNING] .env file not found.")
        print("Creating from .env.example...")
        import shutil
        shutil.copy(".env.example", ".env")
        print("Please edit .env and add your OPENROUTER_API_KEY")
        return 1
    
    with open(".env") as f:
        env_content = f.read()
    if "your_openrouter_api_key" in env_content:
        print("[WARNING] OPENROUTER_API_KEY not set in .env")
        print("Please edit .env and add your actual API key")
        return 1
    
    mode = input("Select mode:\n  1. Web Dashboard + CLI\n  2. Terminal UI Only (Bloomberg-style)\n  3. CLI Only\nChoice [1-3]: ").strip()
    
    # Import and create system
    from main import FinancialIntelligenceSystem
    
    if mode == "1":
        print("\nStarting web dashboard...")
        system = FinancialIntelligenceSystem(
            enable_dashboard=True,
            enable_tui=False,
            use_redis=os.getenv("USE_REDIS", "false").lower() == "true",
            use_chromadb=os.getenv("USE_CHROMADB", "false").lower() == "true",
            use_influxdb=os.getenv("USE_INFLUXDB", "false").lower() == "true"
        )
        system.start_dashboard()
        print("Dashboard: http://localhost:8000")
        print("Opening browser in 2 seconds...")
        import time, webbrowser
        time.sleep(2)
        webbrowser.open("http://localhost:8000")
        print("\nStarting interactive CLI...")
        print("Type 'exit' to quit, '/help' for commands\n")
        system.run_interactive_cli()
    
    elif mode == "2":
        print("\nStarting Terminal UI...")
        print("Press Ctrl+C to exit\n")
        system = FinancialIntelligenceSystem(
            enable_dashboard=False,
            enable_tui=True,
            use_redis=os.getenv("USE_REDIS", "false").lower() == "true",
            use_chromadb=os.getenv("USE_CHROMADB", "false").lower() == "true",
            use_influxdb=os.getenv("USE_INFLUXDB", "false").lower() == "true"
        )
        system.run_tui_interactive()
    
    else:
        print("\nStarting CLI mode...")
        print("Type 'exit' to quit, '/help' for commands\n")
        system = FinancialIntelligenceSystem(
            enable_dashboard=False,
            enable_tui=False,
            use_redis=os.getenv("USE_REDIS", "false").lower() == "true",
            use_chromadb=os.getenv("USE_CHROMADB", "false").lower() == "true",
            use_influxdb=os.getenv("USE_INFLUXDB", "false").lower() == "true"
        )
        system.run_interactive_cli()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
