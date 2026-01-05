#!/bin/bash
#
# TQQQ Signal Engine - User-Friendly Analysis
# 
# Usage: ./tqqq_signal_analysis.sh [date]
# Example: ./tqqq_signal_analysis.sh 2025-08-22
# Example: ./tqqq_signal_analysis.sh (for latest analysis)
#

echo "🎯 TQQQ SIGNAL ENGINE - COMPREHENSIVE ANALYSIS"
echo "=============================================="
echo ""

# Check if date is provided
if [ $# -eq 1 ]; then
    DATE=$1
    echo "📅 Analysis Date: $DATE"
else
    DATE="latest"
    echo "📅 Analysis Date: Latest Available"
fi

echo ""

# Run the comprehensive analysis
cd /Users/krishnag/tools/trading-system
docker-compose exec python-worker python user_friendly_display.py

echo ""
echo "📞 API Usage Examples:"
echo "======================"
echo ""
echo "# Get latest analysis:"
echo "curl -X POST \"http://127.0.0.1:8001/signal/generate\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"symbol\": \"TQQQ\"}'"
echo ""
echo "# Get specific date analysis:"
echo "curl -X POST \"http://127.0.0.1:8001/signal/generate\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"symbol\": \"TQQQ\", \"date\": \"2025-08-22\"}'"
echo ""
echo "# Get comprehensive analysis:"
echo "curl -X POST \"http://127.0.0.1:8001/signal/comprehensive-analysis\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"symbol\": \"TQQQ\"}' | jq '.'"
echo ""
echo "🌐 Web Interface:"
echo "=================="
echo "Streamlit Dashboard: http://localhost:8501"
echo "API Documentation: http://localhost:8001/docs"
echo ""
echo "📊 Available Endpoints:"
echo "======================="
echo "• GET  /signal/health - Engine health check"
echo "• POST /signal/generate - Generate signal"
echo "• POST /signal/comprehensive-analysis - Full analysis"
echo "• GET  /admin/data-summary/{table} - Data overview"
echo "• POST /refresh/earnings-calendar - Refresh data"
echo ""
echo "⚠️  Disclaimer: This analysis is for educational purposes only."
echo "    Always do your own research before trading."
