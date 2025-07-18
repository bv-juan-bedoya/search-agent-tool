"""
Test the fallback date parser functionality directly
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'seacrh_by_date'))

from search_by_date import fallback_date_parser, build_filter_expression
from datetime import datetime, timedelta

def test_fallback_parser():
    """Test the fallback date parser that doesn't require Azure AI"""
    
    print("🧪 Testing Fallback Date Parser")
    print("=" * 50)
    
    test_cases = [
        "mes pasado",
        "último mes", 
        "semana pasada",
        "última semana",
        "ayer",
        "hoy",
        "documentos de 2024",
        "archivos de 2023",
        "reportes random text"
    ]
    
    for query in test_cases:
        print(f"Testing: '{query}'")
        try:
            result = fallback_date_parser(query)
            print(f"  📅 Result: {result}")
            
            # Test filter building
            filter_expr = build_filter_expression(result)
            print(f"  🔍 Filter: {filter_expr}")
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
        print()
    
    print("=" * 50)
    print("✅ Fallback parser test completed!")

def test_date_calculations():
    """Test that date calculations are working correctly"""
    
    print("\n🧪 Testing Date Calculations")
    print("=" * 50)
    
    today = datetime.now().date()
    print(f"Today: {today}")
    
    # Test yesterday
    yesterday_result = fallback_date_parser("ayer")
    expected_yesterday = (today - timedelta(days=1)).isoformat()
    print(f"Yesterday test - Expected: {expected_yesterday}, Got: {yesterday_result.get('date')}")
    assert yesterday_result.get('date') == expected_yesterday, "Yesterday calculation failed"
    
    # Test today
    today_result = fallback_date_parser("hoy")
    expected_today = today.isoformat()
    print(f"Today test - Expected: {expected_today}, Got: {today_result.get('date')}")
    assert today_result.get('date') == expected_today, "Today calculation failed"
    
    print("✅ Date calculation tests passed!")

if __name__ == "__main__":
    test_fallback_parser()
    test_date_calculations()
