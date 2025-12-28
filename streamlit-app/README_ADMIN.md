# Trading System Admin Dashboard

A comprehensive back-office interface for monitoring and managing the trading system. This dashboard replaces the previous user-facing interface with an admin-focused tool for system management.

## Features

### 🏠 Dashboard Overview
- **System Health Monitoring**: Real-time status of all services and data sources
- **Key Metrics**: Data sources, refresh status, signal generation, and system health
- **Recent Activity**: Timeline of system events, data refreshes, and operations
- **Data Freshness**: Visual tracking of data recency across different data types

### 📊 Data Sources Management
- **Source Overview**: List all configured data sources with status and performance metrics
- **Configuration**: Add, edit, and remove data sources
- **Connection Testing**: Verify data source connectivity
- **Rate Limiting**: Monitor and manage API call limits
- **Error Tracking**: Track error rates and troubleshoot issues

### 🔄 Data Management
- **Manual Refresh**: Trigger on-demand data refreshes for specific symbols and data types
- **Refresh Status**: Monitor active, queued, and completed refresh jobs
- **Data Summary**: View table statistics, record counts, and storage usage
- **Quality Metrics**: Monitor data completeness, missing values, and error rates

### 📈 Signals & Screeners
- **Signal Generation**: Generate trading signals using various strategies
- **Signal History**: View recent signals with confidence scores and performance
- **Stock Screener**: Run custom screeners with technical and fundamental criteria
- **Performance Analytics**: Track signal accuracy, returns, and win rates

### 🔍 Audit & Logs
- **Comprehensive Logging**: View all system events with filtering capabilities
- **Log Export**: Export logs to CSV for analysis
- **Error Tracking**: Monitor system errors and troubleshooting information
- **Audit Trail**: Complete audit trail of all system operations

### ⚙️ System Settings
- **General Configuration**: Auto-refresh, data retention, and API settings
- **Security Management**: Authentication, user management, and access control
- **Monitoring Setup**: Health checks, alerting thresholds, and metrics collection

## Installation & Setup

### Prerequisites
- Python 3.8+
- Docker and Docker Compose
- Access to the trading system APIs

### Local Development

1. **Install Dependencies**:
   ```bash
   cd streamlit-app
   pip install -r requirements.txt
   ```

2. **Set Environment Variables**:
   ```bash
   export PYTHON_API_URL="http://localhost:8001"
   export GO_API_URL="http://localhost:8000"
   ```

3. **Run the Dashboard**:
   ```bash
   streamlit run admin_main.py
   ```

### Docker Deployment

1. **Build and Run**:
   ```bash
   cd streamlit-app
   docker-compose up -d
   ```

2. **Access the Dashboard**:
   Open http://localhost:8501 in your browser

## API Integration

The admin dashboard integrates with both the Python Worker API and Go API:

### Python Worker API Endpoints
- `/admin/data-sources` - Data source management
- `/refresh` - Data refresh operations
- `/admin/data-summary/{table}` - Table statistics
- `/signals/generate` - Signal generation
- `/screener/run` - Stock screening
- `/admin/audit-logs` - System logs
- `/admin/health` - System health

### Go API Endpoints
- `/api/v1/stock/{symbol}` - Stock data retrieval
- `/api/v1/signals` - Signal endpoints
- `/api/v1/screener` - Screener endpoints

## Configuration

### Environment Variables
- `PYTHON_API_URL`: Python Worker API endpoint (default: http://localhost:8001)
- `GO_API_URL`: Go API endpoint (default: http://localhost:8000)

### Data Sources Configuration
Data sources are configured through the dashboard interface. Each source requires:
- Name and type
- API credentials
- Rate limiting settings
- Supported data types
- Priority and fallback settings

## Security

### Authentication
- Admin dashboard supports role-based access control
- Session management with configurable timeouts
- API key authentication for external access

### Access Control
- Three user roles: Viewer, Operator, Admin
- Granular permissions for different features
- IP whitelisting support

## Monitoring & Alerting

### Health Checks
- Database connectivity
- API service availability
- Data source status
- Resource usage monitoring

### Alerts
- CPU/Memory/Disk usage thresholds
- API error rate monitoring
- Data freshness alerts
- Failed refresh notifications

## Troubleshooting

### Common Issues

1. **API Connection Failed**:
   - Check if backend services are running
   - Verify environment variables
   - Check network connectivity

2. **Data Not Refreshing**:
   - Verify data source configuration
   - Check API rate limits
   - Review error logs

3. **Slow Performance**:
   - Check resource usage
   - Review database query performance
   - Optimize data filters

### Debug Mode
Enable debug logging by setting:
```bash
export STREAMLIT_LOG_LEVEL=debug
```

## Development

### Project Structure
```
streamlit-app/
├── admin_main.py          # Main entry point
├── admin_dashboard.py     # Main dashboard application
├── admin_api_client.py    # API client for backend communication
├── app_original_backup.py # Backup of original user-facing app
├── requirements.txt       # Python dependencies
└── Dockerfile            # Docker configuration
```

### Adding New Features

1. Add new pages to the `render_sidebar()` navigation
2. Implement page functions following the existing pattern
3. Add corresponding API endpoints to `admin_api_client.py`
4. Update the documentation

## Production Deployment

### Security Considerations
- Use HTTPS in production
- Enable authentication
- Configure proper CORS settings
- Set up monitoring and alerting

### Performance Optimization
- Enable caching for frequently accessed data
- Optimize database queries
- Use connection pooling
- Configure appropriate timeouts

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the audit logs in the dashboard
3. Check the API service logs
4. Contact the development team

## License

This admin dashboard is part of the trading system project. See the main project LICENSE file for details.
