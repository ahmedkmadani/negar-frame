## Development Setup

1. **Prerequisites**
   ```bash
   # Create development network
   docker network create dev-network
   ```

2. **Start Services**
   ```bash
   # Build and start all services
   docker-compose -f docker-compose-dev.yml up --build
   ```

3. **Access Documentation**
   - Swagger UI: `http://localhost:5004/docs`
   - ReDoc: `http://localhost:5004/redoc`

## Monitoring and Health

### Health Checks
- Each service provides a `/health` endpoint
- Monitors:
  - Redis connectivity
  - MinIO availability
  - WebSocket connections
  - Processing queue status

### Logging
- Centralized logging system
- Log levels: DEBUG, INFO, WARNING, ERROR
- Service-specific logging configuration

## Security Considerations

### Network Security
- Internal services not exposed externally
- WebSocket connections over secure protocols
- Redis password protection
- MinIO access control

### Data Security
- Temporary frame storage
- Secure object storage access
- Client authentication for WebSocket

## Error Handling

### Retry Mechanisms
- Automatic Redis reconnection
- MinIO operation retries
- WebSocket connection recovery

### Circuit Breakers
- Service health monitoring
- Automatic failover capabilities
- Rate limiting protection

## Performance Optimization

### Caching
- Redis frame metadata caching
- MinIO presigned URL caching
- WebSocket message batching

### Scaling
- Horizontal scaling capability
- Load balancing ready
- Stateless service design

## Contributing

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Create pull request

## License

[Your License Here]
