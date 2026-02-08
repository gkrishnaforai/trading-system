#!/usr/bin/env python3
"""
Debug the import issue step by step
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_import_from_outside():
    """Test import from outside the package (like other files do)"""
    print("🔍 Testing import from OUTSIDE app.database package...")
    try:
        from app.database import db
        print(f"   ✅ SUCCESS: db = {type(db)}")
        print(f"   ✅ db.session_factory = {getattr(db, 'session_factory', 'NOT_FOUND')}")
        return True
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False

def test_import_from_inside():
    """Test import from inside the app.database package"""
    print("\n🔍 Testing import from INSIDE app.database package...")
    
    # Simulate being inside the package by changing the import path
    try:
        # This is what happens when we're inside app.database/repositories.py
        import sys
        original_path = sys.path.copy()
        
        # Add current directory to simulate being inside the package
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app', 'database'))
        
        # Try the same import
        from app.database import db
        print(f"   ✅ SUCCESS: db = {type(db)}")
        return True
        
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    finally:
        # Restore original path
        sys.path = original_path

def test_direct_module_import():
    """Test importing the database module directly"""
    print("\n🔍 Testing direct module import...")
    try:
        import app.database
        print(f"   ✅ SUCCESS: app.database = {type(app.database)}")
        print(f"   ✅ app.database.db = {getattr(app.database, 'db', 'NOT_FOUND')}")
        return True
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False

def test_sys_modules_approach():
    """Test using sys.modules approach"""
    print("\n🔍 Testing sys.modules approach...")
    try:
        import sys
        database_module = sys.modules.get('app.database')
        print(f"   ✅ sys.modules['app.database'] = {database_module}")
        
        if database_module:
            db = getattr(database_module, 'db', None)
            print(f"   ✅ db = {db}")
            return True
        else:
            print(f"   ❌ Module not found in sys.modules")
            return False
            
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False

def main():
    """Main debug function"""
    print("🐛 DEBUGGING IMPORT ISSUE STEP BY STEP")
    print("=" * 60)
    
    results = []
    
    # Test 1: Import from outside (like working files)
    results.append(test_import_from_outside())
    
    # Test 2: Import from inside (like our failing case)
    results.append(test_import_from_inside())
    
    # Test 3: Direct module import
    results.append(test_direct_module_import())
    
    # Test 4: sys.modules approach
    results.append(test_sys_modules_approach())
    
    print("\n" + "=" * 60)
    print("🎯 DEBUG RESULTS:")
    print("=" * 60)
    
    if results[0] and not results[1]:
        print("✅ CONFIRMED: Import works from OUTSIDE but fails from INSIDE")
        print("🔧 SOLUTION: Use sys.modules approach when inside the package")
    elif all(results):
        print("✅ All imports working - issue might be elsewhere")
    else:
        print("❌ Multiple import issues detected")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
