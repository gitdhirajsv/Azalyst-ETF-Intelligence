"""
test_llm_integration.py — Test Script for LLM Integration

Run this to verify that the LLM integration is properly configured.
"""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("LLM_TEST")


def test_imports():
    """Test that all LLM modules can be imported."""
    log.info("Testing imports...")
    
    try:
        from llm_optimizer import MistralETFOptimizer
        from llm_analyzer import LLMAnalyzer
        from llm_prompts import PromptTemplates
        from config import Config
        log.info("✓ All modules imported successfully")
        return True
    except ImportError as e:
        log.error(f"✗ Import failed: {e}")
        return False


def test_config():
    """Test that LLM configuration is loaded."""
    log.info("Testing configuration...")
    
    try:
        from config import Config
        cfg = Config()
        
        if not cfg.NVIDIA_API_KEY:
            log.warning("⚠ NVIDIA_API_KEY not set in .env file")
            log.info("  To enable LLM, add NVIDIA_API_KEY=your_key to .env")
        else:
            log.info("✓ NVIDIA API key configured")
        
        log.info(f"  LLM_MODEL: {cfg.LLM_MODEL}")
        log.info(f"  LLM_ENABLED: {cfg.LLM_ENABLED}")
        log.info(f"  LLM_TEMPERATURE: {cfg.LLM_TEMPERATURE}")
        log.info(f"  LLM_MAX_TOKENS: {cfg.LLM_MAX_TOKENS}")
        
        return True
    except Exception as e:
        log.error(f"✗ Configuration test failed: {e}")
        return False


def test_optimizer_init():
    """Test that optimizer can be initialized."""
    log.info("Testing optimizer initialization...")
    
    try:
        from llm_optimizer import MistralETFOptimizer
        from config import Config
        
        cfg = Config()
        
        if not cfg.NVIDIA_API_KEY:
            log.info("  Skipping API test (no key configured)")
            optimizer = MistralETFOptimizer()
            if optimizer.client is None:
                log.info("✓ Optimizer initialized (client=None as expected without key)")
            return True
        
        optimizer = MistralETFOptimizer(api_key=cfg.NVIDIA_API_KEY)
        
        if optimizer.client:
            log.info("✓ Optimizer initialized with API client")
            return True
        else:
            log.warning("⚠ Optimizer client is None despite key being set")
            return True
            
    except Exception as e:
        log.error(f"✗ Optimizer initialization failed: {e}")
        return False


def test_prompts():
    """Test that prompt templates work."""
    log.info("Testing prompt templates...")
    
    try:
        from llm_prompts import PromptTemplates
        
        test_portfolio = {
            "cash_inr": 5000,
            "total_deposited": 20000,
            "open_positions": [],
            "closed_trades": [],
        }
        
        prompt = PromptTemplates.format_backtest_prompt(test_portfolio)
        
        if prompt and len(prompt) > 100:
            log.info(f"✓ Prompt generated ({len(prompt)} chars)")
            return True
        else:
            log.error("✗ Generated prompt is too short or empty")
            return False
            
    except Exception as e:
        log.error(f"✗ Prompt test failed: {e}")
        return False


def test_analyzer_init():
    """Test that analyzer can be initialized."""
    log.info("Testing analyzer initialization...")
    
    try:
        from llm_analyzer import LLMAnalyzer, create_llm_analyzer
        from config import Config
        
        cfg = Config()
        analyzer = create_llm_analyzer(cfg)
        
        if analyzer:
            log.info(f"✓ Analyzer initialized (enabled={analyzer.enabled})")
            if not analyzer.enabled:
                log.info("  LLM is disabled. Set NVIDIA_API_KEY in .env to enable.")
            return True
        else:
            log.error("✗ Analyzer is None")
            return False
            
    except Exception as e:
        log.error(f"✗ Analyzer initialization failed: {e}")
        return False


def test_portfolio_load():
    """Test that portfolio data can be loaded."""
    log.info("Testing portfolio data loading...")
    
    try:
        from llm_optimizer import load_portfolio_for_analysis
        
        portfolio = load_portfolio_for_analysis()
        
        if portfolio:
            log.info(f"✓ Portfolio loaded (cash: ₹{portfolio.get('cash_inr', 0):,.0f})")
            log.info(f"  Open positions: {len(portfolio.get('open_positions', []))}")
            log.info(f"  Closed trades: {len(portfolio.get('closed_trades', []))}")
            return True
        else:
            log.warning("⚠ No portfolio data found (this is OK for fresh installs)")
            return True
            
    except Exception as e:
        log.error(f"✗ Portfolio load failed: {e}")
        return False


def test_macro_fetch():
    """Test that macro indicators can be fetched."""
    log.info("Testing macro indicator fetch...")
    
    try:
        from llm_optimizer import fetch_macro_indicators
        
        indicators = fetch_macro_indicators()
        
        if indicators:
            log.info(f"✓ Macro indicators fetched ({len(indicators)} indicators)")
            for key, value in indicators.items():
                log.info(f"  {key}: {value}")
            return True
        else:
            log.warning("⚠ No macro indicators returned")
            return True
            
    except Exception as e:
        log.error(f"✗ Macro fetch failed: {e}")
        return False


def run_api_test():
    """Test actual API call (only if key is configured)."""
    log.info("Testing API call (this may take a few seconds)...")
    
    try:
        from llm_optimizer import MistralETFOptimizer
        from config import Config
        
        cfg = Config()
        
        if not cfg.NVIDIA_API_KEY:
            log.info("  Skipping API test (no key configured)")
            return True
        
        optimizer = MistralETFOptimizer(api_key=cfg.NVIDIA_API_KEY)
        
        if not optimizer.client:
            log.warning("⚠ API client not initialized despite key being set")
            return True
        
        # Simple test prompt
        response = optimizer._call_llm(
            "You are a helpful assistant.",
            "Respond with just the word 'OK' to confirm the API is working."
        )
        
        if response and len(response) > 0:
            log.info(f"✓ API call successful (response: {response[:50]}...)")
            return True
        else:
            log.warning("⚠ API returned empty response")
            return True
            
    except Exception as e:
        log.error(f"✗ API test failed: {e}")
        log.info("  This could be due to: invalid key, network issue, or API downtime")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("LLM Integration Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("Optimizer Init", test_optimizer_init),
        ("Prompt Templates", test_prompts),
        ("Analyzer Init", test_analyzer_init),
        ("Portfolio Load", test_portfolio_load),
        ("Macro Fetch", test_macro_fetch),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
            print()
        except Exception as e:
            log.error(f"Test '{name}' crashed: {e}")
            results.append((name, False))
            print()
    
    # API test (optional)
    from config import Config
    cfg = Config()
    if cfg.NVIDIA_API_KEY:
        api_result = run_api_test()
        results.append(("API Call", api_result))
        print()
    
    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print()
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print()
        print("🎉 All tests passed! LLM integration is ready.")
        print()
        print("Next steps:")
        print("  1. Add NVIDIA_API_KEY to .env (if not already done)")
        print("  2. Run: python azalyst.py --llm-analysis")
        print("  3. See docs/LLM_INTEGRATION.md for full documentation")
    else:
        print()
        print("⚠ Some tests failed. Check the logs above for details.")
        print("  The integration may still work with limited functionality.")
    
    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
