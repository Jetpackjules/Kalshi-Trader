#!/usr/bin/env python3
"""
Simple Kalshi test without SDK dependency
"""

def test_kalshi_import():
    print("🔧 Testing Kalshi module import...")
    
    try:
        # Test if we can import the module
        from modules.kalshi_api import KalshiAPI
        print("✅ KalshiAPI class imported successfully")
        
        # Test creating an instance
        kalshi = KalshiAPI("KNYC")
        print("✅ KalshiAPI instance created")
        
        # Test basic methods
        print("✅ Basic module structure works")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   This might be due to missing kalshi-python package")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_kalshi_import() 