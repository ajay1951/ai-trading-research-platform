#!/usr/bin/env python
"""
Launch the Multi-Agent Financial Intelligence System in TUI mode
(Bloomberg Terminal-style interface).
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

def main():
    print("\n" + "="*70)
    print("  MULTI-AGENT FINANCIAL INTELLIGENCE SYSTEM")
    print("  Terminal UI Mode - Bloomberg Terminal Edition")
    print("="*70)
    
    # Check API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("\n[ERROR] OPENROUTER_API_KEY not set in .env file!")
        print("Please copy .env.example to .env and add your API key.")
        return 1
    
    # Import and create system instance with TUI only
    from main import FinancialIntelligenceSystem
    system = FinancialIntelligenceSystem(
        enable_dashboard=False,  # No web dashboard in TUI mode
        enable_tui=True,
        use_redis=os.getenv("USE_REDIS", "false").lower() == "true",
        use_chromadb=os.getenv("USE_CHROMADB", "false").lower() == "true",
        use_influxdb=os.getenv("USE_INFLUXDB", "false").lower() == "true"
    )
    
    print("\nStarting Terminal Dashboard...")
    print("Use /help to see available commands")
    print("Press Ctrl+C to exit\n")
    
    # Run TUI interactive mode
    system.run_tui_interactive()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
