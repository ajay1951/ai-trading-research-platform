#!/usr/bin/env python
"""
Installation and setup script for Multi-Agent Financial Intelligence System.
Installs dependencies, checks configuration, and validates installation.
"""
import sys
import os
import subprocess
import shutil
from pathlib import Path

def print_banner():
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   Multi-Agent Financial Intelligence System                  ║
║   Installation & Validation Script                           ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)

def check_python():
    """Check Python version."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("[ERROR] Python 3.9+ required")
        return False
    print(f"[OK] Python {version.major}.{version.minor}.{version.micro}")
    return True

def install_dependencies():
    """Install required packages."""
    print("\n[1/5] Installing dependencies...")
    req_file = Path("requirements.txt")
    if not req_file.exists():
        print("[ERROR] requirements.txt not found")
        return False
    
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
            capture_output=False
        )
        print("[OK] Dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] pip install failed: {e}")
        return False

def setup_env():
    """Create .env file if missing."""
    print("\n[2/5] Checking environment configuration...")
    env_file = Path(".env")
    if not env_file.exists():
        print("  Creating .env from template...")
        shutil.copy(".env.example", ".env")

    # Check if API key is set
    content = env_file.read_text()
    if "your_openrouter_api_key" in content:
        print("  [WARNING] OPENROUTER_API_KEY not configured in .env")
        api_key = input("  Please enter your OPENROUTER_API_KEY (or press Enter to skip): ").strip()
        if api_key:
            content = content.replace("your_openrouter_api_key", api_key)
            env_file.write_text(content)
            print("  [OK] OPENROUTER_API_KEY saved to .env file.")
        else:
            print("  [WARNING] API Key not provided. Please edit .env manually.")
            return False

    print("[OK] Environment configured")
    return True

def validate_imports():
    """Test that all modules can be imported."""
    print("\n[3/5] Validating imports...")
    
    modules = [
        ('core.memory', 'SharedMemory'),
        ('core.orchestrator', 'MasterCoordinator'),
        ('core.nl_interface', 'NaturalLanguageInterface'),
        ('core.storage', 'DataManager'),
        ('agents.data_agent', 'RealTimeDataAgent'),
        ('agents.quant_agent', 'QuantitativeAnalysisAgent'),
        ('agents.research_agent', 'FundamentalResearchAgent'),
        ('agents.risk_agent', 'RiskManagementAgent'),
        ('models.technical_indicators', 'TechnicalIndicators'),
        ('models.risk_models', 'ValueAtRisk'),
        ('terminal_ui', ''), # Changed to check module import directly
    ]
    
    failed = []
    for module_name, class_name in modules:
        try:
            if class_name: # If a specific class name is provided
                module = __import__(module_name, fromlist=[class_name])
                cls = getattr(module, class_name)
                print(f"  [OK] {module_name}.{class_name}")
            else: # If only module name is provided
                module = __import__(module_name)
                print(f"  [OK] {module_name}")
        except ImportError as e:
            print(f"  [FAIL] {module_name}: {e}")
            failed.append(module_name)
        except Exception as e:
            if class_name:
                print(f"  [FAIL] {module_name}.{class_name}: {e}")
            else:
                print(f"  [FAIL] {module_name}: {e}")
            failed.append(module_name)
    
    return len(failed) == 0

def run_smoke_tests():
    """Run basic functionality tests."""
    print("\n[4/5] Running smoke tests...")
    
    try:
        # Test technical indicators
        import pandas as pd
        import numpy as np
        from models.technical_indicators import TechnicalIndicators
        
        prices = pd.Series([100 + i + np.random.randn() for i in range(100)])
        sma = TechnicalIndicators.sma(prices, 20)
        assert len(sma) == 100
        print("  [OK] Technical indicators work")
        
        # Test risk models
        from models.risk_models import ValueAtRisk, PortfolioAnalyzer
        returns = np.random.normal(0.001, 0.02, 365)
        var_calc = ValueAtRisk(pd.Series(returns), 100000) # Convert to Pandas Series
        var = var_calc.calculate()
        assert var.var_95 > 0
        print("  [OK] VaR calculation works")
        
        analyzer = PortfolioAnalyzer()
        portfolio = {"BTC": 0.5, "ETH": 0.3, "USDT": 0.2}
        hhi = analyzer.calculate_concentration(portfolio)
        assert 0 <= hhi <= 10000
        print("  [OK] Portfolio analysis works")
        
        # Test NL interface
        from core.nl_interface import nl_interface
        parsed = nl_interface.parse_query("Analyze BTC/USDT")
        assert parsed.intent == "analyze"
        print("  [OK] NL parsing works")
        
        return True
    except Exception as e:
        print(f"  [FAIL] Smoke test error: {e}")
        import traceback
        traceback.print_exc()
        return False

def print_next_steps():
    """Print next steps for user."""
    print("\n" + "="*60)
    print("INSTALLATION COMPLETE")
    print("="*60)
    print("""
Next steps:

1. Verify your OPENROUTER_API_KEY is set in .env file

2. Run the system in your preferred mode:

   ┌─────────────────────────────────────────────────┐
   │  Terminal UI (Bloomberg-style)                  │
   │      python main.py --tui                       │
   │  or                                             │
   │      python run_tui.py                          │
   ├─────────────────────────────────────────────────┤
   │  Web Dashboard                                  │
   │      python main.py                             │
   │  Then open http://localhost:8000                │
   ├─────────────────────────────────────────────────┤
   │  CLI Interactive                                │
   │      python main.py --interactive               │
   ├─────────────────────────────────────────────────┤
   │  Single Query                                   │
   │      python main.py --query "Analyze BTC"       │
   └─────────────────────────────────────────────────┘

3. Try these example queries:
   - "Analyze BTC/USDT and generate trading signal"
   - "What's the risk exposure for ETH?"
   - "Should I buy Tesla stock?"
   - "Calculate VaR for my portfolio"

4. Check documentation:
   - README.md - Full documentation
   - TUI_FEATURES.md - Terminal UI guide

For support, see: https://github.com/your-repo/issues
    """)

def main():
    print_banner()
    
    # Step 1: Check Python
    if not check_python():
        return 1
    
    # Step 2: Install dependencies
    if not install_dependencies():
        print("\n[WARNING] Dependency installation had issues.")
        print("Try running: pip install -r requirements.txt")
    
    # Step 3: Setup environment
    env_ok = setup_env()
    
    # Step 4: Validate imports
    imports_ok = validate_imports()
    
    # Step 5: Smoke tests
    smoke_ok = run_smoke_tests()
    
    # Summary
    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    print(f"  Environment: {'✓ OK' if env_ok else '✗ Needs config'}")
    print(f"  Imports: {'✓ OK' if imports_ok else '✗ Failed'}")
    print(f"  Smoke tests: {'✓ OK' if smoke_ok else '✗ Failed'}")
    
    if env_ok and imports_ok and smoke_ok:
        print("\n[SUCCESS] System ready!")
        print_next_steps()
        return 0
    else:
        print("\n[WARNING] Some checks failed. Review errors above.")
        print("Fix issues and re-run this script.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
